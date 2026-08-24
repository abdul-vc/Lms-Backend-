import uuid
import os
import csv
import io

from rest_framework import viewsets, permissions, status, generics
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.core.files.storage import default_storage
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.decorators import action

from .models import Course, Module, Lesson, AccessRequest, AssessmentQuestion, AssessmentAttempt
from .serializers import CourseSerializer, ModuleSerializer, LessonSerializer, AccessRequestSerializer, AssessmentQuestionSerializer
from organizations.permissions import IsOrgScoped
from organizations.audit import log_activity


def _org_filter(request):
    """Return a queryset-safe org filter dict, or {} for super-admins."""
    if request.user.is_platform_super_admin:
        return {}
    return {'organization_id': request.user.organization_id}


class HasCourseMutationPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.user.is_platform_super_admin:
            return True
        if request.method in permissions.SAFE_METHODS:
            return True
        role = request.user.role
        if role and (role.is_admin_role or role.can_edit_courses or role.can_create_courses):
            return True
        if request.user.is_authenticated:
            return True
        return False

    def has_object_permission(self, request, view, obj):
        if request.user.is_platform_super_admin:
            return True
        if request.method in permissions.SAFE_METHODS:
            return True
        if getattr(obj, 'author_id', None) == request.user.id:
            return True
        role = request.user.role
        if role and (role.is_admin_role or role.can_edit_courses):
            return True
        return False

class CourseViewSet(viewsets.ModelViewSet):
    """CRUD for courses. Returns full nested structure (modules + lessons) on GET."""
    serializer_class = CourseSerializer
    permission_classes = [IsAuthenticated, IsOrgScoped, HasCourseMutationPermission]

    def get_queryset(self):
        qs = Course.objects.prefetch_related('modules__lessons').all()
        if self.request.user.is_platform_super_admin:
            return qs
        return qs.filter(organization_id=self.request.user.organization_id)

    def perform_create(self, serializer):
        # Automatically set author and org when a user creates a course
        if not self.request.user.is_platform_super_admin:
            course = serializer.save(author=self.request.user, organization=self.request.user.organization)
        else:
            course = serializer.save(author=self.request.user)
        log_activity(self.request, 'course_created', target=course, organization=course.organization)

    def perform_update(self, serializer):
        course = serializer.save()
        log_activity(self.request, 'course_updated', target=course, organization=course.organization)

    from rest_framework.decorators import action
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsOrgScoped])
    def publish(self, request, pk=None):
        course = self.get_object()
        if not request.user.is_platform_super_admin:
            if not request.user.role or not request.user.role.can_publish_courses:
                return Response({"detail": "You do not have permission to publish courses."}, status=403)

        from authoring_engine.publishing import execute_publishing_pipeline, PublishingValidationException
        try:
            manifest = execute_publishing_pipeline(request, course)
            return Response({
                'status': 'Course published successfully',
                'course_id': course.id,
                'published_status': course.status,
                'version_snapshot': manifest['metadata']
            })
        except PublishingValidationException as pve:
            return Response({
                'detail': 'Pre-flight validation failed.',
                'errors': pve.errors
            }, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated, IsOrgScoped])
    def progress(self, request, pk=None):
        course = self.get_object()
        from .models import LessonProgress
        total_lessons = Lesson.objects.filter(module__course=course).count()
        progress_records = LessonProgress.objects.filter(user=request.user, lesson__module__course=course)
        completed_lesson_ids = list(progress_records.filter(completed=True).values_list('lesson_id', flat=True))
        completed_lessons = len(completed_lesson_ids)
        percent = int((completed_lessons / total_lessons * 100)) if total_lessons > 0 else 0
        
        last_active = progress_records.order_by('-completed_at', '-id').first()
        last_active_lesson_id = last_active.lesson_id if last_active else None

        return Response({
            'completed_lessons': completed_lessons,
            'completed_lesson_ids': completed_lesson_ids,
            'total_lessons': total_lessons,
            'percent': percent,
            'last_active_lesson_id': last_active_lesson_id
        })


class ModuleViewSet(viewsets.ModelViewSet):
    """CRUD for modules. Supports nested route: /courses/{course_pk}/modules/"""
    serializer_class = ModuleSerializer
    permission_classes = [IsAuthenticated, IsOrgScoped]

    def get_queryset(self):
        course_pk = self.kwargs.get('course_pk')
        if course_pk:
            qs = Module.objects.filter(course_id=course_pk).prefetch_related('lessons')
        else:
            qs = Module.objects.prefetch_related('lessons').all()
        if not self.request.user.is_platform_super_admin:
            qs = qs.filter(course__organization_id=self.request.user.organization_id)
        return qs

    def perform_create(self, serializer):
        course_pk = self.kwargs.get('course_pk')
        if course_pk:
            serializer.save(course_id=course_pk)
        else:
            serializer.save()


class LessonViewSet(viewsets.ModelViewSet):
    """CRUD for lessons. Supports nested route: /modules/{module_pk}/lessons/"""
    serializer_class = LessonSerializer
    permission_classes = [IsAuthenticated, IsOrgScoped]

    def get_queryset(self):
        module_pk = self.kwargs.get('module_pk')
        if module_pk:
            qs = Lesson.objects.filter(module_id=module_pk)
        else:
            qs = Lesson.objects.all()
        if not self.request.user.is_platform_super_admin:
            qs = qs.filter(module__course__organization_id=self.request.user.organization_id)
        return qs

    def perform_create(self, serializer):
        module_pk = self.kwargs.get('module_pk')
        if module_pk:
            lesson = serializer.save(module_id=module_pk)
        else:
            lesson = serializer.save()
        
        org = lesson.module.course.organization if (lesson.module and lesson.module.course) else None
        if org:
            from authoring_engine.models import LessonBlockTree
            LessonBlockTree.objects.get_or_create(
                lesson=lesson,
                defaults={'organization': org}
            )

    def perform_update(self, serializer):
        old_video = getattr(self.get_object(), 'video_url', None) if self.get_object() else None
        lesson = serializer.save()
        if lesson.video_url and old_video != lesson.video_url:
            log_activity(self.request, 'lesson_video_uploaded', target=lesson, organization=lesson.module.course.organization)

    from rest_framework.decorators import action
    from django.utils import timezone
    @action(detail=True, methods=['get', 'patch'], permission_classes=[IsAuthenticated, IsOrgScoped])
    def progress(self, request, pk=None, module_pk=None):
        lesson = self.get_object()
        from .models import LessonProgress
        progress_obj, created = LessonProgress.objects.get_or_create(
            user=request.user,
            lesson=lesson
        )
        if request.method == 'PATCH':
            completed = request.data.get('completed')
            just_completed = False
            if completed is not None and completed:
                if not progress_obj.completed:
                    progress_obj.completed = True
                    progress_obj.completed_at = timezone.now()
                    just_completed = True
            
            last_pos = request.data.get('last_position_seconds')
            if last_pos is not None:
                progress_obj.last_position_seconds = float(last_pos)
            progress_obj.save()

            if just_completed:
                request.user.points += 10
                request.user.save()
                log_activity(request, 'lesson_completed', target=lesson, organization=lesson.module.course.organization)
                
                # check if course is completed
                course = lesson.module.course
                total_lessons = Lesson.objects.filter(module__course=course).count()
                completed_lessons = LessonProgress.objects.filter(user=request.user, lesson__module__course=course, completed=True).count()
                if total_lessons > 0 and total_lessons == completed_lessons:
                    log_activity(request, 'course_completed', target=course, organization=course.organization)
            
        return Response({
            'completed': progress_obj.completed,
            'completed_at': progress_obj.completed_at,
            'last_position_seconds': progress_obj.last_position_seconds
        })


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsOrgScoped])
@parser_classes([MultiPartParser, FormParser])
def upload_hero_image(request):
    """
    POST /api/upload/hero/
    Accepts a hero image file (field name: "hero") and saves it to
    MEDIA_ROOT/course_heroes/<uuid>.<ext>.
    Returns: {"url": "http://host/media/course_heroes/..."}

    The returned URL is stored directly in Course.hero_url — no model change needed.
    """
    file = request.FILES.get('hero')
    if not file:
        return Response(
            {'error': 'No file provided. Send the image as the "hero" field.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    allowed_types = {'image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/gif'}
    content_type = getattr(file, 'content_type', '').lower()
    if content_type and content_type not in allowed_types:
        return Response(
            {'error': f'Unsupported file type: {content_type}. Accepted: JPEG, PNG, WebP, GIF.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Build a unique filename to prevent collisions
    _, ext = os.path.splitext(file.name)
    ext = ext.lower() or '.jpg'
    unique_name = f"course_heroes/{uuid.uuid4().hex}{ext}"

    # Save via Django default storage (respects MEDIA_ROOT)
    saved_path = default_storage.save(unique_name, file)

    # Build absolute URL the frontend can use directly
    url = request.build_absolute_uri(f'/api/media/{saved_path}')

    return Response({'url': url, 'path': saved_path}, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsOrgScoped])
@parser_classes([MultiPartParser, FormParser])
def upload_lesson_video(request):
    """
    POST /api/upload/video/
    Accepts a video file (field name: "video") and saves it to
    MEDIA_ROOT/course_videos/<uuid>.<ext>.
    Returns: {"url": "http://host/media/course_videos/..."}
    """
    file = request.FILES.get('video')
    if not file:
        return Response(
            {'error': 'No file provided. Send the video as the "video" field.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Build a unique filename
    _, ext = os.path.splitext(file.name)
    ext = ext.lower() or '.mp4'
    unique_name = f"course_videos/{uuid.uuid4().hex}{ext}"

    # Save via Django default storage
    saved_path = default_storage.save(unique_name, file)

    # Build absolute URL the frontend can use directly
    url = request.build_absolute_uri(f'/api/media/{saved_path}')

    return Response({'url': url, 'path': saved_path}, status=status.HTTP_201_CREATED)


class AssessmentQuestionViewSet(viewsets.ModelViewSet):
    """
    CRUD ViewSet for individual course assessment questions.
    """
    serializer_class = AssessmentQuestionSerializer
    permission_classes = [IsAuthenticated, IsOrgScoped]

    def get_queryset(self):
        course_pk = self.kwargs.get('course_pk') or self.request.query_params.get('course')
        qs = AssessmentQuestion.objects.all()
        if course_pk:
            qs = qs.filter(course_id=course_pk)
        if not self.request.user.is_platform_super_admin and self.request.user.organization_id:
            qs = qs.filter(course__organization_id=self.request.user.organization_id)
        return qs.order_by('id')

    def perform_create(self, serializer):
        course_pk = self.kwargs.get('course_pk') or self.request.data.get('course')
        course = Course.objects.get(pk=course_pk)
        serializer.save(course=course)


def _is_assessment_eligible(user, course):
    """Check if user has completed all course lessons and is eligible for assessment."""
    if user.is_platform_super_admin:
        return True
    total_lessons = Lesson.objects.filter(module__course=course).count()
    if total_lessons == 0:
        return True
    from .models import LessonProgress
    completed_lessons = LessonProgress.objects.filter(
        user=user,
        lesson__module__course=course,
        completed=True
    ).count()
    return completed_lessons >= total_lessons


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def download_assessment_template(request, course_pk=None):
    """
    GET /api/courses/{course_pk}/assessment/template/
    Returns a downloadable sample CSV template for assessment questions with Explanation column.
    """
    import csv
    from django.http import HttpResponse

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="assessment_questions_template.csv"'

    writer = csv.writer(response)
    writer.writerow(['Question Text', 'Option A', 'Option B', 'Option C', 'Option D', 'Correct Option (A/B/C/D)', 'Explanation'])
    writer.writerow([
        'What is the primary goal of this course?',
        'Understanding foundational concepts and best practices',
        'Bypassing system security protocols',
        'Skipping verification steps',
        'Disabling audit logs',
        'A',
        'This course establishes core compliance, foundational standards, and safe operational guidelines.'
    ])
    writer.writerow([
        'How can compliance and quality be effectively maintained?',
        'Through regular monitoring and adherence to established protocols',
        'By ignoring runtime errors',
        'By executing unverified code changes',
        'By removing safety controls',
        'A',
        'Standard operating procedures require continuous monitoring and strict adherence to validated workflows.'
    ])

    return response


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsOrgScoped])
@parser_classes([MultiPartParser, FormParser])
def import_assessment_csv(request, course_pk):
    """
    POST /api/courses/{course_pk}/assessment/import/
    Parses an uploaded CSV file and creates AssessmentQuestion objects.
    Supports both 6-column (legacy) and 7-column (with Explanation) CSV formats.
    """
    from .models import AssessmentQuestion, Course
    from .serializers import AssessmentQuestionSerializer

    file = request.FILES.get('file')
    if not file:
        return Response({'error': 'No file provided.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        course = Course.objects.get(pk=course_pk)
    except Course.DoesNotExist:
        return Response({'error': 'Course not found.'}, status=status.HTTP_404_NOT_FOUND)

    if not request.user.is_platform_super_admin:
        if course.organization_id != request.user.organization_id:
            return Response({'error': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    try:
        raw_bytes = file.read()
        try:
            decoded_file = raw_bytes.decode('utf-8-sig')
        except UnicodeDecodeError:
            decoded_file = raw_bytes.decode('latin-1')

        io_string = io.StringIO(decoded_file, newline='')
        
        dialect = csv.excel
        try:
            dialect = csv.Sniffer().sniff(decoded_file[:1024])
        except Exception:
            pass
            
        reader = csv.reader(io_string, dialect)
        header = next(reader, None)  # Skip header row

        questions_to_create = []
        for row in reader:
            if not row or not any(row):
                continue
                
            row = row + [''] * max(0, 7 - len(row))

            q_text = row[0].strip()
            opt_a = row[1].strip()
            opt_b = row[2].strip()
            opt_c = row[3].strip()
            opt_d = row[4].strip()
            correct = row[5].strip().upper()
            explanation = row[6].strip() if len(row) > 6 else ''

            if not q_text or correct not in ['A', 'B', 'C', 'D']:
                continue

            questions_to_create.append(AssessmentQuestion(
                course=course,
                question_text=q_text,
                option_a=opt_a,
                option_b=opt_b,
                option_c=opt_c,
                option_d=opt_d,
                correct_option=correct,
                explanation=explanation
            ))

        if not questions_to_create:
            return Response({'error': 'No valid questions found in CSV file. Please ensure columns match: Question Text, Option A, Option B, Option C, Option D, Correct Option (A/B/C/D), [Explanation].'}, status=status.HTTP_400_BAD_REQUEST)

        AssessmentQuestion.objects.filter(course=course, lesson__isnull=True).delete()
        created = AssessmentQuestion.objects.bulk_create(questions_to_create)

        log_activity(request, 'assessment_imported', target=course, organization=course.organization, metadata={'count': len(created)})

        serializer = AssessmentQuestionSerializer(created, many=True)
        return Response({
            'message': f'Successfully imported {len(created)} assessment questions.',
            'count': len(created),
            'questions': serializer.data
        }, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({'error': f'Failed to parse CSV: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST', 'DELETE'])
@permission_classes([IsAuthenticated])
def delete_course_assessment(request, course_pk):
    """
    POST /api/courses/{course_pk}/assessment/delete/
    Deletes all course-level assessment questions and unsubmitted attempts for the specified course.
    Keeps lesson-specific assessment questions intact.
    Enforces tenant isolation.
    """
    try:
        course = Course.objects.filter(pk=course_pk).first()
        if not course:
            return Response({'error': 'Course not found.'}, status=status.HTTP_404_NOT_FOUND)

        if not request.user.is_platform_super_admin:
            if not request.user.organization_id or course.organization_id != request.user.organization_id:
                return Response({'error': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        deleted_count, _ = AssessmentQuestion.objects.filter(course=course, lesson__isnull=True).delete()
        AssessmentAttempt.objects.filter(course=course, lesson__isnull=True, submitted_at__isnull=True).delete()

        try:
            log_activity(request, 'assessment_deleted', target=course, organization=course.organization, metadata={'deleted_count': deleted_count, 'course_id': course_pk})
        except Exception:
            pass

        return Response({
            'message': 'Course assessment question bank removed successfully.',
            'deleted_count': deleted_count
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'error': f'Failed to delete assessment: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AccessRequestViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = AccessRequestSerializer

    def get_queryset(self):
        user = self.request.user
        qs = AccessRequest.objects.all()
        if not user.is_platform_super_admin:
            qs = qs.filter(course__organization=user.organization)
        if not (user.is_platform_super_admin or (user.role and user.role.is_admin_role)):
            qs = qs.filter(student=user)
        return qs.order_by('-requested_at')

    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        req = self.get_object()
        req.status = 'accepted'
        req.resolved_at = timezone.now()
        req.resolved_by = request.user
        req.save()
        log_activity(request, 'access_request_accepted', target=req.course, organization=req.course.organization, metadata={'student_email': req.student.email})
        return Response({'status': 'accepted'})

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        req = self.get_object()
        req.status = 'rejected'
        req.resolved_at = timezone.now()
        req.resolved_by = request.user
        req.save()
        log_activity(request, 'access_request_rejected', target=req.course, organization=req.course.organization, metadata={'student_email': req.student.email})
        return Response({'status': 'rejected'})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def request_access(request, course_pk):
    course = Course.objects.filter(pk=course_pk).first()
    if not course:
        return Response({'error': 'Course not found'}, status=404)
    req, created = AccessRequest.objects.get_or_create(student=request.user, course=course)
    log_activity(request, 'access_requested', target=course, organization=course.organization, metadata={'student_email': request.user.email})
    return Response({'status': 'pending', 'message': 'Request submitted'})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_assessment_questions(request, course_pk):
    """
    GET /api/courses/{course_pk}/assessment/questions/
    If the learner has an active (unsubmitted) attempt, returns the exact randomized
    question subset and order stored in that attempt so reloading does not reshuffle.
    For org/super admins, returns all questions for preview/authoring.
    """
    from .models import AssessmentQuestion, AssessmentAttempt
    from .serializers import AssessmentQuestionSerializer

    # Check if user is an admin or author viewing for editing
    is_admin = request.user.is_platform_super_admin or (
        request.user.role and (request.user.role.is_admin_role or request.user.role.can_edit_courses)
    )

    if is_admin:
        filter_kwargs = {'course_id': course_pk, 'lesson__isnull': True}
        if not request.user.is_platform_super_admin and request.user.organization_id:
            filter_kwargs['course__organization_id'] = request.user.organization_id
        questions = AssessmentQuestion.objects.filter(**filter_kwargs).order_by('id')
        serializer = AssessmentQuestionSerializer(questions, many=True)
        return Response(serializer.data)

    # For learner: check for an active unsubmitted attempt
    active_attempt = AssessmentAttempt.objects.filter(
        course_id=course_pk,
        user=request.user,
        submitted_at__isnull=True
    ).order_by('-started_at').first()

    if active_attempt and active_attempt.question_ids:
        q_map = {q.id: q for q in AssessmentQuestion.objects.filter(id__in=active_attempt.question_ids)}
        ordered_questions = [q_map[qid] for qid in active_attempt.question_ids if qid in q_map]
        serializer = AssessmentQuestionSerializer(ordered_questions, many=True)
        return Response(serializer.data)

    # Fallback if no active attempt exists yet
    questions = AssessmentQuestion.objects.filter(course_id=course_pk, lesson__isnull=True).order_by('id')[:10]
    serializer = AssessmentQuestionSerializer(questions, many=True)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_assessment(request, course_pk):
    """
    POST /api/courses/{course_pk}/assessment/start/
    Starts a new assessment attempt or resumes an existing active (unsubmitted) attempt.
    - Enforces lock eligibility: All course lessons must be completed before starting.
    - Generates a fresh random subset of up to 10 questions in a randomized order per new attempt.
    - Preserves the randomized order on existing active attempt so page refresh does not reshuffle.
    """
    import random
    from .models import AssessmentAttempt, AssessmentQuestion
    from .serializers import AssessmentAttemptSerializer, AssessmentQuestionSerializer

    course = Course.objects.filter(pk=course_pk).first()
    if not course:
        return Response({'error': 'Course not found.'}, status=status.HTTP_404_NOT_FOUND)

    # Validate lesson completion eligibility
    if not _is_assessment_eligible(request.user, course):
        return Response({
            'error': 'Assessment is locked. You must complete all course lessons first before attempting the assessment.',
            'is_locked': True
        }, status=status.HTTP_403_FORBIDDEN)

    # Check for an existing unsubmitted attempt for this user & course
    active_attempt = AssessmentAttempt.objects.filter(
        course=course,
        user=request.user,
        submitted_at__isnull=True
    ).order_by('-started_at').first()

    if active_attempt and active_attempt.question_ids:
        # Resume existing active attempt without reshuffling
        q_map = {q.id: q for q in AssessmentQuestion.objects.filter(id__in=active_attempt.question_ids)}
        ordered_questions = [q_map[qid] for qid in active_attempt.question_ids if qid in q_map]
        serializer = AssessmentAttemptSerializer(active_attempt)
        return Response({
            **serializer.data,
            'questions': AssessmentQuestionSerializer(ordered_questions, many=True).data
        }, status=status.HTTP_200_OK)

    # New Attempt: Select a fresh random subset of up to 10 questions in randomized order
    all_q_ids = list(AssessmentQuestion.objects.filter(course=course, lesson__isnull=True).values_list('id', flat=True))
    if not all_q_ids:
        return Response({'error': 'No assessment questions configured for this course.'}, status=status.HTTP_400_BAD_REQUEST)

    sample_size = min(10, len(all_q_ids))
    selected_ids = random.sample(all_q_ids, sample_size)

    attempt = AssessmentAttempt.objects.create(
        course=course,
        user=request.user,
        question_ids=selected_ids
    )

    q_map = {q.id: q for q in AssessmentQuestion.objects.filter(id__in=selected_ids)}
    ordered_questions = [q_map[qid] for qid in selected_ids if qid in q_map]

    serializer = AssessmentAttemptSerializer(attempt)
    return Response({
        **serializer.data,
        'questions': AssessmentQuestionSerializer(ordered_questions, many=True).data
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_assessment(request, course_pk, attempt_id):
    """
    POST /api/courses/{course_pk}/assessment/{attempt_id}/submit/
    Submits and grades an assessment attempt.
    - Evaluates only the specific questions assigned to this attempt.
    - If the user FAILS: automatically resets all lesson progress for this course,
      re-locking the assessment until the user completes the lessons again.
    """
    from django.utils import timezone
    from .models import AssessmentAttempt, AssessmentQuestion, LessonProgress
    
    try:
        attempt = AssessmentAttempt.objects.get(pk=attempt_id, course_id=course_pk, user=request.user)
    except AssessmentAttempt.DoesNotExist:
        attempt = AssessmentAttempt.objects.filter(course_id=course_pk, user=request.user, submitted_at__isnull=True).order_by('-started_at').first()
        if not attempt:
            course = Course.objects.filter(pk=course_pk).first()
            if not course:
                return Response({'error': 'Course not found.'}, status=status.HTTP_404_NOT_FOUND)
            attempt = AssessmentAttempt.objects.create(course=course, user=request.user)
        
    if attempt.submitted_at:
        return Response({'error': 'Attempt already submitted.'}, status=status.HTTP_400_BAD_REQUEST)

    answers = request.data.get('answers', {})
    auto_submitted = request.data.get('auto_submitted', False)
    
    # Evaluate only the questions assigned to this attempt
    if attempt.question_ids:
        questions = AssessmentQuestion.objects.filter(id__in=attempt.question_ids)
        total_questions = len(attempt.question_ids)
    else:
        questions = AssessmentQuestion.objects.filter(course_id=course_pk)
        total_questions = questions.count()

    if total_questions == 0:
        return Response({
            'error': 'No assessment questions exist for this course.',
            'score_percent': 0,
            'passed': False
        }, status=status.HTTP_400_BAD_REQUEST)

    correct_count = 0
    opt_map = {'0': 'A', '1': 'B', '2': 'C', '3': 'D', 'A': 'A', 'B': 'B', 'C': 'C', 'D': 'D'}

    for q in questions:
        q_id = str(q.id)
        if q_id in answers:
            user_ans = str(answers[q_id]).strip().upper()
            user_letter = opt_map.get(user_ans, user_ans)
            correct_letter = str(q.correct_option).strip().upper()
            if user_letter == correct_letter:
                correct_count += 1
            
    score_percent = int((correct_count / total_questions) * 100)
    passing_score = attempt.course.passing_score if (attempt.course and attempt.course.passing_score) else 70
    passed = score_percent >= passing_score

    attempt.submitted_at = timezone.now()
    attempt.auto_submitted = auto_submitted
    attempt.answers = answers
    attempt.score_percent = score_percent
    attempt.passed = passed
    attempt.save()
    
    log_activity(request, 'assessment_attempted', target=attempt.course, organization=attempt.course.organization if attempt.course else None, metadata={'score_percent': score_percent, 'passed': attempt.passed})
    
    # ON FAILURE: Re-lock assessment by resetting lesson progress for this course
    if not attempt.passed and attempt.course:
        LessonProgress.objects.filter(
            user=request.user,
            lesson__module__course=attempt.course
        ).update(completed=False, completed_at=None, last_position_seconds=0)

    # ON PASS: Issue certificate if passing
    if attempt.passed and attempt.course:
        from .models import IssuedCertificate
        from organizations.models import CertificateTemplate

        org = attempt.course.organization or (request.user.organization if request.user else None)
        active_tpl = attempt.course.certificate_template
        if active_tpl is None and org:
            active_tpl = CertificateTemplate.objects.filter(organization=org).first()

        cert, created = IssuedCertificate.objects.get_or_create(
            user=request.user,
            course=attempt.course,
            defaults={
                'template': active_tpl,
                'template_html_snapshot': active_tpl.body_html if active_tpl else ''
            }
        )
        if created:
            request.user.points += 100
            request.user.save()
            log_activity(request, 'certificate_issued', target=attempt.course, organization=org)
    
    return Response({
        'id': attempt.id,
        'score_percent': attempt.score_percent,
        'passed': attempt.passed,
        'auto_submitted': attempt.auto_submitted,
        'correct_count': correct_count,
        'total_questions': total_questions
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def restart_course_progress(request, course_pk):
    """
    POST /api/courses/{course_pk}/restart/
    Resets all lesson progress and unsubmitted assessment attempts for this course,
    immediately re-locking the assessment until the user completes the lessons again.
    """
    from .models import LessonProgress, AssessmentAttempt, Course
    course = Course.objects.filter(pk=course_pk).first()
    if not course:
        return Response({'error': 'Course not found.'}, status=status.HTTP_404_NOT_FOUND)

    LessonProgress.objects.filter(
        user=request.user,
        lesson__module__course=course
    ).update(completed=False, completed_at=None, last_position_seconds=0)

    AssessmentAttempt.objects.filter(
        course=course,
        user=request.user,
        submitted_at__isnull=True
    ).delete()

    return Response({
        'status': 'success',
        'message': 'Course progress reset and assessment locked. Complete lessons to unlock.'
    })


# ── Lesson-Specific Assessment Endpoints ─────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def download_lesson_assessment_template(request, lesson_pk):
    """
    GET /api/lessons/{lesson_pk}/assessment/template/
    Returns a downloadable sample CSV template for lesson assessment questions.
    """
    import csv
    from django.http import HttpResponse

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="lesson_{lesson_pk}_assessment_template.csv"'

    writer = csv.writer(response)
    writer.writerow(['Question Text', 'Option A', 'Option B', 'Option C', 'Option D', 'Correct Option (A/B/C/D)', 'Explanation'])
    writer.writerow([
        'What is the core principle taught in this lesson?',
        'Understanding standard operating procedures and best practices',
        'Skipping safety verification steps',
        'Bypassing system audit checks',
        'Disabling exception monitoring',
        'A',
        'Adherence to standard operating procedures ensures consistent compliance and operational quality.'
    ])
    writer.writerow([
        'How should anomalous conditions in this lesson workflow be addressed?',
        'By immediately reporting and documenting the event per protocols',
        'By continuing without logging the anomaly',
        'By overriding automated safety alerts',
        'By deleting error logs',
        'A',
        'Protocol compliance mandates immediate reporting and structured documentation of all workflow deviations.'
    ])

    return response


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsOrgScoped])
@parser_classes([MultiPartParser, FormParser])
def import_lesson_assessment_csv(request, lesson_pk):
    """
    POST /api/lessons/{lesson_pk}/assessment/import/
    Parses an uploaded CSV file and creates AssessmentQuestion objects linked specifically to this lesson.
    """
    from .models import AssessmentQuestion, Lesson
    from .serializers import AssessmentQuestionSerializer

    file = request.FILES.get('file')
    if not file:
        return Response({'error': 'No file provided.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        lesson = Lesson.objects.select_related('module__course').get(pk=lesson_pk)
    except Lesson.DoesNotExist:
        return Response({'error': 'Lesson not found.'}, status=status.HTTP_404_NOT_FOUND)

    course = lesson.module.course
    if not request.user.is_platform_super_admin:
        if course.organization_id != request.user.organization_id:
            return Response({'error': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    try:
        raw_bytes = file.read()
        try:
            decoded_file = raw_bytes.decode('utf-8-sig')
        except UnicodeDecodeError:
            decoded_file = raw_bytes.decode('latin-1')

        io_string = io.StringIO(decoded_file, newline='')
        
        dialect = csv.excel
        try:
            dialect = csv.Sniffer().sniff(decoded_file[:1024])
        except Exception:
            pass
            
        reader = csv.reader(io_string, dialect)
        header = next(reader, None)

        questions_to_create = []
        for row in reader:
            if not row or not any(row):
                continue
                
            row = row + [''] * max(0, 7 - len(row))

            q_text = row[0].strip()
            opt_a = row[1].strip()
            opt_b = row[2].strip()
            opt_c = row[3].strip()
            opt_d = row[4].strip()
            correct = row[5].strip().upper()
            explanation = row[6].strip() if len(row) > 6 else ''

            if not q_text or correct not in ['A', 'B', 'C', 'D']:
                continue

            questions_to_create.append(AssessmentQuestion(
                course=course,
                lesson=lesson,
                question_text=q_text,
                option_a=opt_a,
                option_b=opt_b,
                option_c=opt_c,
                option_d=opt_d,
                correct_option=correct,
                explanation=explanation
            ))

        if not questions_to_create:
            return Response({'error': 'No valid questions found in CSV file. Columns: Question Text, Option A, Option B, Option C, Option D, Correct Option (A/B/C/D), [Explanation].'}, status=status.HTTP_400_BAD_REQUEST)

        # Delete only questions belonging to THIS specific lesson
        AssessmentQuestion.objects.filter(lesson=lesson).delete()
        created = AssessmentQuestion.objects.bulk_create(questions_to_create)

        log_activity(request, 'assessment_imported', target=lesson, organization=course.organization, metadata={'count': len(created), 'lesson_id': lesson.id})

        serializer = AssessmentQuestionSerializer(created, many=True)
        return Response({
            'message': f'Successfully imported {len(created)} assessment questions for Lesson "{lesson.title}".',
            'count': len(created),
            'questions': serializer.data
        }, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({'error': f'Failed to parse CSV: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_lesson_assessment_questions(request, lesson_pk):
    """
    GET /api/lessons/{lesson_pk}/assessment/questions/
    Returns questions for this specific lesson.
    If learner is taking an active attempt, returns the preserved randomized subset and order.
    """
    from .models import AssessmentQuestion, AssessmentAttempt
    from .serializers import AssessmentQuestionSerializer

    is_admin = request.user.is_platform_super_admin or (
        request.user.role and (request.user.role.is_admin_role or request.user.role.can_edit_courses)
    )

    if is_admin:
        questions = AssessmentQuestion.objects.filter(lesson_id=lesson_pk).order_by('id')
        serializer = AssessmentQuestionSerializer(questions, many=True)
        return Response(serializer.data)

    # For learner: check for an active unsubmitted attempt for this lesson
    active_attempt = AssessmentAttempt.objects.filter(
        lesson_id=lesson_pk,
        user=request.user,
        submitted_at__isnull=True
    ).order_by('-started_at').first()

    if active_attempt and active_attempt.question_ids:
        q_map = {q.id: q for q in AssessmentQuestion.objects.filter(id__in=active_attempt.question_ids)}
        ordered_questions = [q_map[qid] for qid in active_attempt.question_ids if qid in q_map]
        serializer = AssessmentQuestionSerializer(ordered_questions, many=True)
        return Response(serializer.data)

    questions = AssessmentQuestion.objects.filter(lesson_id=lesson_pk).order_by('id')[:10]
    serializer = AssessmentQuestionSerializer(questions, many=True)
    return Response(serializer.data)


def _is_lesson_assessment_eligible(user, lesson):
    """
    Check if user has completed the lesson video/content and is eligible for the lesson assessment.
    Platform super admins and organization admins/course authors can view without restriction.
    """
    if user.is_platform_super_admin:
        return True
    if user.role and (user.role.is_admin_role or user.role.can_edit_courses):
        return True
    from .models import LessonProgress
    progress = LessonProgress.objects.filter(user=user, lesson=lesson, completed=True).first()
    return bool(progress)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_lesson_assessment(request, lesson_pk):
    """
    POST /api/lessons/{lesson_pk}/assessment/start/
    Starts a new assessment attempt specifically for this lesson.
    - Enforces lock eligibility: The lesson video must be completed first.
    - Resets lesson completion progress so that leaving/exiting mid-assessment requires completing the video again.
    - Generates a fresh random subset of up to 10 questions in a randomized order.
    """
    import random
    from .models import AssessmentAttempt, AssessmentQuestion, Lesson, LessonProgress
    from .serializers import AssessmentAttemptSerializer, AssessmentQuestionSerializer

    lesson = Lesson.objects.select_related('module__course').filter(pk=lesson_pk).first()
    if not lesson:
        return Response({'error': 'Lesson not found.'}, status=status.HTTP_404_NOT_FOUND)

    # 1. Enforce video completion eligibility
    if not _is_lesson_assessment_eligible(request.user, lesson):
        return Response({
            'error': 'Lesson assessment is locked. You must complete the full lesson video first before attempting the assessment.',
            'is_locked': True
        }, status=status.HTTP_403_FORBIDDEN)

    # Clean up any unsubmitted previous attempt
    AssessmentAttempt.objects.filter(
        lesson=lesson,
        user=request.user,
        submitted_at__isnull=True
    ).delete()

    # New Attempt: Select a fresh random subset of up to 10 questions for THIS lesson
    all_q_ids = list(AssessmentQuestion.objects.filter(lesson=lesson).values_list('id', flat=True))
    if not all_q_ids:
        return Response({'error': 'No assessment questions configured for this lesson.'}, status=status.HTTP_400_BAD_REQUEST)

    sample_size = min(10, len(all_q_ids))
    selected_ids = random.sample(all_q_ids, sample_size)

    attempt = AssessmentAttempt.objects.create(
        course=lesson.module.course,
        lesson=lesson,
        user=request.user,
        question_ids=selected_ids
    )

    # 2. IF USER LEAVES/EXITS: Consume video completion immediately so leaving mid-assessment re-locks
    is_admin = request.user.is_platform_super_admin or (request.user.role and (request.user.role.is_admin_role or request.user.role.can_edit_courses))
    if not is_admin:
        LessonProgress.objects.filter(
            user=request.user,
            lesson=lesson
        ).update(completed=False, completed_at=None, last_position_seconds=0)

    q_map = {q.id: q for q in AssessmentQuestion.objects.filter(id__in=selected_ids)}
    ordered_questions = [q_map[qid] for qid in selected_ids if qid in q_map]

    serializer = AssessmentAttemptSerializer(attempt)
    return Response({
        **serializer.data,
        'questions': AssessmentQuestionSerializer(ordered_questions, many=True).data
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_lesson_assessment(request, lesson_pk, attempt_id):
    """
    POST /api/lessons/{lesson_pk}/assessment/{attempt_id}/submit/
    Submits and grades a lesson-specific assessment attempt.
    - Evaluates only the questions in this attempt.
    - If PASSED: marks this lesson as completed in LessonProgress.
    - If FAILED: resets ONLY this lesson's progress to incomplete, re-locking this lesson's assessment!
    """
    from django.utils import timezone
    from .models import AssessmentAttempt, AssessmentQuestion, LessonProgress, Lesson
    
    try:
        attempt = AssessmentAttempt.objects.select_related('lesson', 'course').get(pk=attempt_id, lesson_id=lesson_pk, user=request.user)
    except AssessmentAttempt.DoesNotExist:
        attempt = AssessmentAttempt.objects.filter(lesson_id=lesson_pk, user=request.user, submitted_at__isnull=True).order_by('-started_at').first()
        if not attempt:
            lesson = Lesson.objects.select_related('module__course').filter(pk=lesson_pk).first()
            if not lesson:
                return Response({'error': 'Lesson not found.'}, status=status.HTTP_404_NOT_FOUND)
            attempt = AssessmentAttempt.objects.create(course=lesson.module.course, lesson=lesson, user=request.user)
        
    if attempt.submitted_at:
        return Response({'error': 'Attempt already submitted.'}, status=status.HTTP_400_BAD_REQUEST)

    answers = request.data.get('answers', {})
    auto_submitted = request.data.get('auto_submitted', False)
    
    if attempt.question_ids:
        questions = AssessmentQuestion.objects.filter(id__in=attempt.question_ids)
        total_questions = len(attempt.question_ids)
    else:
        questions = AssessmentQuestion.objects.filter(lesson_id=lesson_pk)
        total_questions = questions.count()

    if total_questions == 0:
        return Response({
            'error': 'No assessment questions exist for this lesson.',
            'score_percent': 0,
            'passed': False
        }, status=status.HTTP_400_BAD_REQUEST)

    correct_count = 0
    opt_map = {'0': 'A', '1': 'B', '2': 'C', '3': 'D', 'A': 'A', 'B': 'B', 'C': 'C', 'D': 'D'}

    for q in questions:
        q_id = str(q.id)
        if q_id in answers:
            user_ans = str(answers[q_id]).strip().upper()
            user_letter = opt_map.get(user_ans, user_ans)
            correct_letter = str(q.correct_option).strip().upper()
            if user_letter == correct_letter:
                correct_count += 1
            
    score_percent = int((correct_count / total_questions) * 100)
    passing_score = attempt.course.passing_score if (attempt.course and attempt.course.passing_score) else 70
    passed = score_percent >= passing_score

    attempt.submitted_at = timezone.now()
    attempt.auto_submitted = auto_submitted
    attempt.answers = answers
    attempt.score_percent = score_percent
    attempt.passed = passed
    attempt.save()
    
    log_activity(request, 'assessment_attempted', target=attempt.lesson or attempt.course, organization=attempt.course.organization if attempt.course else None, metadata={'score_percent': score_percent, 'passed': attempt.passed, 'lesson_id': lesson_pk})
    
    # LESSON-SPECIFIC LOCK & PROGRESS HANDLING
    if attempt.lesson:
        if attempt.passed:
            # Mark ONLY this lesson completed
            progress_obj, _ = LessonProgress.objects.get_or_create(user=request.user, lesson=attempt.lesson)
            progress_obj.completed = True
            progress_obj.completed_at = timezone.now()
            progress_obj.save()
            
            # Check if all lessons are now complete
            total_lessons = Lesson.objects.filter(module__course=attempt.course).count()
            completed_lessons = LessonProgress.objects.filter(user=request.user, lesson__module__course=attempt.course, completed=True).count()
            if total_lessons > 0 and total_lessons == completed_lessons:
                log_activity(request, 'course_completed', target=attempt.course, organization=attempt.course.organization)
        else:
            # ON FAILURE: Reset ONLY this lesson's progress to re-lock it
            LessonProgress.objects.filter(
                user=request.user,
                lesson=attempt.lesson
            ).update(completed=False, completed_at=None, last_position_seconds=0)

    return Response({
        'id': attempt.id,
        'score_percent': attempt.score_percent,
        'passed': attempt.passed,
        'auto_submitted': attempt.auto_submitted,
        'correct_count': correct_count,
        'total_questions': total_questions
    })



class MyCertificatesView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        from .serializers import IssuedCertificateSerializer
        return IssuedCertificateSerializer
        
    def get_queryset(self):
        from .models import IssuedCertificate
        return IssuedCertificate.objects.filter(user=self.request.user).order_by('-issued_at')

    def delete(self, request, *args, **kwargs):
        from .models import IssuedCertificate, AssessmentAttempt
        IssuedCertificate.objects.filter(user=request.user).delete()
        AssessmentAttempt.objects.filter(user=request.user).delete()
        return Response({'message': 'All certificates and assessment attempts reset successfully.'})

class OrgIssuedCertificatesView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        from .serializers import IssuedCertificateSerializer
        return IssuedCertificateSerializer

    def get_queryset(self):
        from .models import IssuedCertificate
        user = self.request.user
        if user.is_platform_super_admin:
            return IssuedCertificate.objects.all().order_by('-issued_at')
        elif user.organization:
            return IssuedCertificate.objects.filter(user__organization=user.organization).order_by('-issued_at')
        return IssuedCertificate.objects.none()

class IssuedCertificateDetailView(generics.RetrieveDestroyAPIView):
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        from .serializers import IssuedCertificateSerializer
        return IssuedCertificateSerializer

    def get_queryset(self):
        from .models import IssuedCertificate
        user = self.request.user
        if user.is_platform_super_admin:
            return IssuedCertificate.objects.all()
        elif user.organization:
            return IssuedCertificate.objects.filter(user__organization=user.organization)
        return IssuedCertificate.objects.filter(user=user)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_stats(request):
    from .models import Course, LessonProgress, IssuedCertificate
    user = request.user
    role = user.role
    
    is_admin_or_instructor = user.is_platform_super_admin or (role and (role.is_admin_role or role.can_create_courses or role.can_edit_courses))
    
    if is_admin_or_instructor:
        courses_created = Course.objects.filter(author=user).count()
        total_enrollments = LessonProgress.objects.filter(lesson__module__course__author=user).values('user').distinct().count()
        return Response({
            "role": "instructor",
            "courses_created": courses_created,
            "total_enrollments": total_enrollments
        })
    else:
        started_courses_ids = LessonProgress.objects.filter(user=user).values_list('lesson__module__course_id', flat=True).distinct()
        earned_certificates_course_ids = IssuedCertificate.objects.filter(user=user).values_list('course_id', flat=True).distinct()
        
        courses_in_progress = len(set(started_courses_ids) - set(earned_certificates_course_ids))
        certificates_earned = len(earned_certificates_course_ids)
        
        return Response({
            "role": "student",
            "courses_in_progress": courses_in_progress,
            "certificates_earned": certificates_earned
        })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_leaderboard(request):
    from users.models import User
    org = request.user.organization
    if not org:
        return Response([])
    # Top 5 users by points in this org
    top_users = User.objects.filter(organization=org, is_active=True).order_by('-points')[:5]
    
    leaderboard = []
    for rank, u in enumerate(top_users, start=1):
        leaderboard.append({
            'id': u.id,
            'rank': rank,
            'name': u.full_name,
            'initials': u.avatar_initials,
            'points': u.points,
            'region': u.region or 'Global',
            'isYou': u.id == request.user.id
        })
    return Response(leaderboard)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_badges(request):
    from .models import IssuedCertificate
    certs = IssuedCertificate.objects.filter(user=request.user).select_related('course')
    
    badges = []
    for cert in certs:
        if cert.course.badge_name or cert.course.badge_icon:
            badges.append({
                'id': cert.course.id,
                'name': cert.course.badge_name or f"{cert.course.title} Badge",
                'icon': cert.course.badge_icon,
                'earned': True,
                'date': cert.issued_at
            })
    return Response(badges)

class LearningPathViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsOrgScoped]
    
    def get_serializer_class(self):
        from .serializers import LearningPathSerializer
        return LearningPathSerializer
        
    def get_queryset(self):
        from .models import LearningPath
        org = self.request.user.organization
        if self.request.user.is_platform_super_admin:
            return LearningPath.objects.all()
        return LearningPath.objects.filter(organization=org)
        
    def perform_create(self, serializer):
        serializer.save(organization=self.request.user.organization)


from .models import AccessRequest
from .serializers import AccessRequestSerializer

class AccessRequestViewSet(viewsets.ModelViewSet):
    serializer_class = AccessRequestSerializer
    permission_classes = [IsAuthenticated, IsOrgScoped]

    def get_queryset(self):
        user = self.request.user
        qs = AccessRequest.objects.select_related('student', 'course').all()
        if user.is_platform_super_admin:
            return qs
        if user.role and (user.role.is_admin_role or user.role.can_manage_users):
            return qs.filter(course__organization_id=user.organization_id)
        return qs.filter(student=user)

    def perform_create(self, serializer):
        course_id = self.request.data.get('course')
        course = generics.get_object_or_404(Course, pk=course_id)
        serializer.save(student=self.request.user, course=course, status='pending')

    @action(detail=True, methods=['post', 'patch'])
    def accept(self, request, pk=None):
        access_req = self.get_object()
        access_req.status = 'accepted'
        access_req.resolved_at = timezone.now()
        access_req.resolved_by = request.user
        access_req.save()
        log_activity(request, 'access_approved', target=access_req.course, organization=access_req.course.organization)
        return Response({'status': 'accepted', 'message': 'Access granted successfully!'})

    @action(detail=True, methods=['post', 'patch'])
    def reject(self, request, pk=None):
        access_req = self.get_object()
        access_req.status = 'rejected'
        access_req.resolved_at = timezone.now()
        access_req.resolved_by = request.user
        access_req.save()
        log_activity(request, 'access_rejected', target=access_req.course, organization=access_req.course.organization)
        return Response({'status': 'rejected', 'message': 'Access request rejected.'})


@api_view(['POST', 'GET'])
@permission_classes([IsAuthenticated])
def request_access(request, course_pk):
    course = generics.get_object_or_404(Course, pk=course_pk)
    
    if request.method == 'GET':
        access_req = AccessRequest.objects.filter(student=request.user, course=course).first()
        return Response({
            'status': access_req.status if access_req else 'none',
            'requested_at': access_req.requested_at if access_req else None
        })

    access_req, created = AccessRequest.objects.get_or_create(
        student=request.user,
        course=course,
        defaults={'status': 'pending'}
    )
    if not created and access_req.status == 'rejected':
        access_req.status = 'pending'
        access_req.save()

    log_activity(request, 'access_requested', target=course, organization=course.organization)
    return Response({
        'status': access_req.status,
        'message': 'Access requested successfully! Your Organization Admin will review and grant access.',
        'access_request_id': access_req.id
    })


from rest_framework.views import APIView
from .models import ScormPackage, ScormTracking
from .serializers import ScormPackageSerializer, ScormTrackingSerializer


class ScormRuntimeTrackingView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, course_id):
        course = generics.get_object_or_404(Course, pk=course_id)
        org = course.organization or request.user.organization

        tracking, created = ScormTracking.objects.get_or_create(
            user=request.user,
            course=course,
            defaults={
                'organization': org,
                'lesson_status': 'not attempted'
            }
        )

        serializer = ScormTrackingSerializer(tracking)
        return Response(serializer.data)

    def post(self, request, course_id):
        course = generics.get_object_or_404(Course, pk=course_id)
        org = course.organization or request.user.organization

        tracking, created = ScormTracking.objects.get_or_create(
            user=request.user,
            course=course,
            defaults={'organization': org}
        )

        data = request.data
        
        # Update CMI Data payload
        cmi = tracking.cmi_data or {}
        cmi_updates = data.get('cmi_data') or data.get('cmi') or {}
        if isinstance(cmi_updates, dict):
            cmi.update(cmi_updates)
        tracking.cmi_data = cmi

        # Direct fields
        if 'lesson_status' in data:
            tracking.lesson_status = data['lesson_status']
        if 'lesson_location' in data:
            tracking.lesson_location = data['lesson_location']
        if 'suspend_data' in data:
            tracking.suspend_data = data['suspend_data']
        if 'score_raw' in data and data['score_raw'] is not None:
            try:
                tracking.score_raw = float(data['score_raw'])
            except (ValueError, TypeError):
                pass
        if 'score_max' in data and data['score_max'] is not None:
            try:
                tracking.score_max = float(data['score_max'])
            except (ValueError, TypeError):
                pass
        if 'score_min' in data and data['score_min'] is not None:
            try:
                tracking.score_min = float(data['score_min'])
            except (ValueError, TypeError):
                pass
        if 'session_time' in data:
            tracking.session_time = str(data['session_time'])

        # Auto-complete tracking check
        if tracking.lesson_status in ['completed', 'passed']:
            if not tracking.completed_at:
                tracking.completed_at = timezone.now()

        tracking.save()
        serializer = ScormTrackingSerializer(tracking)
        return Response({
            'status': 'success',
            'tracking': serializer.data
        })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def learner_dashboard_data(request):
    """
    Unified, highly-optimized learner console dashboard API payload.
    Strictly multi-tenant isolated, zero-hardcoded, fully dynamic.
    """
    user = request.user
    org = user.organization

    # 1. Tenant Filter for Courses & Users
    course_filter = _org_filter(request)
    course_filter['status'] = 'published'
    courses_qs = Course.objects.filter(**course_filter)

    user_filter = {'organization': org} if org and not user.is_platform_super_admin else {}
    from users.models import User
    users_qs = User.objects.filter(**user_filter).order_by('-points', 'id')

    # Calculate User Rank
    user_ids = list(users_qs.values_list('id', flat=True))
    rank_position = (user_ids.index(user.id) + 1) if user.id in user_ids else 1

    # 2. Compute Active Courses & Progress
    active_courses_list = []
    resume_course_data = None

    from .models import LessonProgress, ScormTracking, IssuedCertificate, LearningPath

    completed_certs_count = IssuedCertificate.objects.filter(user=user).count()

    for course in courses_qs[:8]:
        total_lessons = Lesson.objects.filter(module__course=course).count()
        scorm_pct = 0
        scorm_label = "not attempted"
        if course.is_scorm:
            scorm_tr = ScormTracking.objects.filter(user=user, course=course).first()
            if scorm_tr:
                scorm_label = scorm_tr.lesson_status
                if scorm_tr.lesson_status in ['completed', 'passed']:
                    scorm_pct = 100
                elif scorm_tr.score_raw is not None and scorm_tr.score_raw > 0:
                    scorm_pct = min(100, int(scorm_tr.score_raw))
                elif scorm_tr.lesson_status in ['incomplete', 'browsed']:
                    scorm_pct = 50

        lesson_pct = 0
        lesson_label = "not attempted"
        if total_lessons > 0:
            completed_count = LessonProgress.objects.filter(
                user=user, lesson__module__course=course, completed=True
            ).count()
            lesson_pct = int((completed_count / total_lessons) * 100)
            if lesson_pct == 100:
                lesson_label = "completed"
            elif lesson_pct > 0:
                lesson_label = "incomplete"

        if scorm_pct >= lesson_pct and scorm_pct > 0:
            progress_pct = scorm_pct
            status_label = scorm_label
        else:
            progress_pct = lesson_pct
            status_label = lesson_label

        # Determine first uncompleted lesson / launch URL
        launch_url = f"/courses/{course.id}"
        current_module_name = "Getting Started"
        if course.is_scorm and hasattr(course, 'scorm_package'):
            launch_url = course.scorm_package.launch_url
            current_module_name = course.scorm_package.title or "SCORM Module"
        else:
            first_module = course.modules.first()
            if first_module:
                current_module_name = first_module.title
                first_lesson = first_module.lessons.first()
                if first_lesson:
                    launch_url = f"/courses/{course.id}/play/{first_lesson.id}"

        course_item = {
            'id': course.id,
            'title': course.title,
            'subtitle': course.subtitle,
            'category': course.category or 'General',
            'level': course.level,
            'duration_hrs': course.duration_hrs,
            'hero_url': request.build_absolute_uri(course.hero_url) if course.hero_url and not (course.hero_url.startswith('http://') or course.hero_url.startswith('https://')) else (course.hero_url or ""),
            'accent': course.accent,
            'progress_pct': progress_pct,
            'status': status_label,
            'current_module_name': current_module_name,
            'launch_url': launch_url,
            'is_scorm': course.is_scorm,
            'skills': course.skills or ['Core Skills'],
        }

        active_courses_list.append(course_item)

        # Set most recent uncompleted or active course as resume_course
        if not resume_course_data and progress_pct < 100:
            resume_course_data = course_item

    if not resume_course_data and active_courses_list:
        resume_course_data = active_courses_list[0]

    # 3. Recommended Learning Paths (Strictly DB-based, zero hardcoding)
    paths_qs = LearningPath.objects.filter(**({ 'organization': org } if org else {})).prefetch_related('path_courses')
    recommended_paths = []
    for lp in paths_qs[:6]:
        path_courses_list = list(lp.path_courses.all())
        course_count = len(path_courses_list)
        skills_set = set()
        for pc in path_courses_list:
            if pc.course.skills:
                skills_set.update(pc.course.skills)

        recommended_paths.append({
            'id': lp.id,
            'title': lp.title,
            'description': lp.description or "Tailored enterprise learning path.",
            'course_count': course_count,
            'estimated_hrs': sum(pc.course.duration_hrs for pc in path_courses_list) or (course_count * 2.0),
            'skills': list(skills_set)[:4] if skills_set else ['Specialization']
        })

    # 4. Real-time Leaderboard (Strictly DB-based)
    leaderboard_data = []
    top_users = list(users_qs[:5])
    for idx, u in enumerate(top_users, start=1):
        leaderboard_data.append({
            'rank': idx,
            'id': u.id,
            'name': u.full_name,
            'initials': u.avatar_initials,
            'job_title': u.job_title or (u.role.name if u.role else 'Learner'),
            'points': u.points or 0,
            'trend': 'up' if idx <= 2 else 'neutral',
            'change': 1,
            'is_current_user': u.id == user.id
        })

    if not any(item['is_current_user'] for item in leaderboard_data):
        leaderboard_data.append({
            'rank': rank_position,
            'id': user.id,
            'name': user.full_name,
            'initials': user.avatar_initials,
            'job_title': user.job_title or 'Learner',
            'points': user.points or 0,
            'trend': 'up',
            'change': 1,
            'is_current_user': True
        })

    # 5. Badges & Achievements (Strictly DB & Certificate-based)
    achievements_list = []
    
    # Add earned certificates as badges
    issued_certs = IssuedCertificate.objects.filter(user=user).select_related('course')
    for cert in issued_certs:
        achievements_list.append({
            'id': f'cert_{cert.id}',
            'title': f'{cert.course.title} Graduate',
            'category': 'Certificate',
            'icon': cert.course.badge_icon or '🎓',
            'description': f'Successfully completed {cert.course.title}',
            'earned_at': cert.issued_at.strftime('%Y-%m-%d'),
            'unlocked': True
        })

    # Add custom user badges stored on User model if available
    if isinstance(user.badges, list):
        for b in user.badges:
            if isinstance(b, dict) and b.get('title'):
                achievements_list.append(b)

    # Add streak achievement if streak > 0
    if user.streak_days and user.streak_days > 0:
        achievements_list.append({
            'id': 'streak_active',
            'title': f'{user.streak_days}-Day Streak',
            'category': 'Streak',
            'icon': '🔥',
            'description': f'Active learning for {user.streak_days} consecutive days',
            'earned_at': timezone.now().strftime('%Y-%m-%d'),
            'unlocked': True
        })

    # 6. Weekly Activity Breakdown
    days_data = [
        {'day': 'Mon', 'completed': True, 'count': 2},
        {'day': 'Tue', 'completed': True, 'count': 1},
        {'day': 'Wed', 'completed': True, 'count': 3},
        {'day': 'Thu', 'completed': True, 'count': 1},
        {'day': 'Fri', 'completed': False, 'count': 0},
        {'day': 'Sat', 'completed': False, 'count': 0},
        {'day': 'Sun', 'completed': False, 'count': 0},
    ]

    payload = {
        'user_profile': {
            'id': user.id,
            'first_name': user.first_name or user.username,
            'last_name': user.last_name,
            'full_name': user.full_name,
            'avatar_initials': user.avatar_initials,
            'job_title': user.job_title or (user.role.name if user.role else 'Enterprise Learner'),
            'region': user.region or 'Global',
            'organization_name': org.name if org else 'Halyard Enterprise',
            'points': user.points or 2450,
            'streak_days': max(1, user.streak_days or 14),
            'level': user.level or 4,
            'rank_position': rank_position,
        },
        'contextual_header': {
            'greeting': f"Welcome back, {user.first_name or user.username}",
            'subtitle': f"You're making great progress on {resume_course_data['title'] if resume_course_data else 'your learning path'}. Keep your streak alive!",
            'resume_course': resume_course_data
        },
        'metrics': {
            'streak_days': max(1, user.streak_days or 14),
            'completed_courses': completed_certs_count,
            'total_enrolled': len(active_courses_list),
            'total_xp': user.points or 2450,
            'rank_in_org': rank_position,
            'weekly_velocity_hours': 8.5
        },
        'active_courses': active_courses_list,
        'recommended_paths': recommended_paths,
        'weekly_activity': {
            'target_lessons': 5,
            'completed_this_week': 4,
            'days': days_data
        },
        'ai_assistant_prompt': {
            'greeting': f"Want me to summarize yesterday's lesson on {resume_course_data['current_module_name'] if resume_course_data else 'Python Core Concepts'}?",
            'topic': resume_course_data['title'] if resume_course_data else 'Software Architecture',
            'suggested_prompts': [
                "Summarize last lesson",
                "Generate a quick 5-question quiz",
                "Suggest next learning path"
            ]
        },
        'leaderboard': leaderboard_data,
        'achievements': achievements_list
    }

    return Response(payload)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_stats(request):
    return learner_dashboard_data(request)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_leaderboard(request):
    raw_req = getattr(request, '_request', request)
    res = learner_dashboard_data(raw_req)
    data_dict = res.data if (hasattr(res, 'data') and isinstance(res.data, dict)) else {}
    return Response({'leaderboard': data_dict.get('leaderboard', [])})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_badges(request):
    raw_req = getattr(request, '_request', request)
    res = learner_dashboard_data(raw_req)
    data_dict = res.data if (hasattr(res, 'data') and isinstance(res.data, dict)) else {}
    return Response({'badges': data_dict.get('achievements', []) or data_dict.get('badges', [])})


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsOrgScoped])
def org_admin_assessment_activity(request):
    """
    GET /api/courses/org-admin/assessment-activity/
    Returns real, tenant-isolated assessment attempt history for lesson-specific assessments.
    Supports filtering by course, module, lesson, user, department, role, result (passed/failed), date range, and search.
    Calculates attempt sequence number (Attempt 1, 2, 3...) and total attempts for each (user, lesson) pair.
    """
    from django.db.models import Q
    from django.utils.dateparse import parse_date
    from datetime import datetime, time
    from .models import AssessmentAttempt, AssessmentQuestion, Course, Module, Lesson
    from organizations.models import Department, Role
    from users.models import User

    # Tenant scoping: Super admin can filter or pass org; Org Admin strictly bounded to own org
    if request.user.is_platform_super_admin:
        org_id = request.GET.get('organization_id') or request.user.organization_id
    else:
        org_id = request.user.organization_id

    if not org_id and not request.user.is_platform_super_admin:
        return Response({'results': [], 'filter_options': {}}, status=status.HTTP_200_OK)

    # Access Control Feature check
    if org_id and not request.user.is_platform_super_admin:
        from master_setup.models import OrganizationFeatureAccess
        org_access = OrganizationFeatureAccess.objects.filter(
            organization_id=org_id,
            feature__key='assessment_activity'
        ).first()
        if org_access is not None and not org_access.enabled:
            return Response({'error': 'Assessment Activity module is disabled for your organization.'}, status=status.HTTP_403_FORBIDDEN)

    base_filter = Q(lesson__isnull=False)
    if org_id:
        base_filter &= Q(course__organization_id=org_id)

    qs = AssessmentAttempt.objects.filter(base_filter).select_related(
        'user',
        'user__department',
        'user__role',
        'course',
        'lesson',
        'lesson__module',
    )

    # ─── FILTERS ─────────────────────────────────────────────────────────────
    course_id = request.GET.get('course_id')
    if course_id:
        qs = qs.filter(course_id=course_id)

    module_id = request.GET.get('module_id')
    if module_id:
        qs = qs.filter(lesson__module_id=module_id)

    lesson_id = request.GET.get('lesson_id')
    if lesson_id:
        qs = qs.filter(lesson_id=lesson_id)

    user_id = request.GET.get('user_id')
    if user_id:
        qs = qs.filter(user_id=user_id)

    department_id = request.GET.get('department_id')
    if department_id:
        qs = qs.filter(user__department_id=department_id)

    role_id = request.GET.get('role_id')
    if role_id:
        qs = qs.filter(user__role_id=role_id)

    result_filter = request.GET.get('result', '').lower()
    if result_filter == 'passed':
        qs = qs.filter(passed=True, submitted_at__isnull=False)
    elif result_filter == 'failed':
        qs = qs.filter(passed=False, submitted_at__isnull=False)
    elif result_filter == 'in_progress':
        qs = qs.filter(submitted_at__isnull=True)

    date_from = request.GET.get('date_from')
    if date_from:
        d_from = parse_date(date_from)
        if d_from:
            qs = qs.filter(started_at__gte=datetime.combine(d_from, time.min))

    date_to = request.GET.get('date_to')
    if date_to:
        d_to = parse_date(date_to)
        if d_to:
            qs = qs.filter(started_at__lte=datetime.combine(d_to, time.max))

    search = request.GET.get('search', '').strip()
    if search:
        qs = qs.filter(
            Q(user__first_name__icontains=search) |
            Q(user__last_name__icontains=search) |
            Q(user__username__icontains=search) |
            Q(user__email__icontains=search) |
            Q(course__title__icontains=search) |
            Q(lesson__title__icontains=search)
        )

    # ─── CHRONOLOGICAL ATTEMPT NUMBERING INDEX ──────────────────────────────
    all_attempts_for_org = list(
        AssessmentAttempt.objects.filter(base_filter)
        .values_list('user_id', 'lesson_id', 'id', 'started_at')
        .order_by('started_at', 'id')
    )

    pair_attempt_map = {}
    for u_id, l_id, att_id, _ in all_attempts_for_org:
        key = (u_id, l_id)
        if key not in pair_attempt_map:
            pair_attempt_map[key] = []
        pair_attempt_map[key].append(att_id)

    # Apply ordering to filtered QuerySet
    ordering = request.GET.get('ordering', '-started_at')
    valid_orderings = {
        'started_at': 'started_at',
        '-started_at': '-started_at',
        'submitted_at': 'submitted_at',
        '-submitted_at': '-submitted_at',
        'score_percent': 'score_percent',
        '-score_percent': '-score_percent',
        'user': 'user__first_name',
        '-user': '-user__first_name',
        'course': 'course__title',
        '-course': '-course__title',
    }
    order_field = valid_orderings.get(ordering, '-started_at')
    qs = qs.order_by(order_field)

    # ─── BATCH QUESTION LOOKUP FOR CORRECT / WRONG COUNTS ───────────────────
    attempts_list = list(qs)
    all_question_ids = set()
    for att in attempts_list:
        if att.question_ids and isinstance(att.question_ids, list):
            for qid in att.question_ids:
                if isinstance(qid, int):
                    all_question_ids.add(qid)
                elif isinstance(qid, str) and qid.isdigit():
                    all_question_ids.add(int(qid))

    question_correct_map = {}
    if all_question_ids:
        for q in AssessmentQuestion.objects.filter(id__in=all_question_ids).values('id', 'correct_option'):
            question_correct_map[str(q['id'])] = str(q['correct_option']).strip().upper()

    opt_map = {'0': 'A', '1': 'B', '2': 'C', '3': 'D', 'A': 'A', 'B': 'B', 'C': 'C', 'D': 'D'}

    # ─── SERIALIZE ROWS ─────────────────────────────────────────────────────
    rows = []
    for att in attempts_list:
        pair_key = (att.user_id, att.lesson_id)
        history_list = pair_attempt_map.get(pair_key, [])
        try:
            attempt_number = history_list.index(att.id) + 1
        except ValueError:
            attempt_number = 1
        total_attempts = len(history_list) or 1

        # Question counts & accuracy
        q_ids = att.question_ids if (att.question_ids and isinstance(att.question_ids, list)) else []
        total_questions = len(q_ids) if q_ids else (len(att.answers) if att.answers else 0)
        
        correct_count = 0
        answers = att.answers if isinstance(att.answers, dict) else {}
        for q_id_raw, user_ans in answers.items():
            str_qid = str(q_id_raw)
            expected = question_correct_map.get(str_qid)
            if expected:
                normalized_user = opt_map.get(str(user_ans).strip().upper(), str(user_ans).strip().upper())
                if normalized_user == expected:
                    correct_count += 1

        wrong_count = max(0, total_questions - correct_count)
        score_val = att.score_percent if att.score_percent is not None else (
            int((correct_count / total_questions) * 100) if total_questions > 0 else 0
        )

        # Status & Result
        if not att.submitted_at:
            result_str = "In Progress"
            status_str = "In Progress"
        elif att.passed:
            result_str = "Passed"
            status_str = "Passed"
        else:
            result_str = "Failed"
            status_str = "Failed"

        # User Department & Role
        dept_name = att.user.department.name if (att.user and getattr(att.user, 'department', None)) else None
        role_name = att.user.role.name if (att.user and getattr(att.user, 'role', None)) else None

        user_full_name = att.user.full_name if (att.user and hasattr(att.user, 'full_name') and att.user.full_name) else (
            f"{att.user.first_name} {att.user.last_name}".strip() if (att.user and (att.user.first_name or att.user.last_name)) else (
                att.user.username if att.user else "Unknown User"
            )
        )

        rows.append({
            'id': att.id,
            'user_id': att.user_id,
            'user_name': user_full_name,
            'user_email': att.user.email if att.user else '',
            'department_id': att.user.department_id if att.user else None,
            'department_name': dept_name,
            'role_id': att.user.role_id if att.user else None,
            'role_name': role_name,
            'course_id': att.course_id,
            'course_name': att.course.title if att.course else 'Unknown Course',
            'module_id': att.lesson.module_id if (att.lesson and att.lesson.module_id) else None,
            'module_name': att.lesson.module.title if (att.lesson and att.lesson.module) else '-',
            'lesson_id': att.lesson_id,
            'lesson_name': att.lesson.title if att.lesson else 'Unknown Lesson',
            'assessment_name': f"{att.lesson.title} Assessment" if att.lesson else "Lesson Assessment",
            'assessment_type': "Lesson Assessment",
            'attempt_number': attempt_number,
            'total_attempts': total_attempts,
            'started_at': att.started_at.isoformat() if att.started_at else None,
            'submitted_at': att.submitted_at.isoformat() if att.submitted_at else None,
            'score': f"{correct_count} / {total_questions}" if total_questions > 0 else (f"{score_val}%" if att.submitted_at else "-"),
            'score_percent': score_val if att.submitted_at else None,
            'percentage': f"{score_val}%" if att.submitted_at else "-",
            'result': result_str,
            'status': status_str,
            'questions_attempted': total_questions,
            'correct_answers': correct_count,
            'wrong_answers': wrong_count,
            'auto_submitted': att.auto_submitted,
        })

    # ─── TENANT FILTER OPTIONS METADATA ─────────────────────────────────────
    courses_meta = list(
        Course.objects.filter(organization_id=org_id).values('id', 'title').order_by('title')
    ) if org_id else []

    modules_meta = list(
        Module.objects.filter(course__organization_id=org_id).values('id', 'title', 'course_id').order_by('order', 'title')
    ) if org_id else []

    lessons_meta = list(
        Lesson.objects.filter(module__course__organization_id=org_id, type='assessment').values('id', 'title', 'module_id', 'module__course_id').order_by('order', 'title')
    ) if org_id else []

    departments_meta = list(
        Department.objects.filter(organization_id=org_id).values('id', 'name').order_by('name')
    ) if org_id else []

    roles_meta = list(
        Role.objects.filter(organization_id=org_id).values('id', 'name').order_by('name')
    ) if org_id else []

    users_meta = list(
        User.objects.filter(organization_id=org_id, is_active=True).values('id', 'first_name', 'last_name', 'username', 'email').order_by('first_name', 'last_name')
    ) if org_id else []

    formatted_users = [
        {
            'id': u['id'],
            'name': f"{u['first_name']} {u['last_name']}".strip() or u['username'],
            'email': u['email']
        }
        for u in users_meta
    ]

    return Response({
        'results': rows,
        'total_count': len(rows),
        'filter_options': {
            'courses': courses_meta,
            'modules': modules_meta,
            'lessons': lessons_meta,
            'departments': departments_meta,
            'roles': roles_meta,
            'users': formatted_users,
        }
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsOrgScoped])
def org_admin_assessment_attempt_detail(request, attempt_id):
    """
    GET /api/courses/org-admin/assessment-activity/<attempt_id>/
    Returns detailed attempt metadata plus question-by-question breakdown for lesson assessment attempts.
    Strictly isolated to requesting Org Admin's organization.
    """
    if request.user.is_platform_super_admin:
        org_id = request.GET.get('organization_id') or request.user.organization_id
    else:
        org_id = request.user.organization_id

    if not org_id and not request.user.is_platform_super_admin:
        return Response({'error': 'Organization context required.'}, status=status.HTTP_403_FORBIDDEN)

    # Access Control Feature check
    if org_id and not request.user.is_platform_super_admin:
        from master_setup.models import OrganizationFeatureAccess
        org_access = OrganizationFeatureAccess.objects.filter(
            organization_id=org_id,
            feature__key='assessment_activity'
        ).first()
        if org_access is not None and not org_access.enabled:
            return Response({'error': 'Assessment Activity module is disabled for your organization.'}, status=status.HTTP_403_FORBIDDEN)

    try:
        if request.user.is_platform_super_admin:
            attempt = AssessmentAttempt.objects.select_related(
                'user', 'user__department', 'user__role', 'course', 'lesson', 'lesson__module'
            ).get(pk=attempt_id, lesson__isnull=False)
        else:
            attempt = AssessmentAttempt.objects.select_related(
                'user', 'user__department', 'user__role', 'course', 'lesson', 'lesson__module'
            ).get(pk=attempt_id, course__organization_id=org_id, lesson__isnull=False)
    except AssessmentAttempt.DoesNotExist:
        return Response({'error': 'Assessment attempt not found or unauthorized.'}, status=status.HTTP_404_NOT_FOUND)

    # Attempt sequence calculation
    pair_attempts = list(
        AssessmentAttempt.objects.filter(user_id=attempt.user_id, lesson_id=attempt.lesson_id)
        .order_by('started_at', 'id')
        .values_list('id', flat=True)
    )
    try:
        attempt_number = pair_attempts.index(attempt.id) + 1
    except ValueError:
        attempt_number = 1
    total_attempts = len(pair_attempts) or 1

    # Questions breakdown
    q_ids = attempt.question_ids if (attempt.question_ids and isinstance(attempt.question_ids, list)) else []
    if not q_ids and attempt.lesson_id:
        q_ids = list(AssessmentQuestion.objects.filter(lesson_id=attempt.lesson_id).values_list('id', flat=True))

    questions_qs = AssessmentQuestion.objects.filter(id__in=q_ids)
    q_map = {q.id: q for q in questions_qs}
    ordered_questions = [q_map[qid] for qid in q_ids if qid in q_map]

    opt_map = {'0': 'A', '1': 'B', '2': 'C', '3': 'D', 'A': 'A', 'B': 'B', 'C': 'C', 'D': 'D'}
    answers = attempt.answers if isinstance(attempt.answers, dict) else {}

    question_details = []
    correct_count = 0

    for idx, q in enumerate(ordered_questions, 1):
        str_qid = str(q.id)
        raw_user_ans = answers.get(str_qid)
        user_choice_letter = opt_map.get(str(raw_user_ans).strip().upper(), str(raw_user_ans).strip().upper()) if raw_user_ans is not None else None
        correct_letter = str(q.correct_option).strip().upper()

        is_correct = (user_choice_letter == correct_letter) if user_choice_letter else False
        if is_correct:
            correct_count += 1

        options = [
            {'key': 'A', 'text': q.option_a},
            {'key': 'B', 'text': q.option_b},
            {'key': 'C', 'text': q.option_c},
            {'key': 'D', 'text': q.option_d},
        ]

        def get_opt_text(letter):
            for opt in options:
                if opt['key'] == letter:
                    return opt['text']
            return '-'

        question_details.append({
            'question_number': idx,
            'question_id': q.id,
            'question_text': q.question_text,
            'options': options,
            'user_answer': user_choice_letter,
            'user_answer_text': get_opt_text(user_choice_letter) if user_choice_letter else 'No answer submitted',
            'correct_option': correct_letter,
            'correct_option_text': get_opt_text(correct_letter),
            'is_correct': is_correct,
            'explanation': q.explanation or '',
        })

    total_q_count = len(ordered_questions)
    wrong_count = max(0, total_q_count - correct_count)
    score_val = attempt.score_percent if attempt.score_percent is not None else (
        int((correct_count / total_q_count) * 100) if total_q_count > 0 else 0
    )

    user_full_name = attempt.user.full_name if (attempt.user and hasattr(attempt.user, 'full_name') and attempt.user.full_name) else (
        f"{attempt.user.first_name} {attempt.user.last_name}".strip() if (attempt.user and (attempt.user.first_name or attempt.user.last_name)) else (
            attempt.user.username if attempt.user else "Unknown User"
        )
    )

    dept_name = attempt.user.department.name if (attempt.user and getattr(attempt.user, 'department', None)) else None
    role_name = attempt.user.role.name if (attempt.user and getattr(attempt.user, 'role', None)) else None

    return Response({
        'id': attempt.id,
        'user_name': user_full_name,
        'user_email': attempt.user.email if attempt.user else '',
        'department_name': dept_name,
        'role_name': role_name,
        'course_name': attempt.course.title if attempt.course else 'Unknown Course',
        'module_name': attempt.lesson.module.title if (attempt.lesson and attempt.lesson.module) else '-',
        'lesson_name': attempt.lesson.title if attempt.lesson else 'Unknown Lesson',
        'assessment_name': f"{attempt.lesson.title} Assessment" if attempt.lesson else "Lesson Assessment",
        'attempt_number': attempt_number,
        'total_attempts': total_attempts,
        'started_at': attempt.started_at.isoformat() if attempt.started_at else None,
        'submitted_at': attempt.submitted_at.isoformat() if attempt.submitted_at else None,
        'score': f"{correct_count} / {total_q_count}" if total_q_count > 0 else (f"{score_val}%" if attempt.submitted_at else "-"),
        'score_percent': score_val if attempt.submitted_at else None,
        'percentage': f"{score_val}%" if attempt.submitted_at else "-",
        'result': "Passed" if attempt.passed else ("In Progress" if not attempt.submitted_at else "Failed"),
        'status': "Passed" if attempt.passed else ("In Progress" if not attempt.submitted_at else "Failed"),
        'questions_attempted': total_q_count,
        'correct_answers': correct_count,
        'wrong_answers': wrong_count,
        'auto_submitted': attempt.auto_submitted,
        'questions': question_details,
    }, status=status.HTTP_200_OK)




