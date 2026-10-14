import json
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from organizations.models import Organization, ExternalTenantMapping, ExternalUserMapping, Role
from organizations.mapping_services import (
    create_tenant_mapping,
    create_user_mapping,
    lookup_tenant_mapping,
    lookup_user_mapping,
    MappingConflictError,
)
from organizations.provisioning_services import (
    provision_tenant,
    provision_user,
    ProvisioningValidationError,
    TenantNotFoundError,
    ProvisioningConflictError,
)

User = get_user_model()

TEST_M2M_SECRET = "test-super-secret-m2m-provisioning-token-99999"


@override_settings(VIBECONNECT_M2M_SECRET=TEST_M2M_SECRET)
class LMSProvisioningContractTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.m2m_auth_header = f"Bearer {TEST_M2M_SECRET}"

        # Sample initial tenant & user
        self.org1 = Organization.objects.create(
            name="Org One",
            company_name="Org One",
            entity_name="Org One",
            sub_domain="org-one",
            status="Active"
        )
        self.org2 = Organization.objects.create(
            name="Org Two",
            company_name="Org Two",
            entity_name="Org Two",
            sub_domain="org-two",
            status="Active"
        )

        self.normal_user = User.objects.create_user(
            username="normal.user@orgone.com",
            email="normal.user@orgone.com",
            password="StrongPassword123!",
            organization=self.org1,
            is_active=True
        )

        self.super_admin = User.objects.create_superuser(
            username="superadmin@platform.com",
            email="superadmin@platform.com",
            password="SuperPassword123!",
            is_platform_super_admin=True
        )

    def _post_tenant(self, payload, auth_header=None):
        headers = {}
        if auth_header is not None:
            headers['HTTP_AUTHORIZATION'] = auth_header
        return self.client.post(
            '/api/v1/integration/tenants/provision/',
            data=json.dumps(payload),
            content_type='application/json',
            **headers
        )

    def _post_user(self, payload, auth_header=None):
        headers = {}
        if auth_header is not None:
            headers['HTTP_AUTHORIZATION'] = auth_header
        return self.client.post(
            '/api/v1/integration/users/provision/',
            data=json.dumps(payload),
            content_type='application/json',
            **headers
        )

    # =========================================================================
    # TENANT PROVISIONING TESTS (1 - 10)
    # =========================================================================

    def test_01_tenant_m2m_authentication_required(self):
        """1. Request without M2M token must be rejected with 401."""
        resp = self._post_tenant({
            "external_tenant_id": "org_uuid_101",
            "name": "Acme Corp",
            "code": "acme",
            "status": "active"
        })
        self.assertEqual(resp.status_code, 401)

    def test_02_valid_tenant_provisioning_succeeds(self):
        """2. Valid tenant provisioning creates organization and mapping."""
        payload = {
            "external_tenant_id": "org_uuid_102",
            "name": "Wayne Enterprises",
            "code": "wayne",
            "status": "active"
        }
        resp = self._post_tenant(payload, auth_header=self.m2m_auth_header)
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["external_tenant_id"], "org_uuid_102")
        self.assertIn("lms_organization_id", data)
        self.assertEqual(data["status"], "active")
        self.assertEqual(data["action_taken"], "created")

        # Verify DB
        org = Organization.objects.get(id=data["lms_organization_id"])
        self.assertEqual(org.name, "Wayne Enterprises")
        self.assertEqual(org.status, "Active")
        mapping = lookup_tenant_mapping("vibeconnect", "org_uuid_102")
        self.assertIsNotNone(mapping)
        self.assertEqual(mapping.organization_id, org.id)

    def test_03_duplicate_tenant_provisioning_is_idempotent(self):
        """3. Duplicate tenant provisioning returns 200 with existing organization."""
        payload = {
            "external_tenant_id": "org_uuid_103",
            "name": "Stark Industries",
            "code": "stark",
            "status": "active"
        }
        resp1 = self._post_tenant(payload, auth_header=self.m2m_auth_header)
        self.assertEqual(resp1.status_code, 201)
        org_id_1 = resp1.json()["lms_organization_id"]

        resp2 = self._post_tenant(payload, auth_header=self.m2m_auth_header)
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()
        self.assertEqual(data2["lms_organization_id"], org_id_1)
        self.assertEqual(data2["action_taken"], "existing")

        # DB must have exactly ONE mapping and ONE organization
        self.assertEqual(ExternalTenantMapping.objects.filter(external_tenant_id="org_uuid_103").count(), 1)

    def test_04_mapping_created_on_tenant_provision(self):
        """4. Verify ExternalTenantMapping record exists with correct provider and external ID."""
        payload = {
            "external_tenant_id": "org_uuid_104",
            "name": "Cyberdyne Systems",
            "code": "cyberdyne",
            "status": "active"
        }
        resp = self._post_tenant(payload, auth_header=self.m2m_auth_header)
        self.assertEqual(resp.status_code, 201)

        mapping = ExternalTenantMapping.objects.get(external_tenant_id="org_uuid_104")
        self.assertEqual(mapping.provider, "vibeconnect")
        self.assertEqual(mapping.organization.name, "Cyberdyne Systems")

    def test_05_existing_tenant_mapping_reused(self):
        """5. Pre-existing tenant mapping is looked up and reused."""
        create_tenant_mapping("vibeconnect", "org_uuid_105", self.org1)

        payload = {
            "external_tenant_id": "org_uuid_105",
            "name": "Org One Updated",
            "code": "org-one",
            "status": "active"
        }
        resp = self._post_tenant(payload, auth_header=self.m2m_auth_header)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["lms_organization_id"], self.org1.id)
        self.assertEqual(data["action_taken"], "existing")

    def test_06_invalid_payload_rejected_tenant(self):
        """6. Missing required tenant fields return 400 Bad Request."""
        # Missing external_tenant_id
        resp = self._post_tenant({"name": "Test", "code": "t", "status": "active"}, auth_header=self.m2m_auth_header)
        self.assertEqual(resp.status_code, 400)

        # Blank code
        resp = self._post_tenant({"external_tenant_id": "id1", "name": "Test", "code": "   ", "status": "active"}, auth_header=self.m2m_auth_header)
        self.assertEqual(resp.status_code, 400)

        # Non-dict body
        resp = self.client.post('/api/v1/integration/tenants/provision/', data='invalid', content_type='application/json', HTTP_AUTHORIZATION=self.m2m_auth_header)
        self.assertEqual(resp.status_code, 400)

    def test_07_invalid_status_rejected_tenant(self):
        """7. Status outside allowed set (active, inactive, suspended) is rejected."""
        payload = {
            "external_tenant_id": "org_uuid_107",
            "name": "Invalid Status Org",
            "code": "invalid-status",
            "status": "archived"  # Not allowed
        }
        resp = self._post_tenant(payload, auth_header=self.m2m_auth_header)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Allowed values", resp.json()["detail"])

    def test_08_concurrent_duplicate_provisioning_safe_tenant(self):
        """8. If concurrent request throws MappingConflictError, existing mapping is cleanly returned."""
        create_tenant_mapping("vibeconnect", "org_uuid_108", self.org1)

        with patch('organizations.provisioning_services.create_tenant_mapping', side_effect=MappingConflictError("Simulated race")):
            org, mapping, action = provision_tenant(
                provider='vibeconnect',
                external_tenant_id='org_uuid_108',
                name='Org One Race',
                code='org-one',
                status='active'
            )
            self.assertEqual(org.id, self.org1.id)
            self.assertEqual(action, "existing")

    def test_09_tenant_status_update_works(self):
        """9. Incoming status changes synchronize cleanly to LMS organization."""
        payload = {
            "external_tenant_id": "org_uuid_109",
            "name": "Status Test Org",
            "code": "status-org",
            "status": "active"
        }
        resp1 = self._post_tenant(payload, auth_header=self.m2m_auth_header)
        self.assertEqual(resp1.status_code, 201)
        org = Organization.objects.get(id=resp1.json()["lms_organization_id"])
        self.assertEqual(org.status, "Active")

        # Update to suspended
        payload["status"] = "suspended"
        resp2 = self._post_tenant(payload, auth_header=self.m2m_auth_header)
        self.assertEqual(resp2.status_code, 200)
        org.refresh_from_db()
        self.assertEqual(org.status, "Suspended")
        self.assertEqual(resp2.json()["status"], "suspended")

        # Update to inactive
        payload["status"] = "inactive"
        resp3 = self._post_tenant(payload, auth_header=self.m2m_auth_header)
        self.assertEqual(resp3.status_code, 200)
        org.refresh_from_db()
        self.assertEqual(org.status, "Inactive")

    def test_10_unauthorized_request_rejected_tenant(self):
        """10. Bad Bearer token rejected with 401."""
        resp = self._post_tenant(
            {"external_tenant_id": "org_uuid_110", "name": "Bad Auth", "code": "bad", "status": "active"},
            auth_header="Bearer wrong-secret-token"
        )
        self.assertEqual(resp.status_code, 401)

    # =========================================================================
    # USER PROVISIONING TESTS (11 - 23)
    # =========================================================================

    def test_11_user_m2m_authentication_required(self):
        """11. Request without M2M token must be rejected with 401."""
        resp = self._post_user({
            "external_tenant_id": "org_uuid_101",
            "external_user_id": "usr_uuid_201",
            "email": "user@example.com",
            "is_active": True
        })
        self.assertEqual(resp.status_code, 401)

    def test_12_tenant_mapping_must_exist(self):
        """12. Provisioning a user for an unmapped tenant returns 404."""
        resp = self._post_user({
            "external_tenant_id": "unmapped_org_uuid_999",
            "external_user_id": "usr_uuid_202",
            "email": "orphan@example.com",
            "first_name": "Orphan",
            "last_name": "User",
            "is_active": True
        }, auth_header=self.m2m_auth_header)
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["error"], "tenant_not_found")

    def test_13_new_user_provisioning_succeeds(self):
        """13. Provisioning a new user creates LMS User and ExternalUserMapping."""
        create_tenant_mapping("vibeconnect", "org_uuid_tenant_13", self.org1)

        payload = {
            "external_tenant_id": "org_uuid_tenant_13",
            "external_user_id": "usr_uuid_203",
            "email": "clark.kent@dailyplanet.com",
            "first_name": "Clark",
            "last_name": "Kent",
            "is_active": True
        }
        resp = self._post_user(payload, auth_header=self.m2m_auth_header)
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["external_tenant_id"], "org_uuid_tenant_13")
        self.assertEqual(data["external_user_id"], "usr_uuid_203")
        self.assertEqual(data["email"], "clark.kent@dailyplanet.com")
        self.assertTrue(data["is_active"])
        self.assertEqual(data["action_taken"], "created")

        # Verify DB
        user = User.objects.get(id=data["lms_user_id"])
        self.assertEqual(user.first_name, "Clark")
        self.assertEqual(user.last_name, "Kent")
        self.assertEqual(user.organization_id, self.org1.id)
        self.assertFalse(user.is_platform_super_admin)
        self.assertFalse(user.has_usable_password())

        mapping = lookup_user_mapping("vibeconnect", "usr_uuid_203")
        self.assertIsNotNone(mapping)
        self.assertEqual(mapping.user_id, user.id)
        self.assertEqual(mapping.organization_id, self.org1.id)

    def test_14_duplicate_user_provisioning_is_idempotent(self):
        """14. Repeated user provisioning returns 200 with existing user."""
        create_tenant_mapping("vibeconnect", "org_uuid_tenant_14", self.org1)

        payload = {
            "external_tenant_id": "org_uuid_tenant_14",
            "external_user_id": "usr_uuid_204",
            "email": "bruce.wayne@waynecorp.com",
            "first_name": "Bruce",
            "last_name": "Wayne",
            "is_active": True
        }
        resp1 = self._post_user(payload, auth_header=self.m2m_auth_header)
        self.assertEqual(resp1.status_code, 201)
        user_id_1 = resp1.json()["lms_user_id"]

        resp2 = self._post_user(payload, auth_header=self.m2m_auth_header)
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()
        self.assertEqual(data2["lms_user_id"], user_id_1)
        self.assertEqual(data2["action_taken"], "existing")

        # Verify exactly one user in DB
        self.assertEqual(User.objects.filter(email="bruce.wayne@waynecorp.com").count(), 1)

    def test_15_user_mapping_created_on_provision(self):
        """15. ExternalUserMapping created with correct relations and provider."""
        create_tenant_mapping("vibeconnect", "org_uuid_tenant_15", self.org1)

        payload = {
            "external_tenant_id": "org_uuid_tenant_15",
            "external_user_id": "usr_uuid_205",
            "email": "barry.allen@ccpd.gov",
            "is_active": True
        }
        resp = self._post_user(payload, auth_header=self.m2m_auth_header)
        self.assertEqual(resp.status_code, 201)

        mapping = ExternalUserMapping.objects.get(external_user_id="usr_uuid_205")
        self.assertEqual(mapping.provider, "vibeconnect")
        self.assertEqual(mapping.organization_id, self.org1.id)
        self.assertEqual(mapping.user.email, "barry.allen@ccpd.gov")

    def test_16_existing_mapping_reused_user(self):
        """16. Existing user mapping is looked up and reused."""
        create_tenant_mapping("vibeconnect", "org_uuid_tenant_16", self.org1)
        create_user_mapping("vibeconnect", "usr_uuid_206", self.org1, self.normal_user)

        payload = {
            "external_tenant_id": "org_uuid_tenant_16",
            "external_user_id": "usr_uuid_206",
            "email": self.normal_user.email,
            "first_name": "Updated",
            "last_name": "Name",
            "is_active": True
        }
        resp = self._post_user(payload, auth_header=self.m2m_auth_header)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["lms_user_id"], self.normal_user.id)
        self.assertEqual(data["action_taken"], "existing")

        self.normal_user.refresh_from_db()
        self.assertEqual(self.normal_user.first_name, "Updated")

    def test_17_same_email_in_same_tenant_handled_safely(self):
        """17. Existing user with same email in same tenant is safely linked if unmapped."""
        create_tenant_mapping("vibeconnect", "org_uuid_tenant_17", self.org1)
        unmapped_user = User.objects.create_user(
            username="unmapped@orgone.com",
            email="unmapped@orgone.com",
            organization=self.org1,
            is_active=True
        )

        payload = {
            "external_tenant_id": "org_uuid_tenant_17",
            "external_user_id": "usr_uuid_207",
            "email": "unmapped@orgone.com",
            "first_name": "Linked",
            "last_name": "User",
            "is_active": True
        }
        resp = self._post_user(payload, auth_header=self.m2m_auth_header)
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["lms_user_id"], unmapped_user.id)

        # Mapping now exists
        mapping = lookup_user_mapping("vibeconnect", "usr_uuid_207")
        self.assertIsNotNone(mapping)
        self.assertEqual(mapping.user_id, unmapped_user.id)

    def test_18_cross_tenant_identity_rejected(self):
        """18. If a user with same email belongs to another organization, reject with conflict 409."""
        create_tenant_mapping("vibeconnect", "org_uuid_tenant_18", self.org2)
        # normal_user belongs to org1!
        payload = {
            "external_tenant_id": "org_uuid_tenant_18",
            "external_user_id": "usr_uuid_208",
            "email": self.normal_user.email,  # belongs to org1
            "is_active": True
        }
        resp = self._post_user(payload, auth_header=self.m2m_auth_header)
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["error"], "conflict")
        self.assertIn("Cross-tenant conflict", resp.json()["detail"])

    def test_19_inactive_user_handled_correctly(self):
        """19. Provisioning with is_active=false sets user active status to false."""
        create_tenant_mapping("vibeconnect", "org_uuid_tenant_19", self.org1)
        payload = {
            "external_tenant_id": "org_uuid_tenant_19",
            "external_user_id": "usr_uuid_209",
            "email": "inactive.test@orgone.com",
            "is_active": False
        }
        resp = self._post_user(payload, auth_header=self.m2m_auth_header)
        self.assertEqual(resp.status_code, 201)
        user = User.objects.get(id=resp.json()["lms_user_id"])
        self.assertFalse(user.is_active)

    def test_20_reactivation_handled_correctly(self):
        """20. Subsequent provision with is_active=true reactivates user."""
        create_tenant_mapping("vibeconnect", "org_uuid_tenant_20", self.org1)
        payload = {
            "external_tenant_id": "org_uuid_tenant_20",
            "external_user_id": "usr_uuid_210",
            "email": "reactivate.test@orgone.com",
            "is_active": False
        }
        resp1 = self._post_user(payload, auth_header=self.m2m_auth_header)
        self.assertEqual(resp1.status_code, 201)
        user = User.objects.get(id=resp1.json()["lms_user_id"])
        self.assertFalse(user.is_active)

        # Reactivate
        payload["is_active"] = True
        resp2 = self._post_user(payload, auth_header=self.m2m_auth_header)
        self.assertEqual(resp2.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertTrue(resp2.json()["is_active"])

    def test_21_platform_super_admin_never_granted(self):
        """21. Provisioned user is never platform super admin, and mapping super admin fails."""
        create_tenant_mapping("vibeconnect", "org_uuid_tenant_21", self.org1)

        # Try to provision user with superadmin's email
        payload = {
            "external_tenant_id": "org_uuid_tenant_21",
            "external_user_id": "usr_uuid_211",
            "email": self.super_admin.email,
            "is_active": True
        }
        resp = self._post_user(payload, auth_header=self.m2m_auth_header)
        self.assertEqual(resp.status_code, 409)
        self.assertIn("Platform Super Admin", resp.json()["detail"])

        # Also verify new user has is_platform_super_admin=False
        new_payload = {
            "external_tenant_id": "org_uuid_tenant_21",
            "external_user_id": "usr_uuid_212",
            "email": "brand.new.user@orgone.com",
            "is_active": True
        }
        resp2 = self._post_user(new_payload, auth_header=self.m2m_auth_header)
        self.assertEqual(resp2.status_code, 201)
        new_user = User.objects.get(id=resp2.json()["lms_user_id"])
        self.assertFalse(new_user.is_platform_super_admin)

    def test_22_invalid_payload_rejected_user(self):
        """22. Missing external_user_id, bad email, or non-boolean is_active are rejected."""
        create_tenant_mapping("vibeconnect", "org_uuid_tenant_22", self.org1)

        # Missing external_user_id
        resp = self._post_user({
            "external_tenant_id": "org_uuid_tenant_22",
            "email": "test@test.com",
            "is_active": True
        }, auth_header=self.m2m_auth_header)
        self.assertEqual(resp.status_code, 400)

        # Bad email format
        resp = self._post_user({
            "external_tenant_id": "org_uuid_tenant_22",
            "external_user_id": "u22",
            "email": "not-an-email",
            "is_active": True
        }, auth_header=self.m2m_auth_header)
        self.assertEqual(resp.status_code, 400)

        # Non-boolean is_active
        resp = self._post_user({
            "external_tenant_id": "org_uuid_tenant_22",
            "external_user_id": "u22",
            "email": "valid@test.com",
            "is_active": "yes"
        }, auth_header=self.m2m_auth_header)
        self.assertEqual(resp.status_code, 400)

    def test_23_concurrent_duplicate_provisioning_safe_user(self):
        """23. If concurrent user request throws MappingConflictError, existing mapping is cleanly returned."""
        create_tenant_mapping("vibeconnect", "org_uuid_tenant_23", self.org1)
        create_user_mapping("vibeconnect", "usr_uuid_223", self.org1, self.normal_user)

        with patch('organizations.provisioning_services.create_user_mapping', side_effect=MappingConflictError("Simulated race")):
            user, mapping, action = provision_user(
                provider='vibeconnect',
                external_tenant_id='org_uuid_tenant_23',
                external_user_id='usr_uuid_223',
                email=self.normal_user.email,
                first_name='Concurrent',
                last_name='User',
                is_active=True
            )
            self.assertEqual(user.id, self.normal_user.id)
            self.assertEqual(action, "existing")

    # =========================================================================
    # SECURITY & M2M AUTHENTICATION TESTS (24 - 27)
    # =========================================================================

    def test_24_browser_user_jwt_cannot_call_endpoints(self):
        """24. Standard LMS user JWT cannot access M2M integration endpoints."""
        user_jwt = str(RefreshToken.for_user(self.normal_user).access_token)
        jwt_header = f"Bearer {user_jwt}"

        resp_tenant = self._post_tenant({
            "external_tenant_id": "org_uuid_sec_1",
            "name": "Sec Test",
            "code": "sec",
            "status": "active"
        }, auth_header=jwt_header)
        self.assertEqual(resp_tenant.status_code, 401)

        resp_user = self._post_user({
            "external_tenant_id": "org_uuid_sec_1",
            "external_user_id": "usr_uuid_sec_1",
            "email": "sec@test.com",
            "is_active": True
        }, auth_header=jwt_header)
        self.assertEqual(resp_user.status_code, 401)

    def test_25_missing_m2m_header_rejected(self):
        """25. Completely missing Authorization header rejected."""
        resp = self.client.post(
            '/api/v1/integration/tenants/provision/',
            data=json.dumps({"external_tenant_id": "t1", "name": "t1", "code": "t1", "status": "active"}),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 401)

    def test_26_wrong_m2m_token_rejected(self):
        """26. Invalid or forged M2M secret rejected with 401."""
        resp = self._post_tenant(
            {"external_tenant_id": "t2", "name": "t2", "code": "t2", "status": "active"},
            auth_header="Bearer totally-bogus-token"
        )
        self.assertEqual(resp.status_code, 401)

    def test_27_no_secret_leakage_in_response_or_logging(self):
        """27. Secret token is never returned in response payload or error detail."""
        resp = self._post_tenant(
            {"external_tenant_id": "t3", "name": "t3", "code": "t3", "status": "active"},
            auth_header="Bearer totally-bogus-token"
        )
        content_str = resp.content.decode('utf-8')
        self.assertNotIn(TEST_M2M_SECRET, content_str)
        self.assertNotIn("totally-bogus-token", content_str)

    # =========================================================================
    # ROLE INITIALIZATION & CONSTRAINED ROLE ASSIGNMENT TESTS (28 - 35)
    # =========================================================================

    def test_28_tenant_provisioning_ensures_default_org_admin_role_exactly_once(self):
        """28. Tenant provisioning initializes default Organization Admin role and repeated provisioning does not duplicate it."""
        resp = self._post_tenant({
            "external_tenant_id": "org_role_test_1",
            "name": "Role Test Tenant",
            "code": "rtt",
            "status": "active"
        }, auth_header=self.m2m_auth_header)
        self.assertEqual(resp.status_code, 201)
        org_id = resp.json()["lms_organization_id"]

        # Exactly one default Organization Admin role exists with is_admin_role=True
        roles = Role.objects.filter(organization_id=org_id, is_admin_role=True)
        self.assertEqual(roles.count(), 1)
        admin_role = roles.first()
        self.assertEqual(admin_role.name, "Organization Admin")
        self.assertTrue(admin_role.is_default)
        self.assertTrue(admin_role.is_admin_role)
        self.assertTrue(admin_role.can_manage_users)
        self.assertTrue(admin_role.workspaces.filter(key='admin').exists())

        # Repeated provisioning should be idempotent and not create duplicate roles
        resp_repeat = self._post_tenant({
            "external_tenant_id": "org_role_test_1",
            "name": "Role Test Tenant Updated",
            "code": "rtt",
            "status": "active"
        }, auth_header=self.m2m_auth_header)
        self.assertEqual(resp_repeat.status_code, 200)
        self.assertEqual(Role.objects.filter(organization_id=org_id, is_admin_role=True).count(), 1)

    def test_29_user_provisioning_assigns_organization_admin_role(self):
        """29. Provisioning a user with role='organization_admin' assigns tenant-scoped admin role."""
        # First ensure tenant
        self._post_tenant({
            "external_tenant_id": "org_role_test_2",
            "name": "Role Org 2",
            "code": "ro2",
            "status": "active"
        }, auth_header=self.m2m_auth_header)

        resp = self._post_user({
            "external_tenant_id": "org_role_test_2",
            "external_user_id": "usr_admin_101",
            "email": "admin101@ro2.com",
            "first_name": "Admin",
            "last_name": "User",
            "is_active": True,
            "role": "organization_admin"
        }, auth_header=self.m2m_auth_header)
        self.assertEqual(resp.status_code, 201)
        user_data = resp.json()
        self.assertEqual(user_data["role"], "Organization Admin")

        user = User.objects.get(id=user_data["lms_user_id"])
        self.assertIsNotNone(user.role)
        self.assertTrue(user.role.is_admin_role)
        self.assertEqual(user.role.organization_id, user.organization_id)
        self.assertFalse(user.is_platform_super_admin)

    def test_30_user_provisioning_member_does_not_grant_admin(self):
        """30. Provisioning a user with role='member' does not grant Organization Admin role."""
        self._post_tenant({
            "external_tenant_id": "org_role_test_3",
            "name": "Role Org 3",
            "code": "ro3",
            "status": "active"
        }, auth_header=self.m2m_auth_header)

        resp = self._post_user({
            "external_tenant_id": "org_role_test_3",
            "external_user_id": "usr_member_101",
            "email": "member101@ro3.com",
            "first_name": "Member",
            "last_name": "User",
            "is_active": True,
            "role": "member"
        }, auth_header=self.m2m_auth_header)
        self.assertEqual(resp.status_code, 201)
        user_data = resp.json()
        self.assertIsNone(user_data["role"])

        user = User.objects.get(id=user_data["lms_user_id"])
        self.assertIsNone(user.role)
        self.assertFalse(user.is_platform_super_admin)

    def test_31_user_provisioning_omitted_role_preserves_backward_compatibility(self):
        """31. When role is omitted by older callers, no administrative role is granted."""
        self._post_tenant({
            "external_tenant_id": "org_role_test_4",
            "name": "Role Org 4",
            "code": "ro4",
            "status": "active"
        }, auth_header=self.m2m_auth_header)

        resp = self._post_user({
            "external_tenant_id": "org_role_test_4",
            "external_user_id": "usr_legacy_101",
            "email": "legacy101@ro4.com",
            "first_name": "Legacy",
            "last_name": "Caller",
            "is_active": True
        }, auth_header=self.m2m_auth_header)
        self.assertEqual(resp.status_code, 201)
        user_data = resp.json()
        self.assertIsNone(user_data["role"])

        user = User.objects.get(id=user_data["lms_user_id"])
        self.assertIsNone(user.role)

    def test_32_user_provisioning_invalid_role_rejected(self):
        """32. Supplying an arbitrary or unapproved role key is rejected with 400 validation error."""
        self._post_tenant({
            "external_tenant_id": "org_role_test_5",
            "name": "Role Org 5",
            "code": "ro5",
            "status": "active"
        }, auth_header=self.m2m_auth_header)

        resp = self._post_user({
            "external_tenant_id": "org_role_test_5",
            "external_user_id": "usr_bad_role",
            "email": "badrole@ro5.com",
            "is_active": True,
            "role": "platform_super_admin"
        }, auth_header=self.m2m_auth_header)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"], "validation_error")

    def test_33_user_provisioning_assigns_admin_to_existing_role_none_user(self):
        """33. Existing mapped user with role=None is safely assigned admin when role='organization_admin'."""
        self._post_tenant({
            "external_tenant_id": "org_role_test_6",
            "name": "Role Org 6",
            "code": "ro6",
            "status": "active"
        }, auth_header=self.m2m_auth_header)

        # Step 1: provision user without role (role=None)
        resp1 = self._post_user({
            "external_tenant_id": "org_role_test_6",
            "external_user_id": "usr_upgrade_101",
            "email": "upgrade@ro6.com",
            "is_active": True
        }, auth_header=self.m2m_auth_header)
        self.assertEqual(resp1.status_code, 201)
        user = User.objects.get(id=resp1.json()["lms_user_id"])
        self.assertIsNone(user.role)

        # Step 2: repeated provisioning supplying organization_admin
        resp2 = self._post_user({
            "external_tenant_id": "org_role_test_6",
            "external_user_id": "usr_upgrade_101",
            "email": "upgrade@ro6.com",
            "is_active": True,
            "role": "organization_admin"
        }, auth_header=self.m2m_auth_header)
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.json()["role"], "Organization Admin")

        user.refresh_from_db()
        self.assertIsNotNone(user.role)
        self.assertTrue(user.role.is_admin_role)

    def test_34_user_provisioning_conflicting_role_is_not_silently_overwritten(self):
        """34. Existing user with a different LMS custom role raises conflict instead of silent overwrite."""
        self._post_tenant({
            "external_tenant_id": "org_role_test_7",
            "name": "Role Org 7",
            "code": "ro7",
            "status": "active"
        }, auth_header=self.m2m_auth_header)

        org = Organization.objects.get(sub_domain="ro7")
        custom_instructor_role = Role.objects.create(
            organization=org,
            name="Custom Instructor",
            is_admin_role=False,
            is_default=False
        )

        user = User.objects.create_user(
            username="instructor@ro7.com",
            email="instructor@ro7.com",
            organization=org,
            role=custom_instructor_role,
            is_active=True
        )

        # Attempt to provision with organization_admin
        resp = self._post_user({
            "external_tenant_id": "org_role_test_7",
            "external_user_id": "usr_inst_101",
            "email": "instructor@ro7.com",
            "is_active": True,
            "role": "organization_admin"
        }, auth_header=self.m2m_auth_header)
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["error"], "conflict")

        user.refresh_from_db()
        self.assertEqual(user.role_id, custom_instructor_role.id)

    def test_35_member_cannot_demote_organization_admin(self):
        """35. Attempting to pass role='member' for an existing Organization Admin raises conflict."""
        self._post_tenant({
            "external_tenant_id": "org_role_test_8",
            "name": "Role Org 8",
            "code": "ro8",
            "status": "active"
        }, auth_header=self.m2m_auth_header)

        # Provision as admin
        resp1 = self._post_user({
            "external_tenant_id": "org_role_test_8",
            "external_user_id": "usr_demote_test",
            "email": "demote@ro8.com",
            "is_active": True,
            "role": "organization_admin"
        }, auth_header=self.m2m_auth_header)
        self.assertEqual(resp1.status_code, 201)

        # Attempt to demote via member
        resp2 = self._post_user({
            "external_tenant_id": "org_role_test_8",
            "external_user_id": "usr_demote_test",
            "email": "demote@ro8.com",
            "is_active": True,
            "role": "member"
        }, auth_header=self.m2m_auth_header)
        self.assertEqual(resp2.status_code, 409)
        self.assertEqual(resp2.json()["error"], "conflict")

