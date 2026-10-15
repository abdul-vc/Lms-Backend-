import hmac
import logging
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import BasePermission
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework import status
from .audit import log_activity
from .provisioning_services import (
    provision_tenant,
    provision_user,
    ProvisioningValidationError,
    TenantNotFoundError,
    ProvisioningConflictError,
)

logger = logging.getLogger(__name__)


class VibeConnectM2MAuthentication(BaseAuthentication):
    """
    Enforces server-to-server M2M token authentication for integration endpoints.
    Requires:
      Authorization: Bearer <VIBECONNECT_M2M_SECRET>
    """
    def authenticate_header(self, request):
        return 'Bearer realm="vibeconnect-m2m"'

    def authenticate(self, request):
        auth_header = request.headers.get('Authorization') or request.META.get('HTTP_AUTHORIZATION')
        if not auth_header:
            raise AuthenticationFailed("Authentication credentials were not provided.")

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            raise AuthenticationFailed("Invalid authorization scheme. Expected 'Bearer <token>'.")

        token = parts[1].strip()
        m2m_secret = getattr(settings, 'VIBECONNECT_M2M_SECRET', '')
        if not m2m_secret:
            logger.error("VIBECONNECT_M2M_SECRET is not configured on server.")
            raise AuthenticationFailed("M2M authentication is not configured.")

        # Constant-time comparison
        if not hmac.compare_digest(token, m2m_secret):
            raise AuthenticationFailed("Invalid M2M credentials.")

        # Return (user, auth) tuple
        return (AnonymousUser(), "vibeconnect_m2m")


class VibeConnectLaunchGrantAuthentication(BaseAuthentication):
    """
    Enforces server-to-server token authentication specifically for the launch-grant API.
    Requires:
      Authorization: Bearer <VIBECONNECT_LAUNCH_GRANT_SECRET>
    Uses dedicated secret isolated from provisioning and legacy SSO credentials.
    """
    def authenticate_header(self, request):
        return 'Bearer realm="vibeconnect-launch-grant"'

    def authenticate(self, request):
        auth_header = request.headers.get('Authorization') or request.META.get('HTTP_AUTHORIZATION')
        if not auth_header:
            raise AuthenticationFailed("Authentication credentials were not provided.")

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            raise AuthenticationFailed("Invalid authorization scheme. Expected 'Bearer <token>'.")

        token = parts[1].strip()
        grant_secret = getattr(settings, 'VIBECONNECT_LAUNCH_GRANT_SECRET', '')
        if not grant_secret:
            logger.error("VIBECONNECT_LAUNCH_GRANT_SECRET is not configured on server.")
            raise AuthenticationFailed("Launch grant M2M authentication is not configured.")

        # Constant-time comparison
        if not hmac.compare_digest(token, grant_secret):
            raise AuthenticationFailed("Invalid launch grant M2M credentials.")

        # Return (user, auth) tuple
        return (AnonymousUser(), "vibeconnect_launch_grant")


class IsM2MAuthenticated(BasePermission):
    """
    Allows access only to requests authenticated via VibeConnectM2MAuthentication.
    Normal browser users/JWTs are rejected.
    """
    def has_permission(self, request, view):
        return getattr(request, 'auth', None) == "vibeconnect_m2m"


class IsLaunchGrantAuthenticated(BasePermission):
    """
    Allows access only to requests authenticated via VibeConnectLaunchGrantAuthentication.
    """
    def has_permission(self, request, view):
        return getattr(request, 'auth', None) == "vibeconnect_launch_grant"


class TenantProvisionView(APIView):
    """
    POST /api/v1/integration/tenants/provision/

    Idempotently provisions or updates an LMS Organization for an external tenant.
    Authenticated via M2M Bearer token only.
    """
    authentication_classes = [VibeConnectM2MAuthentication]
    permission_classes = [IsM2MAuthenticated]

    def post(self, request, *args, **kwargs):
        data = request.data if isinstance(request.data, dict) else {}

        external_tenant_id = data.get('external_tenant_id')
        name = data.get('name')
        code = data.get('code')
        tenant_status = data.get('status')

        # Basic presence validation
        if not external_tenant_id or not isinstance(external_tenant_id, str) or not external_tenant_id.strip():
            return Response(
                {"error": "validation_error", "detail": "external_tenant_id is required and cannot be blank."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if not name or not isinstance(name, str) or not name.strip():
            return Response(
                {"error": "validation_error", "detail": "name is required and cannot be blank."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if not code or not isinstance(code, str) or not code.strip():
            return Response(
                {"error": "validation_error", "detail": "code is required and cannot be blank."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if not tenant_status or not isinstance(tenant_status, str) or not tenant_status.strip():
            return Response(
                {"error": "validation_error", "detail": "status is required and cannot be blank."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            org, mapping, action_taken = provision_tenant(
                provider='vibeconnect',
                external_tenant_id=external_tenant_id.strip(),
                name=name.strip(),
                code=code.strip(),
                status=tenant_status.strip()
            )

            # Audit activity
            try:
                log_activity(
                    request,
                    'tenant_provisioned',
                    target=org,
                    organization=org,
                    metadata={
                        'provider': 'vibeconnect',
                        'external_tenant_id': external_tenant_id.strip(),
                        'action_taken': action_taken,
                    }
                )
            except Exception as audit_err:
                logger.warning(f"Failed to log tenant provisioning audit: {audit_err}")

            response_status = status.HTTP_201_CREATED if action_taken == "created" else status.HTTP_200_OK
            return Response(
                {
                    "external_tenant_id": external_tenant_id.strip(),
                    "lms_organization_id": org.id,
                    "status": org.status.lower(),
                    "action_taken": action_taken,
                },
                status=response_status
            )

        except ProvisioningValidationError as exc:
            return Response(
                {"error": "validation_error", "detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except ProvisioningConflictError as exc:
            return Response(
                {"error": "conflict", "detail": str(exc)},
                status=status.HTTP_409_CONFLICT
            )
        except Exception as exc:
            logger.exception("Unexpected error during tenant provisioning.")
            return Response(
                {"error": "server_error", "detail": "An unexpected error occurred during tenant provisioning."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class UserProvisionView(APIView):
    """
    POST /api/v1/integration/users/provision/

    Idempotently provisions or updates an LMS User for an external user identity.
    Authenticated via M2M Bearer token only.
    """
    authentication_classes = [VibeConnectM2MAuthentication]
    permission_classes = [IsM2MAuthenticated]

    def post(self, request, *args, **kwargs):
        data = request.data if isinstance(request.data, dict) else {}

        external_tenant_id = data.get('external_tenant_id')
        external_user_id = data.get('external_user_id')
        email = data.get('email')
        first_name = data.get('first_name', '')
        last_name = data.get('last_name', '')
        is_active = data.get('is_active')
        role = data.get('role')

        # Basic presence validation
        if not external_tenant_id or not isinstance(external_tenant_id, str) or not external_tenant_id.strip():
            return Response(
                {"error": "validation_error", "detail": "external_tenant_id is required and cannot be blank."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if not external_user_id or not isinstance(external_user_id, str) or not external_user_id.strip():
            return Response(
                {"error": "validation_error", "detail": "external_user_id is required and cannot be blank."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if not email or not isinstance(email, str) or not email.strip():
            return Response(
                {"error": "validation_error", "detail": "email is required and cannot be blank."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if is_active is None or not isinstance(is_active, bool):
            return Response(
                {"error": "validation_error", "detail": "is_active is required and must be a boolean."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if role is not None and (not isinstance(role, str) or not role.strip()):
            return Response(
                {"error": "validation_error", "detail": "role must be a non-empty string when provided."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user, mapping, action_taken = provision_user(
                provider='vibeconnect',
                external_tenant_id=external_tenant_id.strip(),
                external_user_id=external_user_id.strip(),
                email=email.strip(),
                first_name=first_name,
                last_name=last_name,
                is_active=is_active,
                role=role.strip() if isinstance(role, str) else None
            )

            # Audit activity
            try:
                log_activity(
                    request,
                    'user_provisioned',
                    target=user,
                    organization=user.organization,
                    metadata={
                        'provider': 'vibeconnect',
                        'external_tenant_id': external_tenant_id.strip(),
                        'external_user_id': external_user_id.strip(),
                        'action_taken': action_taken,
                        'role': user.role.name if user.role else None,
                    }
                )
            except Exception as audit_err:
                logger.warning(f"Failed to log user provisioning audit: {audit_err}")

            response_status = status.HTTP_201_CREATED if action_taken == "created" else status.HTTP_200_OK
            return Response(
                {
                    "external_tenant_id": external_tenant_id.strip(),
                    "external_user_id": external_user_id.strip(),
                    "lms_user_id": user.id,
                    "email": user.email,
                    "is_active": user.is_active,
                    "role": user.role.name if user.role else None,
                    "action_taken": action_taken,
                },
                status=response_status
            )

        except ProvisioningValidationError as exc:
            return Response(
                {"error": "validation_error", "detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except TenantNotFoundError as exc:
            return Response(
                {"error": "tenant_not_found", "detail": str(exc)},
                status=status.HTTP_404_NOT_FOUND
            )
        except ProvisioningConflictError as exc:
            return Response(
                {"error": "conflict", "detail": str(exc)},
                status=status.HTTP_409_CONFLICT
            )
        except Exception as exc:
            logger.exception("Unexpected error during user provisioning.")
            return Response(
                {"error": "server_error", "detail": "An unexpected error occurred during user provisioning."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class LaunchGrantView(APIView):
    """
    POST /api/v1/integration/launch-grant/

    Authenticated via dedicated launch-grant M2M Bearer token only.
    Receives trusted identity and context from VibeConnect, verifies existing
    Phase 5B tenant & user mappings, validates safe internal target routes,
    and creates a short-lived, single-use launch grant.
    Returns the frontend callback URL containing the one-time code.
    """
    authentication_classes = [VibeConnectLaunchGrantAuthentication]
    permission_classes = [IsLaunchGrantAuthenticated]

    # Whitelist of safe route prefixes
    SAFE_ROUTE_PREFIXES = (
        '/dashboard',
        '/catalog',
        '/paths',
        '/certificates',
        '/ai-assistant',
        '/messenger',
        '/profile',
        '/courses/',
    )
    ADMIN_ROUTE_PREFIXES = (
        '/org-admin',
    )

    def post(self, request, *args, **kwargs):
        import hashlib
        import secrets
        from datetime import timedelta
        from django.utils import timezone
        from .mapping_services import lookup_tenant_mapping, lookup_user_mapping
        from .models import LmsLaunchGrant

        data = request.data if isinstance(request.data, dict) else {}
        external_tenant_id = data.get('external_tenant_id')
        external_user_id = data.get('external_user_id')
        context = data.get('context', 'standard')
        target_route = data.get('target_route', '')

        # 1. Validation
        if not external_tenant_id or not isinstance(external_tenant_id, str) or not external_tenant_id.strip():
            return Response(
                {"error": "validation_error", "detail": "external_tenant_id is required and cannot be blank."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if not external_user_id or not isinstance(external_user_id, str) or not external_user_id.strip():
            return Response(
                {"error": "validation_error", "detail": "external_user_id is required and cannot be blank."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if context not in ('standard', 'showcase'):
            return Response(
                {"error": "validation_error", "detail": "context must be either 'standard' or 'showcase'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        norm_tenant_id = external_tenant_id.strip()
        norm_user_id = external_user_id.strip()

        # 2. Resolve Tenant Mapping
        tenant_mapping = lookup_tenant_mapping(provider='vibeconnect', external_tenant_id=norm_tenant_id)
        if not tenant_mapping or not tenant_mapping.organization:
            return Response(
                {
                    "error": "tenant_not_found",
                    "detail": f"Tenant '{norm_tenant_id}' is not mapped to an LMS organization. Provision tenant first."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        org = tenant_mapping.organization
        if getattr(org, 'status', None) != 'Active':
            return Response(
                {"error": "account_frozen", "detail": "Organization account is inactive. Kindly contact admin for assistance."},
                status=status.HTTP_403_FORBIDDEN
            )

        # 3. Resolve User Mapping
        user_mapping = lookup_user_mapping(provider='vibeconnect', external_user_id=norm_user_id)
        if not user_mapping or not user_mapping.user:
            return Response(
                {
                    "error": "user_not_found",
                    "detail": f"User '{norm_user_id}' is not provisioned in LMS. Provision user first."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        user = user_mapping.user

        # Platform super admin safety protection
        if getattr(user, 'is_platform_super_admin', False):
            return Response(
                {"error": "forbidden", "detail": "Platform super administrators cannot be launched via launch grant."},
                status=status.HTTP_403_FORBIDDEN
            )

        if not getattr(user, 'is_active', False):
            return Response(
                {"error": "account_frozen", "detail": "User account is inactive. Kindly contact admin for assistance."},
                status=status.HTTP_403_FORBIDDEN
            )

        # 4. Strict Tenant Isolation Invariant
        if user_mapping.organization_id != org.id or user.organization_id != org.id:
            logger.error(
                f"Tenant isolation mismatch during launch grant: User {user.id} belongs to Org "
                f"{user.organization_id}, but requested tenant maps to Org {org.id}."
            )
            return Response(
                {
                    "error": "conflict",
                    "detail": "Cross-tenant isolation violation: User organization does not match the requested tenant."
                },
                status=status.HTTP_409_CONFLICT
            )

        # 5. Validate Target Route and Role Boundary
        clean_target_route = ''
        if target_route and isinstance(target_route, str):
            candidate = target_route.strip()
            # Must be a relative path, no protocol-relative or external URLs (e.g. //evil.com or https://)
            if candidate.startswith('/') and not candidate.startswith('//') and '\\' not in candidate:
                is_admin = bool(user.role and getattr(user.role, 'is_admin_role', False))
                # Super-admin routes are strictly prohibited
                if candidate.startswith('/super-admin') or candidate.startswith('/admin'):
                    clean_target_route = ''
                # Org-admin routes only permitted if user actually has an admin role
                elif any(candidate == prefix or candidate.startswith(f"{prefix}/") for prefix in self.ADMIN_ROUTE_PREFIXES):
                    if is_admin:
                        clean_target_route = candidate
                    else:
                        clean_target_route = ''  # Non-admin cannot receive admin route
                # Safe learner routes
                elif any(candidate == prefix or candidate.startswith(prefix) for prefix in self.SAFE_ROUTE_PREFIXES):
                    clean_target_route = candidate

        # 6. Generate high-entropy one-time code and store cryptographic hash
        code = secrets.token_urlsafe(32)
        code_hash = hashlib.sha256(code.encode('utf-8')).hexdigest()
        expires_at = timezone.now() + timedelta(seconds=60)

        LmsLaunchGrant.objects.create(
            code_hash=code_hash,
            organization=org,
            user=user,
            context=context,
            target_route=clean_target_route,
            is_consumed=False,
            expires_at=expires_at
        )

        # 6. Build callback URL
        frontend_base = getattr(settings, 'FRONTEND_URL', 'https://lms.vibesandbox.live').rstrip('/')
        callback_url = f"{frontend_base}/sso/vibeconnect/callback?code={code}"

        # Audit
        try:
            log_activity(
                request,
                'launch_grant_created',
                target=user,
                organization=org,
                metadata={
                    'provider': 'vibeconnect',
                    'external_tenant_id': norm_tenant_id,
                    'external_user_id': norm_user_id,
                    'context': context,
                    'target_route': clean_target_route,
                }
            )
        except Exception as audit_err:
            logger.warning(f"Failed to log launch grant audit: {audit_err}")

        return Response(
            {
                "callback_url": callback_url,
                "expires_in": 60,
                "context": context,
            },
            status=status.HTTP_201_CREATED
        )
