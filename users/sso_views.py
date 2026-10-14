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
