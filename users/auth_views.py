from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .serializers import UserSerializer


from rest_framework.exceptions import AuthenticationFailed

from rest_framework import serializers

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    username = serializers.CharField(required=False, allow_blank=True)
    email = serializers.CharField(required=False, allow_blank=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.username_field in self.fields:
            self.fields[self.username_field].required = False

    def validate(self, attrs):
        username_input = attrs.get('username') or attrs.get('email')
        if not username_input:
            raise serializers.ValidationError({'username': 'Username or email is required.'})
        attrs['username'] = username_input

        from django.contrib.auth import get_user_model
        UserModel = get_user_model()
        
        user_candidate = UserModel.objects.filter(username__iexact=username_input).first() or UserModel.objects.filter(email__iexact=username_input).first()
        if user_candidate:
            if not user_candidate.is_active or (user_candidate.organization and user_candidate.organization.status == 'Inactive' and not user_candidate.is_platform_super_admin):
                raise AuthenticationFailed(
                    {'error': 'account_frozen', 'message': 'Kindly contact admin for assistance.'},
                    code='account_frozen'
                )

        data = super().validate(attrs)

        if self.user:
            if not self.user.is_active or (self.user.organization and self.user.organization.status == 'Inactive' and not self.user.is_platform_super_admin):
                raise AuthenticationFailed(
                    {'error': 'account_frozen', 'message': 'Kindly contact admin for assistance.'},
                    code='account_frozen'
                )

        return data

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Embed key claims in the JWT so the frontend can read them without hitting /me/
        token['org_id'] = user.organization_id
        token['is_platform_super_admin'] = user.is_platform_super_admin
        return token


from organizations.audit import log_activity

class LoginView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            user = serializer.user
            # Temporarily attach user to request so log_activity can pick it up
            request.user = user
            log_activity(request, 'login', target=user, organization=user.organization)
            return Response(serializer.validated_data, status=200)
        except Exception as e:
            log_activity(request, 'login_failed', metadata={'email': request.data.get('email')})
            raise


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user, context={'request': request}).data)

    def patch(self, request):
        user = request.user
        data = request.data.copy()

        # Handle explicit removal of profile_picture
        remove_picture = (
            data.get('remove_profile_picture') == 'true' or
            data.get('remove_profile_picture') is True or
            (data.get('profile_picture') in ['null', 'none', '', 'delete', None] and not request.FILES.get('profile_picture'))
        )

        if remove_picture:
            if user.profile_picture:
                try:
                    user.profile_picture.delete(save=False)
                except Exception:
                    pass
            user.profile_picture = None
            user.save()
            if 'profile_picture' in data:
                del data['profile_picture']

        serializer = UserSerializer(user, data=data, partial=True, context={'request': request})
        if serializer.is_valid():
            updated_user = serializer.save()
            return Response(UserSerializer(updated_user, context={'request': request}).data)
        return Response(serializer.errors, status=400)

class RegisterView(APIView):
    """
    Public / Dynamic tenant user registration endpoint. Zero hardcoded fields.
    """
    permission_classes = []

    def post(self, request):
        data = request.data
        email = data.get('email', '').strip()
        username = data.get('username', '').strip() or email
        password = data.get('password', '')
        first_name = data.get('first_name', '').strip()
        last_name = data.get('last_name', '').strip()

        if not email or not password:
            return Response({'detail': 'Email and password are required for registration.'}, status=400)

        from django.contrib.auth import get_user_model
        User = get_user_model()

        if User.objects.filter(email__iexact=email).exists():
            return Response({'detail': 'A user with this email address already exists.'}, status=400)
        if User.objects.filter(username__iexact=username).exists():
            return Response({'detail': 'A user with this username already exists.'}, status=400)

        # 1. Resolve Organization Dynamically (zero hardcoding)
        from organizations.models import Organization, Role, Department
        org = None
        org_id = data.get('organization_id') or data.get('organization')
        sub_domain = data.get('sub_domain')
        
        if org_id:
            org = Organization.objects.filter(pk=org_id).first()
        elif sub_domain:
            org = Organization.objects.filter(sub_domain__iexact=sub_domain.strip()).first()

        # 2. Resolve Role Dynamically
        role = None
        role_id = data.get('role_id') or data.get('role')
        if role_id:
            role = Role.objects.filter(pk=role_id).first()
        elif org:
            # Default to default role in org (e.g. Learner/Student), fallback to first role
            role = Role.objects.filter(organization=org, is_default=True, is_admin_role=False).first() or Role.objects.filter(organization=org).first()

        # 3. Resolve Department Dynamically
        dept = None
        dept_id = data.get('department_id') or data.get('department')
        if dept_id:
            dept = Department.objects.filter(pk=dept_id).first()

        # 4. Create User
        user = User.objects.create(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            organization=org,
            role=role,
            department=dept,
            is_active=True
        )
        user.set_password(password)
        user.save()

        # 5. Send Branded Welcome Email Dynamically
        if org and email:
            from organizations.emails import send_tenant_welcome_email
            send_tenant_welcome_email(
                org=org,
                recipient_email=email,
                admin_username=username,
                raw_password=password,
                request=request
            )

        log_activity(request, 'user_created', target=user, organization=org)

        return Response({
            'detail': 'User registered successfully.',
            'user': UserSerializer(user).data
        }, status=201)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        if not user.check_password(request.data.get('current_password', '')):
            return Response({'detail': 'Current password is incorrect.'}, status=400)
        
        new_password = request.data.get('new_password', '')
        if len(new_password) < 8:
            return Response({'detail': 'Password must be at least 8 characters.'}, status=400)
            
        user.set_password(new_password)
        user.save()
        return Response({'detail': 'Password updated.'})


from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth import get_user_model
from organizations.emails import send_password_reset_email

User = get_user_model()

class ForgotPasswordView(APIView):
    permission_classes = []

    def post(self, request):
        identifier = request.data.get('email', '').strip() or request.data.get('username', '').strip()
        if not identifier:
            return Response({'detail': 'Please provide an email address or username.'}, status=400)

        user = User.objects.filter(email__iexact=identifier).first() or User.objects.filter(username__iexact=identifier).first()
        
        if user and user.email:
            token = default_token_generator.make_token(user)
            uid_b64 = urlsafe_base64_encode(force_bytes(user.pk))
            send_password_reset_email(user, token, uid_b64, request=request)

        return Response({
            'detail': 'If an account exists with that email/username, a password reset link has been sent to the registered inbox.'
        })

class ResetPasswordConfirmView(APIView):
    permission_classes = []

    def post(self, request):
        uid_b64 = request.data.get('uid')
        token = request.data.get('token')
        new_password = request.data.get('new_password')

        if not uid_b64 or not token or not new_password:
            return Response({'detail': 'Missing uid, token, or new_password.'}, status=400)

        if len(new_password) < 8:
            return Response({'detail': 'Password must be at least 8 characters long.'}, status=400)

        try:
            pk = force_str(urlsafe_base64_decode(uid_b64))
            user = User.objects.get(pk=pk)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response({'detail': 'Invalid password reset link.'}, status=400)

        if not default_token_generator.check_token(user, token):
            return Response({'detail': 'This password reset token is invalid or has expired.'}, status=400)

        user.set_password(new_password)
        user.save()
        log_activity(request, 'password_reset_confirm', target=user, organization=user.organization)

        return Response({'detail': 'Password has been reset successfully. You can now sign in with your new password.'})


class UpdateThemePreferenceView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        theme = request.data.get('theme_preference') or request.data.get('theme')
        if theme not in ['light', 'dark']:
            return Response({'detail': 'Invalid theme preference. Allowed choices are "light" or "dark".'}, status=400)
        
        request.user.theme_preference = theme
        request.user.save(update_fields=['theme_preference'])
        return Response({
            'detail': 'Theme preference updated successfully.',
            'theme_preference': request.user.theme_preference
        })


