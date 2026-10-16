import logging
from typing import Optional
from django.db import transaction, IntegrityError
from django.contrib.auth import get_user_model
from .models import Organization, ExternalTenantMapping, ExternalUserMapping

logger = logging.getLogger(__name__)
User = get_user_model()


class MappingConflictError(Exception):
    """Raised when an incoming mapping request conflicts with an existing record."""
    pass


class MappingValidationError(Exception):
    """Raised when input parameters fail structural or tenant isolation validation."""
    pass


def normalize_provider(provider: str) -> str:
    """
    Normalizes provider namespace:
    1. Strips leading and trailing whitespace.
    2. Lowercases all characters.
    3. Rejects empty or non-string input.
    """
    if not isinstance(provider, str) or not provider.strip():
        raise MappingValidationError("Provider must be a non-empty string.")
    return provider.strip().lower()


def normalize_external_id(external_id: str, field_name: str = "external_id") -> str:
    """
    Normalizes external identifier:
    1. Strips leading and trailing whitespace.
    2. Preserves original casing (case-sensitive external keys/UUIDs).
    3. Rejects empty or non-string input.
    """
    if not isinstance(external_id, str) or not external_id.strip():
        raise MappingValidationError(f"{field_name} must be a non-empty string.")
    return external_id.strip()


def create_tenant_mapping(provider: str, external_tenant_id: str, organization: Organization) -> ExternalTenantMapping:
    """
    Idempotently creates or retrieves an external tenant mapping.
    
    Validation:
      - Provider and external_tenant_id must be non-empty strings.
      - Organization must be an existing Organization instance.
    
    Concurrency & Idempotency:
      - If identical binding already exists, returns existing instance safely.
      - If external_tenant_id is already bound to another Organization under this provider,
        raises MappingConflictError.
      - If Organization is already bound to another external_tenant_id under this provider,
        raises MappingConflictError.
    """
    norm_provider = normalize_provider(provider)
    norm_tenant_id = normalize_external_id(external_tenant_id, "external_tenant_id")

    if not isinstance(organization, Organization) or not organization.pk:
        raise MappingValidationError("A valid, saved Organization instance is required.")

    try:
        with transaction.atomic():
            return ExternalTenantMapping.objects.create(
                provider=norm_provider,
                external_tenant_id=norm_tenant_id,
                organization=organization
            )
    except IntegrityError:
        existing_by_ext_id = ExternalTenantMapping.objects.filter(
            provider=norm_provider,
            external_tenant_id=norm_tenant_id
        ).first()

        existing_by_org = ExternalTenantMapping.objects.filter(
            provider=norm_provider,
            organization=organization
        ).first()

        # Case A: Identical binding already exists -> Safe Idempotent Retry
        if existing_by_ext_id and existing_by_ext_id.organization_id == organization.id:
            return existing_by_ext_id

        # Case B: External ID is claimed by another Organization -> Conflict
        if existing_by_ext_id and existing_by_ext_id.organization_id != organization.id:
            raise MappingConflictError(
                f"External tenant '{norm_tenant_id}' under provider '{norm_provider}' is already "
                f"mapped to Organization {existing_by_ext_id.organization_id}."
            )

        # Case C: Organization is already claimed by another External ID -> Conflict
        if existing_by_org and existing_by_org.external_tenant_id != norm_tenant_id:
            raise MappingConflictError(
                f"Organization {organization.id} is already mapped to external tenant "
                f"'{existing_by_org.external_tenant_id}' under provider '{norm_provider}'."
            )

        raise


def lookup_tenant_mapping(provider: str, external_tenant_id: str) -> Optional[ExternalTenantMapping]:
    """
    Resolves an ExternalTenantMapping instance by provider and external_tenant_id.
    Returns None if not mapped.
    """
    norm_provider = normalize_provider(provider)
    norm_tenant_id = normalize_external_id(external_tenant_id, "external_tenant_id")

    return ExternalTenantMapping.objects.select_related('organization').filter(
        provider=norm_provider,
        external_tenant_id=norm_tenant_id
    ).first()


def unlink_tenant_mapping(provider: str, external_tenant_id: str) -> bool:
    """
    Deletes the external tenant mapping record.
    Returns True if unlinked, False if record did not exist.
    Leaves the LMS Organization completely intact.
    """
    norm_provider = normalize_provider(provider)
    norm_tenant_id = normalize_external_id(external_tenant_id, "external_tenant_id")

    deleted_count, _ = ExternalTenantMapping.objects.filter(
        provider=norm_provider,
        external_tenant_id=norm_tenant_id
    ).delete()

    return deleted_count > 0


def create_user_mapping(provider: str, external_user_id: str, organization: Organization, user) -> ExternalUserMapping:
    """
    Idempotently creates or retrieves an external user mapping.
    
    Validation & Invariants:
      - Provider and external_user_id must be non-empty strings.
      - Organization and User must be valid saved instances.
      - User must belong to an organization (user.organization_id is not None).
      - Service-layer tenant consistency: user.organization_id == organization.id.
      - Platform Super Admins cannot be mapped to tenant external user mappings.
      - Inactive users and inactive organizations ARE permitted (lifecycle independence).
    
    Concurrency & Idempotency:
      - If identical binding already exists, returns existing instance safely.
      - If external_user_id is already bound to another User under this provider,
        raises MappingConflictError.
      - If User is already bound to another external_user_id under this provider,
        raises MappingConflictError.
    """
    norm_provider = normalize_provider(provider)
    norm_user_id = normalize_external_id(external_user_id, "external_user_id")

    if not isinstance(organization, Organization) or not organization.pk:
        raise MappingValidationError("A valid, saved Organization instance is required.")

    if not user or not getattr(user, 'pk', None):
        raise MappingValidationError("A valid, saved User instance is required.")

    # Platform super admins:
    # A global super admin with no organization cannot be mapped to a tenant identity.
    # An account converted from a tenant admin (retaining organization_id) can be mapped to its organization (e.g. showcase demo).
    if getattr(user, 'is_platform_super_admin', False):
        if getattr(user, 'organization_id', None) is None:
            raise MappingValidationError(
                f"User {user.id} is a Platform Super Admin and cannot be mapped to a tenant external user identity."
            )
        if user.organization_id != organization.id:
            raise MappingValidationError(
                f"Tenant isolation mismatch: User {user.id} belongs to Organization {user.organization_id}, "
                f"cannot map to Organization {organization.id}."
            )
    else:
        if getattr(user, 'organization_id', None) is None:
            raise MappingValidationError(
                f"User {user.id} has no associated organization and cannot be mapped."
            )
        if user.organization_id != organization.id:
            raise MappingValidationError(
                f"Tenant isolation mismatch: User {user.id} belongs to Organization {user.organization_id}, "
                f"cannot map to Organization {organization.id}."
            )

    try:
        with transaction.atomic():
            return ExternalUserMapping.objects.create(
                provider=norm_provider,
                external_user_id=norm_user_id,
                organization=organization,
                user=user
            )
    except IntegrityError:
        existing_by_ext_id = ExternalUserMapping.objects.filter(
            provider=norm_provider,
            external_user_id=norm_user_id
        ).first()

        existing_by_user = ExternalUserMapping.objects.filter(
            provider=norm_provider,
            user=user
        ).first()

        # Case A: Identical binding already exists -> Safe Idempotent Retry
        if (
            existing_by_ext_id
            and existing_by_ext_id.user_id == user.id
            and existing_by_ext_id.organization_id == organization.id
        ):
            return existing_by_ext_id

        # Case B: External ID is claimed by another User -> Conflict
        if existing_by_ext_id and existing_by_ext_id.user_id != user.id:
            raise MappingConflictError(
                f"External user '{norm_user_id}' under provider '{norm_provider}' is already "
                f"mapped to User {existing_by_ext_id.user_id}."
            )

        # Case C: User is already claimed by another External ID -> Conflict
        if existing_by_user and existing_by_user.external_user_id != norm_user_id:
            raise MappingConflictError(
                f"User {user.id} is already mapped to external user "
                f"'{existing_by_user.external_user_id}' under provider '{norm_provider}'."
            )

        raise


def lookup_user_mapping(provider: str, external_user_id: str) -> Optional[ExternalUserMapping]:
    """
    Resolves an ExternalUserMapping instance by provider and external_user_id.
    Returns None if not mapped.
    """
    norm_provider = normalize_provider(provider)
    norm_user_id = normalize_external_id(external_user_id, "external_user_id")

    return ExternalUserMapping.objects.select_related('organization', 'user').filter(
        provider=norm_provider,
        external_user_id=norm_user_id
    ).first()


def unlink_user_mapping(provider: str, external_user_id: str) -> bool:
    """
    Deletes the external user mapping record.
    Returns True if unlinked, False if record did not exist.
    Leaves the LMS User and Organization completely intact.
    """
    norm_provider = normalize_provider(provider)
    norm_user_id = normalize_external_id(external_user_id, "external_user_id")

    deleted_count, _ = ExternalUserMapping.objects.filter(
        provider=norm_provider,
        external_user_id=norm_user_id
    ).delete()

    return deleted_count > 0
