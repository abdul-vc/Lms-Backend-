from django.test import TestCase
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from organizations.models import Organization, ExternalTenantMapping, ExternalUserMapping
from organizations.mapping_services import (
    create_tenant_mapping,
    lookup_tenant_mapping,
    unlink_tenant_mapping,
    create_user_mapping,
    lookup_user_mapping,
    unlink_user_mapping,
    MappingConflictError,
    MappingValidationError,
)

User = get_user_model()


class ExternalMappingTestCase(TestCase):
    def setUp(self):
        # Create standard test organizations in temporary test database
        self.org1 = Organization.objects.create(
            name="Acme Corp",
            company_name="Acme Corporation",
            entity_name="Acme Corp",
            sub_domain="acme-test-org",
            status="Active"
        )
        self.org2 = Organization.objects.create(
            name="Beta Ltd",
            company_name="Beta Limited",
            entity_name="Beta Ltd",
            sub_domain="beta-test-org",
            status="Active"
        )
        self.inactive_org = Organization.objects.create(
            name="Inactive Corp",
            company_name="Inactive Corporation",
            entity_name="Inactive Corp",
            sub_domain="inactive-test-org",
            status="Inactive"
        )

        # Create standard test users in temporary test database
        self.user1 = User.objects.create_user(
            username="john.doe@acme.com",
            email="john.doe@acme.com",
            password="TestPassword123!",
            organization=self.org1,
            is_active=True
        )
        self.user2 = User.objects.create_user(
            username="jane.smith@acme.com",
            email="jane.smith@acme.com",
            password="TestPassword123!",
            organization=self.org1,
            is_active=True
        )
        self.user_org2 = User.objects.create_user(
            username="bob.wilson@beta.com",
            email="bob.wilson@beta.com",
            password="TestPassword123!",
            organization=self.org2,
            is_active=True
        )
        self.inactive_user = User.objects.create_user(
            username="charlie.inactive@inactive.com",
            email="charlie.inactive@inactive.com",
            password="TestPassword123!",
            organization=self.inactive_org,
            is_active=False
        )
        self.super_admin = User.objects.create_user(
            username="superadmin@platform.com",
            email="superadmin@platform.com",
            password="TestPassword123!",
            is_platform_super_admin=True,
            is_superuser=True,
            is_staff=True,
            organization=None
        )

    # ─── TENANT MAPPING TESTS ────────────────────────────────────────────────

    def test_tenant_mapping_creation_and_lookup(self):
        mapping = create_tenant_mapping(
            provider="vibeconnect",
            external_tenant_id="ext-tenant-101",
            organization=self.org1
        )
        self.assertIsNotNone(mapping.id)
        self.assertEqual(mapping.provider, "vibeconnect")
        self.assertEqual(mapping.external_tenant_id, "ext-tenant-101")
        self.assertEqual(mapping.organization, self.org1)

        # Lookup by provider and external ID
        found = lookup_tenant_mapping("vibeconnect", "ext-tenant-101")
        self.assertIsNotNone(found)
        self.assertEqual(found.id, mapping.id)
        self.assertEqual(found.organization, self.org1)

    def test_tenant_mapping_lookup_not_found(self):
        found = lookup_tenant_mapping("vibeconnect", "non-existent-tenant-999")
        self.assertIsNone(found)

    def test_tenant_mapping_idempotent_retry(self):
        mapping1 = create_tenant_mapping("vibeconnect", "ext-tenant-102", self.org1)
        initial_count = ExternalTenantMapping.objects.count()

        # Re-submitting identical binding must return existing instance without creating new rows
        mapping2 = create_tenant_mapping("vibeconnect", "ext-tenant-102", self.org1)
        self.assertEqual(mapping1.id, mapping2.id)
        self.assertEqual(ExternalTenantMapping.objects.count(), initial_count)

    def test_tenant_mapping_conflict_on_external_id(self):
        create_tenant_mapping("vibeconnect", "ext-tenant-103", self.org1)

        # Attempting to map same external tenant ID to a different Organization must raise MappingConflictError
        with self.assertRaises(MappingConflictError):
            create_tenant_mapping("vibeconnect", "ext-tenant-103", self.org2)

    def test_tenant_mapping_conflict_on_organization(self):
        create_tenant_mapping("vibeconnect", "ext-tenant-104", self.org1)

        # Attempting to map the same Organization to a different external tenant ID must raise MappingConflictError
        with self.assertRaises(MappingConflictError):
            create_tenant_mapping("vibeconnect", "ext-tenant-999", self.org1)

    def test_tenant_mapping_provider_normalization(self):
        # Leading/trailing whitespace trimmed and lowercased
        mapping = create_tenant_mapping("  VibeConnect  ", "ext-tenant-105", self.org1)
        self.assertEqual(mapping.provider, "vibeconnect")

        # Looking up with different whitespace/casing must resolve cleanly
        found = lookup_tenant_mapping("  VIBeCONNECT  ", "ext-tenant-105")
        self.assertIsNotNone(found)
        self.assertEqual(found.id, mapping.id)

    def test_tenant_mapping_external_id_normalization_and_case_preservation(self):
        # Whitespace trimmed, but case strictly preserved
        raw_id = "  Tenant-CaseSensitive-UUID_123A  "
        expected_id = "Tenant-CaseSensitive-UUID_123A"
        mapping = create_tenant_mapping("vibeconnect", raw_id, self.org1)
        self.assertEqual(mapping.external_tenant_id, expected_id)

        # Lookup with whitespace trimmed matches
        found = lookup_tenant_mapping("vibeconnect", "  Tenant-CaseSensitive-UUID_123A  ")
        self.assertIsNotNone(found)
        self.assertEqual(found.external_tenant_id, expected_id)

    def test_tenant_mapping_rejects_blank_provider(self):
        with self.assertRaises(MappingValidationError):
            create_tenant_mapping("", "ext-tenant-106", self.org1)
        with self.assertRaises(MappingValidationError):
            create_tenant_mapping("   ", "ext-tenant-106", self.org1)
        with self.assertRaises(MappingValidationError):
            lookup_tenant_mapping("   ", "ext-tenant-106")

    def test_tenant_mapping_rejects_blank_external_id(self):
        with self.assertRaises(MappingValidationError):
            create_tenant_mapping("vibeconnect", "", self.org1)
        with self.assertRaises(MappingValidationError):
            create_tenant_mapping("vibeconnect", "   ", self.org1)
        with self.assertRaises(MappingValidationError):
            lookup_tenant_mapping("vibeconnect", "   ")

    def test_tenant_mapping_inactive_organization_allowed(self):
        # Mapping an inactive organization must be allowed for migration & reconciliation
        mapping = create_tenant_mapping("vibeconnect", "ext-tenant-inactive", self.inactive_org)
        self.assertIsNotNone(mapping.id)
        self.assertEqual(mapping.organization, self.inactive_org)

    # ─── USER MAPPING TESTS ──────────────────────────────────────────────────

    def test_user_mapping_creation_and_lookup(self):
        mapping = create_user_mapping(
            provider="vibeconnect",
            external_user_id="ext-user-201",
            organization=self.org1,
            user=self.user1
        )
        self.assertIsNotNone(mapping.id)
        self.assertEqual(mapping.provider, "vibeconnect")
        self.assertEqual(mapping.external_user_id, "ext-user-201")
        self.assertEqual(mapping.organization, self.org1)
        self.assertEqual(mapping.user, self.user1)

        # Lookup
        found = lookup_user_mapping("vibeconnect", "ext-user-201")
        self.assertIsNotNone(found)
        self.assertEqual(found.id, mapping.id)
        self.assertEqual(found.user, self.user1)
        self.assertEqual(found.organization, self.org1)

    def test_user_mapping_lookup_not_found(self):
        found = lookup_user_mapping("vibeconnect", "non-existent-user-999")
        self.assertIsNone(found)

    def test_user_mapping_idempotent_retry(self):
        mapping1 = create_user_mapping("vibeconnect", "ext-user-202", self.org1, self.user1)
        initial_count = ExternalUserMapping.objects.count()

        # Re-submitting identical user mapping returns existing instance
        mapping2 = create_user_mapping("vibeconnect", "ext-user-202", self.org1, self.user1)
        self.assertEqual(mapping1.id, mapping2.id)
        self.assertEqual(ExternalUserMapping.objects.count(), initial_count)

    def test_user_mapping_conflict_on_external_user_id(self):
        create_user_mapping("vibeconnect", "ext-user-203", self.org1, self.user1)

        # Attempting to map same external user ID to another User must raise MappingConflictError
        with self.assertRaises(MappingConflictError):
            create_user_mapping("vibeconnect", "ext-user-203", self.org1, self.user2)

    def test_user_mapping_conflict_on_user(self):
        create_user_mapping("vibeconnect", "ext-user-204", self.org1, self.user1)

        # Attempting to map the same User to a different external user ID must raise MappingConflictError
        with self.assertRaises(MappingConflictError):
            create_user_mapping("vibeconnect", "ext-user-999", self.org1, self.user1)

    def test_user_mapping_provider_normalization(self):
        mapping = create_user_mapping("  VibeConnect  ", "ext-user-205", self.org1, self.user1)
        self.assertEqual(mapping.provider, "vibeconnect")

        found = lookup_user_mapping("  VIBeCONNECT  ", "ext-user-205")
        self.assertIsNotNone(found)
        self.assertEqual(found.id, mapping.id)

    def test_user_mapping_external_id_normalization_and_case_preservation(self):
        raw_id = "  Usr-CaseSensitive_Id99Z  "
        expected_id = "Usr-CaseSensitive_Id99Z"
        mapping = create_user_mapping("vibeconnect", raw_id, self.org1, self.user1)
        self.assertEqual(mapping.external_user_id, expected_id)

        found = lookup_user_mapping("vibeconnect", "  Usr-CaseSensitive_Id99Z  ")
        self.assertIsNotNone(found)
        self.assertEqual(found.external_user_id, expected_id)

    def test_user_mapping_rejects_blank_provider(self):
        with self.assertRaises(MappingValidationError):
            create_user_mapping("", "ext-user-206", self.org1, self.user1)
        with self.assertRaises(MappingValidationError):
            create_user_mapping("   ", "ext-user-206", self.org1, self.user1)

    def test_user_mapping_rejects_blank_external_id(self):
        with self.assertRaises(MappingValidationError):
            create_user_mapping("vibeconnect", "", self.org1, self.user1)
        with self.assertRaises(MappingValidationError):
            create_user_mapping("vibeconnect", "   ", self.org1, self.user1)

    def test_user_mapping_cross_tenant_mismatch_rejected(self):
        # user_org2 belongs to org2; trying to map them under org1 must be rejected
        with self.assertRaises(MappingValidationError) as ctx:
            create_user_mapping("vibeconnect", "ext-user-cross", self.org1, self.user_org2)
        self.assertIn("Tenant isolation mismatch", str(ctx.exception))

    def test_user_mapping_platform_super_admin_rejected(self):
        # Platform Super Admins cannot be mapped to a tenant external user mapping
        with self.assertRaises(MappingValidationError) as ctx:
            create_user_mapping("vibeconnect", "ext-user-admin", self.org1, self.super_admin)
        self.assertIn("Platform Super Admin", str(ctx.exception))

    def test_user_mapping_inactive_user_and_org_allowed(self):
        # Inactive users and inactive organizations can have their mappings established
        mapping = create_user_mapping("vibeconnect", "ext-user-inactive", self.inactive_org, self.inactive_user)
        self.assertIsNotNone(mapping.id)
        self.assertEqual(mapping.user, self.inactive_user)
        self.assertEqual(mapping.organization, self.inactive_org)

    # ─── LIFECYCLE, UNLINKING & CASCADES ──────────────────────────────────────

    def test_unlink_tenant_preserves_organization(self):
        create_tenant_mapping("vibeconnect", "ext-tenant-unlink", self.org1)
        self.assertIsNotNone(lookup_tenant_mapping("vibeconnect", "ext-tenant-unlink"))

        # Unlink tenant mapping
        success = unlink_tenant_mapping("vibeconnect", "ext-tenant-unlink")
        self.assertTrue(success)
        self.assertIsNone(lookup_tenant_mapping("vibeconnect", "ext-tenant-unlink"))

        # Verify underlying Organization is completely untouched
        self.assertTrue(Organization.objects.filter(id=self.org1.id).exists())

    def test_unlink_user_preserves_user_and_organization(self):
        create_user_mapping("vibeconnect", "ext-user-unlink", self.org1, self.user1)
        self.assertIsNotNone(lookup_user_mapping("vibeconnect", "ext-user-unlink"))

        # Unlink user mapping
        success = unlink_user_mapping("vibeconnect", "ext-user-unlink")
        self.assertTrue(success)
        self.assertIsNone(lookup_user_mapping("vibeconnect", "ext-user-unlink"))

        # Verify underlying User and Organization are completely untouched
        self.assertTrue(User.objects.filter(id=self.user1.id).exists())
        self.assertTrue(Organization.objects.filter(id=self.org1.id).exists())

    def test_unlink_non_existent_returns_false(self):
        self.assertFalse(unlink_tenant_mapping("vibeconnect", "non-existent-tenant"))
        self.assertFalse(unlink_user_mapping("vibeconnect", "non-existent-user"))

    def test_cascade_delete_organization(self):
        t_map = create_tenant_mapping("vibeconnect", "ext-tenant-cascade", self.org1)
        u_map = create_user_mapping("vibeconnect", "ext-user-cascade", self.org1, self.user1)

        # Deleting Organization cascades to both ExternalTenantMapping and ExternalUserMapping
        self.org1.delete()

        self.assertFalse(ExternalTenantMapping.objects.filter(id=t_map.id).exists())
        self.assertFalse(ExternalUserMapping.objects.filter(id=u_map.id).exists())

    def test_cascade_delete_user(self):
        u_map = create_user_mapping("vibeconnect", "ext-user-cascade-2", self.org1, self.user2)

        # Deleting User cascades to ExternalUserMapping
        self.user2.delete()

        self.assertFalse(ExternalUserMapping.objects.filter(id=u_map.id).exists())
        # Organization remains intact
        self.assertTrue(Organization.objects.filter(id=self.org1.id).exists())

    # ─── MULTI-PROVIDER COEXISTENCE ──────────────────────────────────────────

    def test_multi_provider_coexistence(self):
        # Provider A (vibeconnect) and Provider B (okta) using the exact same external IDs
        mapping_vibe = create_tenant_mapping("vibeconnect", "common-ext-tenant-id", self.org1)
        mapping_okta = create_tenant_mapping("okta", "common-ext-tenant-id", self.org2)

        self.assertEqual(mapping_vibe.provider, "vibeconnect")
        self.assertEqual(mapping_okta.provider, "okta")

        # Independent lookups
        self.assertEqual(lookup_tenant_mapping("vibeconnect", "common-ext-tenant-id").organization, self.org1)
        self.assertEqual(lookup_tenant_mapping("okta", "common-ext-tenant-id").organization, self.org2)

        # User mapping coexistence
        u_vibe = create_user_mapping("vibeconnect", "common-ext-user-id", self.org1, self.user1)
        u_okta = create_user_mapping("okta", "common-ext-user-id", self.org2, self.user_org2)

        self.assertEqual(lookup_user_mapping("vibeconnect", "common-ext-user-id").user, self.user1)
        self.assertEqual(lookup_user_mapping("okta", "common-ext-user-id").user, self.user_org2)

    # ─── DATABASE CONSTRAINT INTEGRITY ───────────────────────────────────────

    def test_database_level_unique_constraint_tenant(self):
        ExternalTenantMapping.objects.create(
            provider="vibeconnect",
            external_tenant_id="db-constraint-tenant-1",
            organization=self.org1
        )
        # Bypassing service and trying to create duplicate in DB raises IntegrityError
        with self.assertRaises(IntegrityError):
            ExternalTenantMapping.objects.create(
                provider="vibeconnect",
                external_tenant_id="db-constraint-tenant-1",
                organization=self.org2
            )

    def test_database_level_unique_constraint_user(self):
        ExternalUserMapping.objects.create(
            provider="vibeconnect",
            external_user_id="db-constraint-user-1",
            organization=self.org1,
            user=self.user1
        )
        # Bypassing service and trying to create duplicate in DB raises IntegrityError
        with self.assertRaises(IntegrityError):
            ExternalUserMapping.objects.create(
                provider="vibeconnect",
                external_user_id="db-constraint-user-1",
                organization=self.org1,
                user=self.user2
            )
