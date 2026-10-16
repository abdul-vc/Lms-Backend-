import json
import urllib.error
from unittest.mock import patch, MagicMock
from io import BytesIO

from django.conf import settings
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken

from organizations.models import Organization, ExternalTenantMapping, ExternalUserMapping
from organizations.mapping_services import create_tenant_mapping, create_user_mapping

User = get_user_model()


@override_settings(
    VIBECONNECT_API_BASE_URL='https://mock-vibeconnect.internal',
    VIBECONNECT_SSO_CLIENT_ID='pilot_lms_client',
    VIBECONNECT_M2M_SECRET='test-super-secret-m2m-token-12345',
    VIBECONNECT_SSO_AUDIENCE='vibeconnect-lms',
    VIBECONNECT_HTTP_TIMEOUT=5
)
class SSOCallbackTestCase(TestCase):
    def setUp(self):
        # 1. Pilot Organization (Active)
        self.org = Organization.objects.create(
            name="Pilot Acme Corp",
            company_name="Pilot Acme Corporation",
            entity_name="Pilot Acme Corp",
            sub_domain="pilot-acme",
            status="Active"
        )
        self.other_org = Organization.objects.create(
            name="Other Corp",
            company_name="Other Corporation",
            entity_name="Other Corp",
            sub_domain="other-corp",
            status="Active"
        )
        self.inactive_org = Organization.objects.create(
            name="Frozen Corp",
            company_name="Frozen Corporation",
            entity_name="Frozen Corp",
            sub_domain="frozen-corp",
            status="Inactive"
        )

        # 2. Pilot User (Active)
        self.user = User.objects.create_user(
            username="pilot.john@acme.com",
            email="pilot.john@acme.com",
            password="TestPassword123!",
            organization=self.org,
            is_active=True
        )

        # Inactive User
        self.inactive_user = User.objects.create_user(
            username="inactive.john@acme.com",
            email="inactive.john@acme.com",
            password="TestPassword123!",
            organization=self.org,
            is_active=False
        )

        # Cross-Tenant User (belongs to other_org)
        self.cross_tenant_user = User.objects.create_user(
            username="other.jane@other.com",
            email="other.jane@other.com",
            password="TestPassword123!",
            organization=self.other_org,
            is_active=True
        )

        # 3. Canonical external identifiers (UUIDs)
        self.ext_tenant_id = "org_pilot_uuid_101"
        self.ext_user_id = "usr_vc_uuid_98765"
        self.other_ext_tenant_id = "org_other_uuid_202"

        # 4. Map Tenant to Org
        self.tenant_mapping = create_tenant_mapping(
            provider="vibeconnect",
            external_tenant_id=self.ext_tenant_id,
            organization=self.org
        )

        # Map User to Pilot User
        self.user_mapping = create_user_mapping(
            provider="vibeconnect",
            external_user_id=self.ext_user_id,
            organization=self.org,
            user=self.user
        )

        # Canonical valid VibeConnect claims
        self.valid_claims = {
            "user": {
                "id": self.ext_user_id,
                "email": "pilot.john@acme.com",
                "full_name": "John Pilot"
            },
            "organization": {
                "id": self.ext_tenant_id,
                "code": "acme",
                "name": "Pilot Acme Corp"
            },
            "product": {
                "id": "prod_lms_uuid",
                "code": "lms",
                "name": "Learning Management System"
            },
            "assignment_id": "asgn_uuid_456",
            "audience": "vibeconnect-lms"
        }

    def _mock_vibeconnect_response(self, data, status_code=200):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(data).encode('utf-8')
        mock_resp.getcode.return_value = status_code
        mock_resp.__enter__.return_value = mock_resp
        return mock_resp

    # ─── 1 & 2. INPUT VALIDATION ─────────────────────────────────────────────

    def test_missing_code_returns_400(self):
        resp = self.client.post(
            '/api/v1/auth/sso/callback/',
            {"code_verifier": "valid_verifier_string"},
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['error'], 'invalid_request')

        # Blank code
        resp = self.client.post(
            '/api/v1/auth/sso/callback/',
            {"code": "   ", "code_verifier": "valid_verifier_string"},
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['error'], 'invalid_request')

    @patch('urllib.request.urlopen')
    def test_no_pkce_master_initiated_success(self, mock_urlopen):
        mock_urlopen.return_value = self._mock_vibeconnect_response(self.valid_claims)

        resp = self.client.post(
            '/api/v1/auth/sso/callback/',
            {"code": "valid_auth_code_abc"},
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertIn('access', data)
        self.assertIn('refresh', data)
        self.assertIn('user', data)
        self.assertEqual(data['user']['id'], self.user.id)
        self.assertEqual(data['user']['email'], self.user.email)

        # Verify outbound VibeConnect request payload
        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode('utf-8'))
        self.assertEqual(payload['code'], 'valid_auth_code_abc')
        self.assertEqual(payload['client_identifier'], 'pilot_lms_client')
        self.assertNotIn('code_verifier', payload)

    @patch('urllib.request.urlopen')
    def test_pkce_backward_compatibility(self, mock_urlopen):
        mock_urlopen.return_value = self._mock_vibeconnect_response(self.valid_claims)

        resp = self.client.post(
            '/api/v1/auth/sso/callback/',
            {"code": "valid_auth_code_abc", "code_verifier": "verifier_abc"},
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)

        # Verify outbound payload includes forwarded code_verifier
        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode('utf-8'))
        self.assertEqual(payload['code'], 'valid_auth_code_abc')
        self.assertEqual(payload['client_identifier'], 'pilot_lms_client')
        self.assertEqual(payload['code_verifier'], 'verifier_abc')

    @patch('urllib.request.urlopen')
    def test_blank_code_verifier_treated_as_no_pkce(self, mock_urlopen):
        mock_urlopen.return_value = self._mock_vibeconnect_response(self.valid_claims)

        resp = self.client.post(
            '/api/v1/auth/sso/callback/',
            {"code": "valid_auth_code_abc", "code_verifier": "   "},
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)

        # Blank code_verifier should be omitted from outbound payload
        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode('utf-8'))
        self.assertNotIn('code_verifier', payload)

    # ─── 3. MALFORMED VIBECONNECT RESPONSE ───────────────────────────────────

    @patch('urllib.request.urlopen')
    def test_malformed_vibeconnect_response_handled_cleanly(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"<html>502 Bad Gateway</html>"
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        resp = self.client.post(
            '/api/v1/auth/sso/callback/',
            {"code": "code_1", "code_verifier": "verifier_1"},
            content_type='application/json'
        )
        self.assertIn(resp.status_code, [403, 500, 502])
        self.assertEqual(resp.json()['error'], 'malformed_response')

    # ─── 4. VIBECONNECT 401 UNAUTHORIZED ─────────────────────────────────────

    @patch('urllib.request.urlopen')
    def test_vibeconnect_401_returns_unauthorized(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url='https://mock-vibeconnect.internal/api/v1/sso/validate/',
            code=401,
            msg='Unauthorized',
            hdrs={},
            fp=BytesIO(b'{"detail": "Invalid connector token"}')
        )

        resp = self.client.post(
            '/api/v1/auth/sso/callback/',
            {"code": "code_1", "code_verifier": "verifier_1"},
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()['error'], 'sso_unauthorized')

    # ─── 5. VIBECONNECT INVALID/EXPIRED CODE ─────────────────────────────────

    @patch('urllib.request.urlopen')
    def test_vibeconnect_invalid_code_returns_sso_failed(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url='https://mock-vibeconnect.internal/api/v1/sso/validate/',
            code=400,
            msg='Bad Request',
            hdrs={},
            fp=BytesIO(b'{"error": "invalid_grant", "detail": "Code expired"}')
        )

        resp = self.client.post(
            '/api/v1/auth/sso/callback/',
            {"code": "expired_code", "code_verifier": "verifier_1"},
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()['error'], 'sso_failed')

    # ─── 6. INVALID AUDIENCE ─────────────────────────────────────────────────

    @patch('urllib.request.urlopen')
    def test_invalid_audience_rejected_with_403(self, mock_urlopen):
        bad_claims = dict(self.valid_claims)
        bad_claims['audience'] = 'untrusted-rogue-audience'
        mock_urlopen.return_value = self._mock_vibeconnect_response(bad_claims)

        resp = self.client.post(
            '/api/v1/auth/sso/callback/',
            {"code": "valid_code", "code_verifier": "verifier_1"},
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()['error'], 'invalid_audience')

    # ─── 7. INVALID PRODUCT CODE ─────────────────────────────────────────────

    @patch('urllib.request.urlopen')
    def test_invalid_product_rejected_with_403(self, mock_urlopen):
        bad_claims = dict(self.valid_claims)
        bad_claims['product'] = {"id": "prod_hrms", "code": "hrms", "name": "HRMS"}
        mock_urlopen.return_value = self._mock_vibeconnect_response(bad_claims)

        resp = self.client.post(
            '/api/v1/auth/sso/callback/',
            {"code": "valid_code", "code_verifier": "verifier_1"},
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()['error'], 'invalid_product')

    # ─── 8. UNMAPPED TENANT ──────────────────────────────────────────────────

    @patch('urllib.request.urlopen')
    def test_unmapped_tenant_rejected_with_403(self, mock_urlopen):
        unmapped_claims = dict(self.valid_claims)
        unmapped_claims['organization'] = {
            "id": "unmapped_tenant_9999",
            "code": "unknown",
            "name": "Unknown Corp"
        }
        mock_urlopen.return_value = self._mock_vibeconnect_response(unmapped_claims)

        resp = self.client.post(
            '/api/v1/auth/sso/callback/',
            {"code": "valid_code", "code_verifier": "verifier_1"},
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()['error'], 'unmapped_tenant')

    # ─── 9. UNMAPPED USER ────────────────────────────────────────────────────

    @patch('urllib.request.urlopen')
    def test_unmapped_user_rejected_with_403(self, mock_urlopen):
        unmapped_claims = dict(self.valid_claims)
        unmapped_claims['user'] = {
            "id": "unmapped_user_8888",
            "email": "new.user@acme.com",
            "full_name": "New User"
        }
        mock_urlopen.return_value = self._mock_vibeconnect_response(unmapped_claims)

        resp = self.client.post(
            '/api/v1/auth/sso/callback/',
            {"code": "valid_code", "code_verifier": "verifier_1"},
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()['error'], 'unmapped_user')

    # ─── 10. CROSS-TENANT MISMATCH ───────────────────────────────────────────

    @patch('urllib.request.urlopen')
    def test_cross_tenant_mismatch_rejected_with_403(self, mock_urlopen):
        # Map other_ext_tenant_id to other_org
        create_tenant_mapping("vibeconnect", self.other_ext_tenant_id, self.other_org)

        # Claims claim to be from other_ext_tenant_id, but the user is mapped to self.org
        mismatch_claims = dict(self.valid_claims)
        mismatch_claims['organization'] = {
            "id": self.other_ext_tenant_id,
            "code": "other",
            "name": "Other Corp"
        }
        # user self.ext_user_id is mapped to self.org
        mock_urlopen.return_value = self._mock_vibeconnect_response(mismatch_claims)

        resp = self.client.post(
            '/api/v1/auth/sso/callback/',
            {"code": "valid_code", "code_verifier": "verifier_1"},
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()['error'], 'tenant_mismatch')

    # ─── 11. INACTIVE USER ───────────────────────────────────────────────────

    @patch('urllib.request.urlopen')
    def test_inactive_user_rejected_with_403(self, mock_urlopen):
        # Map inactive user
        create_user_mapping("vibeconnect", "usr_inactive_111", self.org, self.inactive_user)

        inactive_claims = dict(self.valid_claims)
        inactive_claims['user'] = {
            "id": "usr_inactive_111",
            "email": self.inactive_user.email,
            "full_name": "Inactive User"
        }
        mock_urlopen.return_value = self._mock_vibeconnect_response(inactive_claims)

        resp = self.client.post(
            '/api/v1/auth/sso/callback/',
            {"code": "valid_code", "code_verifier": "verifier_1"},
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()['error'], 'account_frozen')

    # ─── 12. INACTIVE ORGANIZATION ───────────────────────────────────────────

    @patch('urllib.request.urlopen')
    def test_inactive_organization_rejected_with_403(self, mock_urlopen):
        # Map inactive organization
        create_tenant_mapping("vibeconnect", "org_frozen_777", self.inactive_org)
        # Create user in inactive organization
        frozen_user = User.objects.create_user(
            username="frozen.john@frozen.com",
            email="frozen.john@frozen.com",
            organization=self.inactive_org,
            is_active=True
        )
        create_user_mapping("vibeconnect", "usr_frozen_222", self.inactive_org, frozen_user)

        frozen_claims = dict(self.valid_claims)
        frozen_claims['organization'] = {"id": "org_frozen_777", "code": "frozen", "name": "Frozen Corp"}
        frozen_claims['user'] = {"id": "usr_frozen_222", "email": frozen_user.email, "full_name": "Frozen User"}
        mock_urlopen.return_value = self._mock_vibeconnect_response(frozen_claims)

        resp = self.client.post(
            '/api/v1/auth/sso/callback/',
            {"code": "valid_code", "code_verifier": "verifier_1"},
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()['error'], 'account_frozen')

    # ─── 13 & 14. SUCCESSFUL SESSION CREATION & CLAIM EMBEDDING ──────────────

    @patch('urllib.request.urlopen')
    def test_successful_mapped_user_returns_tokens_with_claims(self, mock_urlopen):
        mock_urlopen.return_value = self._mock_vibeconnect_response(self.valid_claims)

        resp = self.client.post(
            '/api/v1/auth/sso/callback/',
            {"code": "valid_auth_code_abc", "code_verifier": "valid_pkce_verifier_xyz"},
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertIn('access', data)
        self.assertIn('refresh', data)
        self.assertIn('user', data)
        self.assertEqual(data['user']['id'], self.user.id)
        self.assertEqual(data['user']['email'], self.user.email)

        # Inspect decoded access token claims
        token = AccessToken(data['access'])
        self.assertEqual(int(token['user_id']), self.user.id)
        self.assertEqual(token['org_id'], self.org.id)
        self.assertEqual(token['is_platform_super_admin'], False)

    # ─── 15 & 16. M2M SECRET CONFIDENTIALITY ────────────────────────────────

    @patch('urllib.request.urlopen')
    def test_m2m_secret_sent_in_header_only_and_never_leaked(self, mock_urlopen):
        mock_urlopen.return_value = self._mock_vibeconnect_response(self.valid_claims)

        resp = self.client.post(
            '/api/v1/auth/sso/callback/',
            {"code": "valid_auth_code_abc", "code_verifier": "valid_pkce_verifier_xyz"},
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)

        # Verify outbound call used Authorization Bearer header
        req = mock_urlopen.call_args[0][0]
        auth_header = req.get_header('Authorization')
        self.assertEqual(auth_header, 'Bearer test-super-secret-m2m-token-12345')

        # Verify M2M secret is never leaked in the HTTP response body
        resp_text = resp.content.decode('utf-8')
        self.assertNotIn('test-super-secret-m2m-token-12345', resp_text)

    # ─── 17 & 18. IDENTITY INDEPENDENCE ──────────────────────────────────────

    @patch('urllib.request.urlopen')
    def test_external_identity_and_local_user_id_remain_independent(self, mock_urlopen):
        mock_urlopen.return_value = self._mock_vibeconnect_response(self.valid_claims)

        resp = self.client.post(
            '/api/v1/auth/sso/callback/',
            {"code": "valid_auth_code_abc", "code_verifier": "valid_pkce_verifier_xyz"},
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Local user ID is integer primary key
        self.assertEqual(data['user']['id'], self.user.id)
        self.assertIsInstance(data['user']['id'], int)

        # External mapping preserves VibeConnect PlatformUser UUID
        mapping = ExternalUserMapping.objects.get(user=self.user)
        self.assertEqual(mapping.external_user_id, self.ext_user_id)
        self.assertNotEqual(mapping.external_user_id, str(self.user.id))

    # ─── 19. NO EMAIL-BASED IDENTITY SUBSTITUTION ────────────────────────────

    @patch('urllib.request.urlopen')
    def test_no_email_based_identity_substitution(self, mock_urlopen):
        # Create an unmapped user with matching email
        unmapped_user = User.objects.create_user(
            username="unmapped.email@acme.com",
            email="unmapped.email@acme.com",
            organization=self.org,
            is_active=True
        )

        claims = dict(self.valid_claims)
        # External user ID does NOT match any ExternalUserMapping, even though email matches unmapped_user
        claims['user'] = {
            "id": "usr_unmapped_random_uuid",
            "email": unmapped_user.email,
            "full_name": "Unmapped User"
        }
        mock_urlopen.return_value = self._mock_vibeconnect_response(claims)

        resp = self.client.post(
            '/api/v1/auth/sso/callback/',
            {"code": "valid_auth_code_abc", "code_verifier": "valid_pkce_verifier_xyz"},
            content_type='application/json'
        )
        # Must be rejected because external_user_id is not mapped; cannot silently claim unmapped_user by email!
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()['error'], 'unmapped_user')
        self.assertFalse(ExternalUserMapping.objects.filter(user=unmapped_user).exists())

    # ─── 20. NO REAL NETWORK CALLS ───────────────────────────────────────────

    def test_network_isolation_guaranteed(self):
        # Without mocking urllib.request.urlopen, invoking the service points to mock domain
        # which would fail if called. This verifies mock coverage.
        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_urlopen.return_value = self._mock_vibeconnect_response(self.valid_claims)
            resp = self.client.post(
                '/api/v1/auth/sso/callback/',
                {"code": "test_code", "code_verifier": "test_verifier"},
                content_type='application/json'
            )
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(mock_urlopen.called)


@override_settings(
    VIBECONNECT_M2M_SECRET='test-super-secret-m2m-token-12345',
    VIBECONNECT_LAUNCH_GRANT_SECRET='test-dedicated-launch-grant-secret-67890',
    FRONTEND_URL='http://localhost:8080'
)
class LaunchGrantAndExchangeTestCase(TestCase):
    def setUp(self):
        from organizations.models import Role
        from master_setup.models import Workspace

        admin_ws, _ = Workspace.objects.get_or_create(key='admin', defaults={'label': 'Administration', 'order': 1})
        learner_ws, _ = Workspace.objects.get_or_create(key='learner', defaults={'label': 'Learning', 'order': 2})

        # 1. Organization & Roles
        self.org = Organization.objects.create(
            name="Grant Test Org",
            company_name="Grant Test Org",
            entity_name="Grant Test Org",
            sub_domain="grant-test-org",
            status="Active"
        )
        self.inactive_org = Organization.objects.create(
            name="Inactive Org",
            company_name="Inactive Org",
            entity_name="Inactive Org",
            sub_domain="inactive-org",
            status="Inactive"
        )
        self.other_org = Organization.objects.create(
            name="Other Org",
            company_name="Other Org",
            entity_name="Other Org",
            sub_domain="other-org",
            status="Active"
        )

        self.admin_role = Role.objects.create(
            organization=self.org,
            name="Organization Admin",
            is_admin_role=True,
            is_default=True
        )
        self.admin_role.workspaces.set([admin_ws, learner_ws])

        # 2. Users
        self.admin_user = User.objects.create_user(
            username="admin@grant.com",
            email="admin@grant.com",
            organization=self.org,
            role=self.admin_role,
            is_active=True
        )
        self.member_user = User.objects.create_user(
            username="member@grant.com",
            email="member@grant.com",
            organization=self.org,
            role=None,
            is_active=True
        )
        self.inactive_user = User.objects.create_user(
            username="inactive@grant.com",
            email="inactive@grant.com",
            organization=self.org,
            is_active=False
        )
        self.cross_tenant_user = User.objects.create_user(
            username="cross@other.com",
            email="cross@other.com",
            organization=self.other_org,
            is_active=True
        )
        showcase_superadmin_email = getattr(settings, 'LMS_SHOWCASE_SUPERADMIN_EMAIL', 'superadmin@gmail.com').strip().lower()
        self.super_admin_user = User.objects.create_superuser(
            username=showcase_superadmin_email,
            email=showcase_superadmin_email,
            password="SuperPassword123!",
            organization=self.org,
            is_platform_super_admin=True
        )

        # 3. Phase 5B Mappings
        self.ext_tenant_id = "org_grant_uuid_001"
        self.ext_admin_id = "usr_grant_admin_001"
        self.ext_member_id = "usr_grant_member_002"
        self.ext_inactive_id = "usr_grant_inactive_003"
        self.ext_cross_id = "usr_grant_cross_004"
        self.ext_inactive_tenant_id = "org_grant_inactive_tenant_005"
        self.ext_super_admin_id = "usr_grant_super_006"

        create_tenant_mapping("vibeconnect", self.ext_tenant_id, self.org)
        create_tenant_mapping("vibeconnect", self.ext_inactive_tenant_id, self.inactive_org)
        create_user_mapping("vibeconnect", self.ext_admin_id, self.org, self.admin_user)
        create_user_mapping("vibeconnect", self.ext_member_id, self.org, self.member_user)
        create_user_mapping("vibeconnect", self.ext_inactive_id, self.org, self.inactive_user)
        create_user_mapping("vibeconnect", self.ext_cross_id, self.other_org, self.cross_tenant_user)
        create_user_mapping("vibeconnect", self.ext_super_admin_id, self.org, self.super_admin_user)

        self.provisioning_auth = "Bearer test-super-secret-m2m-token-12345"
        self.launch_grant_auth = "Bearer test-dedicated-launch-grant-secret-67890"

    def _post_grant(self, payload, auth_header=None):
        headers = {}
        if auth_header is not None:
            headers['HTTP_AUTHORIZATION'] = auth_header
        return self.client.post(
            '/api/v1/integration/launch-grant/',
            data=json.dumps(payload),
            content_type='application/json',
            **headers
        )

    def _post_exchange(self, code):
        return self.client.post(
            '/api/v1/auth/sso/vibeconnect/exchange/',
            data=json.dumps({"code": code}),
            content_type='application/json'
        )

    # ─── M2M Authentication Tests ────────────────────────────────────────────

    def test_01_grant_requires_m2m_authentication(self):
        resp = self._post_grant({
            "external_tenant_id": self.ext_tenant_id,
            "external_user_id": self.ext_admin_id
        })
        self.assertEqual(resp.status_code, 401)

    def test_02_grant_rejects_invalid_m2m_token(self):
        resp = self._post_grant(
            {
                "external_tenant_id": self.ext_tenant_id,
                "external_user_id": self.ext_admin_id
            },
            auth_header="Bearer wrong-secret"
        )
        self.assertEqual(resp.status_code, 401)

    def test_02b_grant_rejects_provisioning_m2m_token_secret_isolation(self):
        """Dedicated secret isolation: provisioning secret MUST NOT be accepted by launch-grant endpoint."""
        resp = self._post_grant(
            {
                "external_tenant_id": self.ext_tenant_id,
                "external_user_id": self.ext_admin_id
            },
            auth_header=self.provisioning_auth
        )
        self.assertEqual(resp.status_code, 401)

    # ─── Grant Creation Success & Isolation ──────────────────────────────────

    def test_03_grant_creation_success_standard_admin(self):
        resp = self._post_grant(
            {
                "external_tenant_id": self.ext_tenant_id,
                "external_user_id": self.ext_admin_id,
                "context": "standard",
                "target_route": "/org-admin/courses"
            },
            auth_header=self.launch_grant_auth
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertIn("callback_url", data)
        self.assertIn("http://localhost:8080/sso/vibeconnect/callback?code=", data["callback_url"])
        self.assertEqual(data["expires_in"], 60)
        self.assertEqual(data["context"], "standard")

    def test_04_grant_creation_success_showcase_superadmin(self):
        resp = self._post_grant(
            {
                "external_tenant_id": self.ext_tenant_id,
                "external_user_id": self.ext_super_admin_id,
                "context": "showcase",
                "target_route": "/super-admin/dashboard"
            },
            auth_header=self.launch_grant_auth
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["context"], "showcase")
        code = data["callback_url"].split("code=")[1]
        exch = self._post_exchange(code)
        self.assertEqual(exch.status_code, 200)
        self.assertEqual(exch.json()["target_route"], "/super-admin/dashboard")
        self.assertTrue(exch.json()["user"]["is_platform_super_admin"])

    def test_04b_grant_rejects_showcase_for_non_superadmin(self):
        resp = self._post_grant(
            {
                "external_tenant_id": self.ext_tenant_id,
                "external_user_id": self.ext_member_id,
                "context": "showcase"
            },
            auth_header=self.launch_grant_auth
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"], "forbidden")

    def test_04c_grant_rejects_standard_tenant_launch_for_superadmin(self):
        resp = self._post_grant(
            {
                "external_tenant_id": self.ext_tenant_id,
                "external_user_id": self.ext_super_admin_id,
                "context": "standard"
            },
            auth_header=self.launch_grant_auth
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"], "forbidden")

    def test_05_grant_rejects_unmapped_tenant(self):
        resp = self._post_grant(
            {
                "external_tenant_id": "unmapped_tenant_999",
                "external_user_id": self.ext_admin_id
            },
            auth_header=self.launch_grant_auth
        )
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["error"], "tenant_not_found")

    def test_06_grant_rejects_unmapped_user(self):
        resp = self._post_grant(
            {
                "external_tenant_id": self.ext_tenant_id,
                "external_user_id": "unmapped_user_999"
            },
            auth_header=self.launch_grant_auth
        )
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["error"], "user_not_found")

    def test_07_grant_rejects_inactive_organization(self):
        resp = self._post_grant(
            {
                "external_tenant_id": self.ext_inactive_tenant_id,
                "external_user_id": self.ext_admin_id
            },
            auth_header=self.launch_grant_auth
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"], "account_frozen")

    def test_08_grant_rejects_inactive_user(self):
        resp = self._post_grant(
            {
                "external_tenant_id": self.ext_tenant_id,
                "external_user_id": self.ext_inactive_id
            },
            auth_header=self.launch_grant_auth
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"], "account_frozen")

    def test_09_grant_rejects_cross_tenant_mismatch(self):
        resp = self._post_grant(
            {
                "external_tenant_id": self.ext_tenant_id,
                "external_user_id": self.ext_cross_id  # belongs to other_org
            },
            auth_header=self.launch_grant_auth
        )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["error"], "conflict")

    # ─── Target Route & Role Boundary Tests ──────────────────────────────────

    def test_09b_learner_cannot_request_admin_target_route(self):
        """A non-admin learner requesting /org-admin has target_route scrubbed to empty."""
        resp = self._post_grant(
            {
                "external_tenant_id": self.ext_tenant_id,
                "external_user_id": self.ext_member_id,
                "target_route": "/org-admin/roles"
            },
            auth_header=self.launch_grant_auth
        )
        self.assertEqual(resp.status_code, 201)
        code = resp.json()["callback_url"].split("code=")[1]
        exch_resp = self._post_exchange(code)
        self.assertEqual(exch_resp.status_code, 200)
        self.assertIsNone(exch_resp.json()["target_route"])

    def test_09c_superadmin_target_route_strictly_prohibited(self):
        """Any request for /super-admin is stripped for security."""
        resp = self._post_grant(
            {
                "external_tenant_id": self.ext_tenant_id,
                "external_user_id": self.ext_admin_id,
                "target_route": "/super-admin/dashboard"
            },
            auth_header=self.launch_grant_auth
        )
        self.assertEqual(resp.status_code, 201)
        code = resp.json()["callback_url"].split("code=")[1]
        exch_resp = self._post_exchange(code)
        self.assertEqual(exch_resp.status_code, 200)
        self.assertIsNone(exch_resp.json()["target_route"])

    def test_09d_external_target_route_strictly_prohibited(self):
        """External URL or protocol-relative target routes are stripped."""
        resp = self._post_grant(
            {
                "external_tenant_id": self.ext_tenant_id,
                "external_user_id": self.ext_admin_id,
                "target_route": "https://evil.com/phish"
            },
            auth_header=self.launch_grant_auth
        )
        self.assertEqual(resp.status_code, 201)
        code = resp.json()["callback_url"].split("code=")[1]
        exch_resp = self._post_exchange(code)
        self.assertEqual(exch_resp.status_code, 200)
        self.assertIsNone(exch_resp.json()["target_route"])

    # ─── Code Exchange & Session Tests ───────────────────────────────────────

    def test_10_exchange_success_issues_jwt_tokens(self):
        grant_resp = self._post_grant(
            {
                "external_tenant_id": self.ext_tenant_id,
                "external_user_id": self.ext_admin_id,
                "target_route": "/org-admin"
            },
            auth_header=self.launch_grant_auth
        )
        callback_url = grant_resp.json()["callback_url"]
        code = callback_url.split("code=")[1]

        # Exchange code
        exch_resp = self._post_exchange(code)
        self.assertEqual(exch_resp.status_code, 200)
        data = exch_resp.json()
        self.assertIn("access", data)
        self.assertIn("refresh", data)
        self.assertEqual(data["target_route"], "/org-admin")
        self.assertEqual(data["user"]["id"], self.admin_user.id)
        self.assertTrue(data["user"]["role"]["is_admin_role"])
        self.assertFalse(data["user"]["is_platform_super_admin"])

    def test_11_exchange_single_use_atomic_replay_protection(self):
        grant_resp = self._post_grant(
            {
                "external_tenant_id": self.ext_tenant_id,
                "external_user_id": self.ext_member_id
            },
            auth_header=self.launch_grant_auth
        )
        code = grant_resp.json()["callback_url"].split("code=")[1]

        # First redemption must succeed
        exch_resp1 = self._post_exchange(code)
        self.assertEqual(exch_resp1.status_code, 200)

        # Replay must be rejected with HTTP 400
        exch_resp2 = self._post_exchange(code)
        self.assertEqual(exch_resp2.status_code, 400)
        self.assertEqual(exch_resp2.json()["error"], "grant_already_consumed")

    def test_12_exchange_rejects_expired_grant(self):
        import hashlib
        from datetime import timedelta
        from django.utils import timezone
        from organizations.models import LmsLaunchGrant

        code = "expired_secret_code_123"
        code_hash = hashlib.sha256(code.encode('utf-8')).hexdigest()
        past_time = timezone.now() - timedelta(seconds=10)

        LmsLaunchGrant.objects.create(
            code_hash=code_hash,
            organization=self.org,
            user=self.member_user,
            is_consumed=False,
            expires_at=past_time
        )

        exch_resp = self._post_exchange(code)
        self.assertEqual(exch_resp.status_code, 400)
        self.assertEqual(exch_resp.json()["error"], "grant_expired")

    def test_13_exchange_rejects_bogus_code(self):
        exch_resp = self._post_exchange("non_existent_code_99999")
        self.assertEqual(exch_resp.status_code, 400)
        self.assertEqual(exch_resp.json()["error"], "invalid_grant")

