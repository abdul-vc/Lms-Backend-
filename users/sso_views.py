import logging
import uuid
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status
from organizations.audit import log_activity
from .sso_services import (
    validate_vibeconnect_code,
    validate_claims,
    resolve_sso_user_and_session,
    SSOConfigurationError,
    SSOUpstreamError,
    SSOClaimsValidationError,
    SSOMappingError,
)

logger = logging.getLogger(__name__)


class SSOCallbackView(APIView):
    """
    POST /api/v1/auth/sso/callback/
    
    Receives authorization code and PKCE code_verifier from the LMS frontend.
    Validates code with VibeConnect back-channel, maps external identity to
    an LMS User, and returns a local SimpleJWT session token pair.
    
    The M2M secret is never received from or returned to the browser.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        data = request.data if isinstance(request.data, dict) else {}
        code = data.get('code')
        code_verifier = data.get('code_verifier')

        reference_id = f"sso_{uuid.uuid4().hex[:10]}"

        # 1. Input Validation
        if not code or not isinstance(code, str) or not code.strip():
            return Response(
                {"error": "invalid_request", "detail": "code is required and cannot be blank.", "reference_id": reference_id},
                status=status.HTTP_400_BAD_REQUEST
            )

        code_verifier_clean = None
        if code_verifier and isinstance(code_verifier, str) and code_verifier.strip():
            code_verifier_clean = code_verifier.strip()

        # 2. Back-Channel Validation & Session Issuance
        try:
            raw_claims = validate_vibeconnect_code(code.strip(), code_verifier=code_verifier_clean)
            claims = validate_claims(raw_claims)
            user, session_data = resolve_sso_user_and_session(claims)

            # 3. Audit Activity
            try:
                request.user = user
                log_activity(
                    request,
                    'sso_login',
                    target=user,
                    organization=user.organization,
                    metadata={
                        'provider': 'vibeconnect',
                        'vibeconnect_user_id': claims['user']['id'],
                        'vibeconnect_tenant_id': claims['organization']['id'],
                    }
                )
            except Exception as audit_err:
                logger.warning(f"Failed to log SSO audit activity: {audit_err}")

            return Response(session_data, status=status.HTTP_200_OK)

        except SSOConfigurationError as exc:
            logger.critical(f"[{reference_id}] SSO Configuration Error: {exc}")
            return Response(
                {"error": "configuration_error", "detail": "SSO configuration error on server.", "reference_id": reference_id},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        except SSOUpstreamError as exc:
            logger.warning(f"[{reference_id}] SSO Upstream Error ({exc.error_code}): {exc.message}")
            return Response(
                {"error": exc.error_code, "detail": exc.message, "reference_id": reference_id},
                status=exc.status_code
            )

        except SSOClaimsValidationError as exc:
            logger.warning(f"[{reference_id}] SSO Claims Validation Error ({exc.error_code}): {exc.message}")
            return Response(
                {"error": exc.error_code, "detail": exc.message, "reference_id": reference_id},
                status=status.HTTP_403_FORBIDDEN
            )

        except SSOMappingError as exc:
            logger.warning(f"[{reference_id}] SSO Mapping Error ({exc.code}): {exc.message}")
            return Response(
                {"error": exc.code, "detail": exc.message, "reference_id": reference_id},
                status=exc.status_code
            )

        except Exception as exc:
            logger.exception(f"[{reference_id}] Unexpected error during SSO callback processing.")
            return Response(
                {"error": "sso_failed", "detail": "An unexpected error occurred during SSO authentication.", "reference_id": reference_id},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class VibeConnectExchangeView(APIView):
    """
    POST /api/v1/auth/sso/vibeconnect/exchange/

    Consumes a local single-use LmsLaunchGrant atomically and returns
    a local LMS SimpleJWT session token pair.
    Zero outbound network calls to VibeConnect required.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        import hashlib
        from django.db import transaction
        from django.utils import timezone
        from organizations.models import LmsLaunchGrant

        data = request.data if isinstance(request.data, dict) else {}
        code = data.get('code')
        reference_id = f"sso_vc_{uuid.uuid4().hex[:10]}"

        if not code or not isinstance(code, str) or not code.strip():
            return Response(
                {"error": "invalid_request", "detail": "code is required and cannot be blank.", "reference_id": reference_id},
                status=status.HTTP_400_BAD_REQUEST
            )

        clean_code = code.strip()
        code_hash = hashlib.sha256(clean_code.encode('utf-8')).hexdigest()

        try:
            with transaction.atomic():
                # Lock row with select_for_update to guarantee strict single-use and avoid race conditions
                grant = LmsLaunchGrant.objects.select_for_update().select_related('user', 'organization', 'user__role').filter(
                    code_hash=code_hash
                ).first()

                if not grant:
                    logger.warning(f"[{reference_id}] Launch grant not found for provided code.")
                    return Response(
                        {"error": "invalid_grant", "detail": "Launch grant code is invalid or has expired.", "reference_id": reference_id},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                now = timezone.now()

                # Replay / Already consumed check
                if grant.is_consumed:
                    logger.warning(f"[{reference_id}] Replay rejected: Launch grant {grant.id} was already consumed at {grant.consumed_at}.")
                    return Response(
                        {"error": "grant_already_consumed", "detail": "Launch grant code has already been consumed. Please launch again from VibeConnect.", "reference_id": reference_id},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Expiry check
                if now > grant.expires_at:
                    logger.warning(f"[{reference_id}] Launch grant {grant.id} expired at {grant.expires_at} (current time: {now}).")
                    return Response(
                        {"error": "grant_expired", "detail": "Launch grant code has expired. Please launch again from VibeConnect.", "reference_id": reference_id},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Active status checks on resolved models
                org = grant.organization
                if getattr(org, 'status', None) != 'Active':
                    logger.warning(f"[{reference_id}] Organization {org.id} is inactive.")
                    return Response(
                        {"error": "account_frozen", "detail": "Organization account is inactive. Kindly contact admin for assistance.", "reference_id": reference_id},
                        status=status.HTTP_403_FORBIDDEN
                    )

                user = grant.user
                if not getattr(user, 'is_active', False):
                    logger.warning(f"[{reference_id}] User {user.id} is inactive.")
                    return Response(
                        {"error": "account_frozen", "detail": "User account is inactive. Kindly contact admin for assistance.", "reference_id": reference_id},
                        status=status.HTTP_403_FORBIDDEN
                    )

                # Cross-tenant invariant check
                if user.organization_id != org.id:
                    logger.error(f"[{reference_id}] Cross-tenant violation: User {user.id} (org {user.organization_id}) != Grant Org {org.id}")
                    return Response(
                        {"error": "tenant_mismatch", "detail": "Cross-tenant isolation violation.", "reference_id": reference_id},
                        status=status.HTTP_403_FORBIDDEN
                    )

                # Consume atomically
                grant.is_consumed = True
                grant.consumed_at = now
                grant.save(update_fields=['is_consumed', 'consumed_at'])

                # Issue local SimpleJWT tokens
                from users.auth_views import CustomTokenObtainPairSerializer
                refresh = CustomTokenObtainPairSerializer.get_token(user)

                try:
                    request.user = user
                    log_activity(
                        request,
                        'sso_login_success',
                        target=user,
                        organization=org,
                        metadata={
                            'provider': 'vibeconnect',
                            'flow': 'launch_grant',
                            'context': grant.context,
                            'target_route': grant.target_route,
                            'reference_id': reference_id,
                        }
                    )
                except Exception as audit_err:
                    logger.warning(f"[{reference_id}] Failed to log launch-grant login audit: {audit_err}")

                return Response(
                    {
                        "access": str(refresh.access_token),
                        "refresh": str(refresh),
                        "target_route": grant.target_route or None,
                        "user": {
                            "id": user.id,
                            "email": user.email,
                            "is_platform_super_admin": user.is_platform_super_admin,
                            "role": {
                                "id": user.role.id,
                                "name": user.role.name,
                                "is_admin_role": user.role.is_admin_role,
                            } if user.role else None,
                        }
                    },
                    status=status.HTTP_200_OK
                )

        except Exception as exc:
            logger.exception(f"[{reference_id}] Unexpected error during launch grant exchange.")
            return Response(
                {"error": "sso_failed", "detail": "An unexpected error occurred during grant exchange.", "reference_id": reference_id},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
