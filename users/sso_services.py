import json
import logging
import urllib.request
import urllib.error
from typing import Dict, Any, Tuple, Optional
from django.conf import settings
from django.contrib.auth import get_user_model
from organizations.mapping_services import lookup_tenant_mapping, lookup_user_mapping
from users.auth_views import CustomTokenObtainPairSerializer

logger = logging.getLogger(__name__)
User = get_user_model()


class SSOConfigurationError(Exception):
    """Raised when required VibeConnect SSO settings are missing or misconfigured."""
    pass


class SSOUpstreamError(Exception):
    """Raised when upstream VibeConnect validation encounters HTTP or network failure."""
    def __init__(self, message: str, status_code: int = 502, error_code: str = "upstream_error"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code


class SSOClaimsValidationError(Exception):
    """Raised when VibeConnect response claims fail structural or business validation."""
    def __init__(self, message: str, error_code: str = "invalid_claims"):
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class SSOMappingError(Exception):
    """Raised when tenant/user resolution, isolation, or account status check fails."""
    def __init__(self, message: str, code: str = "mapping_error", status_code: int = 403):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


def validate_vibeconnect_code(code: str, code_verifier: Optional[str] = None) -> Dict[str, Any]:
    """
    Calls VibeConnect back-channel validation API:
    POST {VIBECONNECT_API_BASE_URL}/api/v1/sso/validate/
    
    Headers:
      Authorization: Bearer <VIBECONNECT_M2M_SECRET>
      Content-Type: application/json
    
    Request:
      {"code": code, "client_identifier": client_id}
      or with PKCE:
      {"code": code, "client_identifier": client_id, "code_verifier": code_verifier}
    
    Uses standard library urllib.request only.
    Never exposes M2M secret in exceptions or return values.
    """
    api_base = getattr(settings, 'VIBECONNECT_API_BASE_URL', '').rstrip('/')
    m2m_secret = getattr(settings, 'VIBECONNECT_M2M_SECRET', '')
    client_id = getattr(settings, 'VIBECONNECT_SSO_CLIENT_ID', 'pilot_lms_client')
    timeout = getattr(settings, 'VIBECONNECT_HTTP_TIMEOUT', 10)

    if not api_base:
        logger.error("VIBECONNECT_API_BASE_URL is not configured.")
        raise SSOConfigurationError("VibeConnect SSO API base URL is not configured.")

    if not m2m_secret:
        logger.error("VIBECONNECT_M2M_SECRET is not configured.")
        raise SSOConfigurationError("VibeConnect M2M connector secret is not configured.")

    validate_url = f"{api_base}/api/v1/sso/validate/"
    payload = {
        "code": code,
        "client_identifier": client_id,
    }
    if code_verifier and isinstance(code_verifier, str) and code_verifier.strip():
        payload["code_verifier"] = code_verifier.strip()

    req_data = json.dumps(payload).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {m2m_secret}'
    }

    req = urllib.request.Request(validate_url, data=req_data, headers=headers, method='POST')

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            resp_body = response.read().decode('utf-8')
            return json.loads(resp_body)
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        err_body = None
        try:
            raw_err = exc.read().decode('utf-8')
            err_body = json.loads(raw_err)
        except Exception:
            pass

        upstream_err = (err_body.get('error') if isinstance(err_body, dict) else '') or ''
        upstream_detail = (err_body.get('detail') or err_body.get('message') if isinstance(err_body, dict) else '') or ''

        logger.warning(
            f"VibeConnect validation failed with HTTP {status_code}: "
            f"upstream_error='{upstream_err}', upstream_detail='{upstream_detail}'"
        )
        
        if status_code == 401:
            raise SSOUpstreamError(
                "Upstream VibeConnect authorization failed. Connector credentials rejected.",
                status_code=401,
                error_code="sso_unauthorized"
            )
        elif status_code in (400, 403):
            if upstream_err == 'CODE_ALREADY_USED' or 'already' in str(upstream_detail).lower():
                msg = "Authorization code has already been consumed. Please launch LMS again from VibeConnect."
            elif upstream_err == 'CODE_EXPIRED' or 'expired' in str(upstream_detail).lower():
                msg = "Authorization code has expired. Please launch LMS again from VibeConnect."
            else:
                msg = "Authorization code or PKCE verifier is invalid or expired."

            raise SSOUpstreamError(
                msg,
                status_code=401,
                error_code="sso_failed"
            )
        else:
            raise SSOUpstreamError(
                f"VibeConnect validation service returned HTTP {status_code}.",
                status_code=502,
                error_code="upstream_error"
            )
    except (urllib.error.URLError, TimeoutError) as exc:
        logger.error(f"VibeConnect network/timeout error: {exc}")
        raise SSOUpstreamError(
            "Unable to reach VibeConnect identity service. Connection timed out or failed.",
            status_code=504,
            error_code="upstream_unavailable"
        )
    except json.JSONDecodeError as exc:
        logger.error(f"VibeConnect response JSON decode error: {exc}")
        raise SSOClaimsValidationError(
            "VibeConnect returned an unparseable response.",
            error_code="malformed_response"
        )


def validate_claims(claims: Dict[str, Any]) -> Dict[str, Any]:
    """
    Defensively validates VibeConnect response claims against the locked contract:
      - user: dict with non-empty 'id' and 'email'
      - organization: dict with non-empty 'id'
      - product: dict with 'code' == 'lms'
      - audience: matches VIBECONNECT_SSO_AUDIENCE
      - assignment_id: non-empty string
    """
    if not isinstance(claims, dict):
        raise SSOClaimsValidationError("SSO claims payload must be a JSON object.", error_code="malformed_response")

    # 1. User Claim
    user_obj = claims.get('user')
    if not isinstance(user_obj, dict) or not user_obj.get('id') or not user_obj.get('email'):
        raise SSOClaimsValidationError(
            "SSO claims missing or invalid 'user' object with 'id' and 'email'.",
            error_code="invalid_user_claim"
        )

    # 2. Organization Claim
    org_obj = claims.get('organization')
    if not isinstance(org_obj, dict) or not org_obj.get('id'):
        raise SSOClaimsValidationError(
            "SSO claims missing or invalid 'organization' object with 'id'.",
            error_code="invalid_organization_claim"
        )

    # 3. Product Claim (Locked contract specifies singular 'product' object)
    product_obj = claims.get('product')
    if not isinstance(product_obj, dict) or product_obj.get('code') != 'lms':
        raise SSOClaimsValidationError(
            "SSO claims missing or invalid 'product' assignment for 'lms'.",
            error_code="invalid_product"
        )

    # 4. Audience Claim
    expected_aud = getattr(settings, 'VIBECONNECT_SSO_AUDIENCE', 'vibeconnect-lms')
    audience = claims.get('audience')
    if audience != expected_aud:
        raise SSOClaimsValidationError(
            f"SSO audience mismatch: expected '{expected_aud}', received '{audience}'.",
            error_code="invalid_audience"
        )

    # 5. Assignment ID
    if not claims.get('assignment_id'):
        raise SSOClaimsValidationError(
            "SSO claims missing required 'assignment_id'.",
            error_code="missing_assignment_id"
        )

    return claims


def resolve_sso_user_and_session(claims: Dict[str, Any]) -> Tuple[Any, Dict[str, Any]]:
    """
    Resolves LMS Organization and User via Phase 5B mapping layer.
    Enforces tenant isolation, active status, and creates local SimpleJWT session.
    
    Mapping:
      - claims['organization']['id'] -> ExternalTenantMapping.external_tenant_id (provider='vibeconnect')
      - claims['user']['id'] -> ExternalUserMapping.external_user_id (provider='vibeconnect')
    
    Invariants:
      - Tenant must be mapped to an LMS Organization.
      - User must be mapped to an LMS User (provisioned beforehand).
      - Mapped user organization must strictly match mapped tenant organization.
      - User and Organization must be active.
    """
    ext_tenant_id = str(claims['organization']['id']).strip()
    ext_user_id = str(claims['user']['id']).strip()

    # 1. Resolve Tenant Mapping
    tenant_mapping = lookup_tenant_mapping(provider="vibeconnect", external_tenant_id=ext_tenant_id)
    if not tenant_mapping or not tenant_mapping.organization:
        logger.warning(f"SSO rejected: Unmapped VibeConnect tenant '{ext_tenant_id}'")
        raise SSOMappingError(
            f"VibeConnect tenant '{ext_tenant_id}' is not mapped to an LMS organization.",
            code="unmapped_tenant",
            status_code=403
        )

    org = tenant_mapping.organization

    # 2. Check Organization Status
    if getattr(org, 'status', None) != 'Active':
        logger.warning(f"SSO rejected: LMS organization {org.id} is inactive.")
        raise SSOMappingError(
            "Organization account is inactive. Kindly contact admin for assistance.",
            code="account_frozen",
            status_code=403
        )

    # 3. Resolve User Mapping
    user_mapping = lookup_user_mapping(provider="vibeconnect", external_user_id=ext_user_id)
    if not user_mapping or not user_mapping.user:
        logger.warning(f"SSO rejected: Unmapped VibeConnect user '{ext_user_id}' in tenant '{ext_tenant_id}'")
        raise SSOMappingError(
            f"VibeConnect user '{ext_user_id}' is not provisioned in LMS. User must be provisioned before SSO login.",
            code="unmapped_user",
            status_code=403
        )

    user = user_mapping.user

    # 4. Check User Active Status
    if not getattr(user, 'is_active', False):
        logger.warning(f"SSO rejected: LMS user {user.id} is inactive.")
        raise SSOMappingError(
            "User account is inactive. Kindly contact admin for assistance.",
            code="account_frozen",
            status_code=403
        )

    # 5. Cross-Tenant Safety Invariant
    if user_mapping.organization_id != org.id or user.organization_id != org.id:
        logger.error(
            f"Cross-tenant violation: User {user.id} belongs to Org {user.organization_id}, "
            f"but tenant mapping resolved to Org {org.id}."
        )
        raise SSOMappingError(
            "Cross-tenant isolation violation: User organization does not match the authenticated tenant.",
            code="tenant_mismatch",
            status_code=403
        )

    # 6. Create Local SimpleJWT Session
    refresh = CustomTokenObtainPairSerializer.get_token(user)
    session_data = {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "user": {
            "id": user.id,
            "email": user.email,
        }
    }

    return user, session_data
