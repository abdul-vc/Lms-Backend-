from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model
from .serializers import UserSerializer
from organizations.permissions import IsOrgScoped
from organizations.views import HasRolePermission
from organizations.audit import log_activity

User = get_user_model()


class UserListCreateView(generics.ListCreateAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, IsOrgScoped, HasRolePermission]
    required_permission = 'can_manage_users'

    def get_queryset(self):
        qs = User.objects.all()
        org_id = self.request.query_params.get('organization') or self.request.query_params.get('organization_id')
        if org_id:
            return qs.filter(organization_id=org_id)
        if self.request.user.is_platform_super_admin:
            return qs
        return qs.filter(organization_id=self.request.user.organization_id)

    def perform_create(self, serializer):
        from rest_framework.exceptions import ValidationError
        from organizations.emails import send_user_welcome_credentials_email

        raw_password = self.request.data.get('password')
        target_email = self.request.data.get('email') or self.request.data.get('username')

        if target_email:
            clean_em = str(target_email).strip()
            existing = User.objects.filter(email__iexact=clean_em).first() or User.objects.filter(username__iexact=clean_em).first()
            if existing and existing.is_platform_super_admin:
                raise ValidationError({'email': f"The email address '{clean_em}' is reserved for the Platform Super Admin account and cannot be assigned to an organization user."})

        if self.request.user.is_platform_super_admin:
            org_id = self.request.data.get('organization')
            if not org_id:
                raise ValidationError({'organization': 'organization is required when creating a user as super-admin.'})
            user = serializer.save(is_platform_super_admin=False)
        else:
            user = serializer.save(organization=self.request.user.organization, is_platform_super_admin=False)
        
        log_activity(self.request, 'user_created', target=user, organization=user.organization)

        # Trigger immediate SMTP welcome email with username, password & login portal URL
        try:
            send_user_welcome_credentials_email(user=user, raw_password=raw_password, request=self.request)
        except Exception as e:
            print(f"[USER CREATION EMAIL FAILED] {e}")


class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, IsOrgScoped, HasRolePermission]
    required_permission = 'can_manage_users'

    def get_queryset(self):
        if self.request.user.is_platform_super_admin:
            return User.objects.all()
        return User.objects.filter(organization_id=self.request.user.organization_id)

    def perform_update(self, serializer):
        user = serializer.save()
        if not user.is_active:
            log_activity(self.request, 'user_deactivated', target=user, organization=user.organization)
        else:
            log_activity(self.request, 'user_updated', target=user, organization=user.organization)

    def perform_destroy(self, instance):
        log_activity(self.request, 'user_deleted', target=instance, organization=instance.organization)
        instance.delete()


class LearnerDashboardStatsView(APIView):
    """Returns live, real-time learner dashboard metrics, active courses, leaderboard, and badges."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        org = user.organization

        # 1. Active Streak & Gamification Metrics
        streak_days = max(user.streak_days, 1)  # Active learner logged in
        points = user.points
        level = user.level

        # 2. Dynamic Real Leaderboard (Top 5 active users in the organization)
        leaderboard_qs = User.objects.filter(is_active=True)
        if org:
            leaderboard_qs = leaderboard_qs.filter(organization=org)
        
        top_users = leaderboard_qs.order_by('-points', 'id')[:5]
        leaderboard_data = []
        for idx, u in enumerate(top_users, start=1):
            leaderboard_data.append({
                'rank': idx,
                'id': u.id,
                'name': u.full_name,
                'job_title': u.job_title or (u.role.name if u.role else 'Member'),
                'points': u.points,
                'initials': u.avatar_initials,
                'is_current_user': u.id == user.id
            })

        # 3. Dynamic Real In-Progress or Completed Course
        from courses.models import Course, LessonProgress, AssessmentAttempt, IssuedCertificate, Lesson
        published_courses = Course.objects.filter(status='published')
        if org:
            published_courses = published_courses.filter(organization=org)

        total_published_count = published_courses.count()
        in_progress_course_data = None

        user_certs = IssuedCertificate.objects.filter(user=user).select_related('course')
        user_attempts = AssessmentAttempt.objects.filter(user=user).order_by('-started_at').select_related('course')
        user_lesson_progress = LessonProgress.objects.filter(user=user, completed=True).select_related('lesson__module__course')

        target_course = None
        if user_certs.exists():
            target_course = user_certs.first().course
        elif user_attempts.exists():
            target_course = user_attempts.first().course
        elif user_lesson_progress.exists():
            target_course = user_lesson_progress.first().lesson.module.course
        elif published_courses.exists():
            target_course = published_courses.first()

        if target_course:
            total_lessons = Lesson.objects.filter(module__course=target_course).count()
            completed_lessons = LessonProgress.objects.filter(user=user, lesson__module__course=target_course, completed=True).count()
            has_cert = IssuedCertificate.objects.filter(user=user, course=target_course).exists()
            has_passed = AssessmentAttempt.objects.filter(user=user, course=target_course, passed=True).exists()

            if has_cert or has_passed or (total_lessons > 0 and completed_lessons == total_lessons):
                prog_pct = 100
                c_status = 'completed'
            else:
                prog_pct = int((completed_lessons / total_lessons * 100)) if total_lessons > 0 else (15 if completed_lessons > 0 else 0)
                c_status = 'in_progress' if prog_pct > 0 else 'not_started'

            in_progress_course_data = {
                'id': target_course.id,
                'title': target_course.title,
                'subtitle': target_course.subtitle or (f"{completed_lessons} of {total_lessons} lessons completed" if total_lessons > 0 else "Active Course"),
                'progress_percent': prog_pct,
                'status': c_status,
                'has_certificate': has_cert
            }

        # 4. Real Earned Badges
        earned_badges = []
        certs_count = IssuedCertificate.objects.filter(user=user).count()
        attempts_passed = AssessmentAttempt.objects.filter(user=user, passed=True).count()

        if streak_days >= 1:
            earned_badges.append({'key': 'streak', 'label': f'⚡ {streak_days}-Day Streak', 'color': 'emerald'})
        if certs_count > 0:
            earned_badges.append({'key': 'certified', 'label': f'🎓 {certs_count} Certificate(s)', 'color': 'amber'})
        elif attempts_passed > 0:
            earned_badges.append({'key': 'passed', 'label': '🏆 Assessment Passed', 'color': 'amber'})
        else:
            earned_badges.append({'key': 'newbie', 'label': '🚀 Registered Learner', 'color': 'indigo'})

        return Response({
            'user': {
                'id': user.id,
                'full_name': user.full_name,
                'username': user.username,
                'email': user.email,
                'job_title': user.job_title or (user.role.name if user.role else 'Learner'),
                'points': points,
                'streak_days': streak_days,
                'level': level,
            },
            'in_progress_course': in_progress_course_data,
            'total_published_courses': total_published_count,
            'leaderboard': leaderboard_data,
            'badges': earned_badges,
        })


class SuperAdminListCreateView(APIView):
    """
    GET /api/users/super-admins/ — Returns list of all Platform Super Admins
    POST /api/users/super-admins/ — Creates a new Platform Super Admin and sends welcome credentials email
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.is_platform_super_admin:
            return Response({"detail": "Only Platform Super Admins can access this resource."}, status=403)
        
        super_admins = User.objects.filter(is_platform_super_admin=True).order_by('-date_joined')
        data = []
        for u in super_admins:
            data.append({
                'id': u.id,
                'first_name': u.first_name,
                'last_name': u.last_name,
                'full_name': u.full_name,
                'username': u.username,
                'email': u.email,
                'is_active': u.is_active,
                'date_joined': u.date_joined,
            })
        return Response(data)

    def post(self, request):
        if not request.user.is_platform_super_admin:
            return Response({"detail": "Only Platform Super Admins can create new Super Admins."}, status=403)

        email = request.data.get('email', '').strip()
        username = request.data.get('username', '').strip() or email
        first_name = request.data.get('first_name', '').strip()
        last_name = request.data.get('last_name', '').strip()
        password = request.data.get('password', '').strip()

        if not email:
            return Response({"detail": "Email address is required."}, status=400)
        if not password:
            return Response({"detail": "Password is required."}, status=400)

        if User.objects.filter(username=username).exists():
            return Response({"detail": f"Username '{username}' is already taken."}, status=400)

        if User.objects.filter(email=email).exists():
            return Response({"detail": f"Email '{email}' is already registered."}, status=400)

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            is_platform_super_admin=True,
            is_staff=True,
            is_superuser=True,
            organization=None
        )

        log_activity(request, 'super_admin_created', target=user, metadata={'email': email})

        # Send welcome email via SMTP
        from organizations.emails import send_superadmin_welcome_email
        email_sent, email_msg = send_superadmin_welcome_email(user=user, raw_password=password, request=request)

        return Response({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'full_name': user.full_name,
            'message': 'Super Admin created successfully!',
            'email_status': email_msg
        }, status=201)

    def delete(self, request, pk=None):
        if not request.user.is_platform_super_admin:
            return Response({"detail": "Only Platform Super Admins can delete Super Admins."}, status=403)

        if not pk:
            return Response({"detail": "Super Admin ID is required."}, status=400)

        if request.user.id == int(pk):
            return Response({"detail": "You cannot delete your own active Super Admin account."}, status=400)

        user_to_delete = User.objects.filter(pk=pk, is_platform_super_admin=True).first()
        if not user_to_delete:
            return Response({"detail": "Super Admin account not found."}, status=404)

        log_activity(request, 'super_admin_deleted', target=user_to_delete, metadata={'email': user_to_delete.email})
        user_to_delete.delete()

        return Response({"detail": "Super Admin account deleted successfully."})

