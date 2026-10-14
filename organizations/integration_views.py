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


class IsM2MAuthenticated(BasePermission):
    """
    Allows access only to requests authenticated via VibeConnectM2MAuthentication.
    Normal browser users/JWTs are rejected.
    """
    def has_permission(self, request, view):
        return getattr(request, 'auth', None) == "vibeconnect_m2m"


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
