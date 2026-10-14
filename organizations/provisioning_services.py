import logging
import re
from typing import Tuple, Dict, Any, Optional
from django.db import transaction, IntegrityError
from django.utils.text import slugify
from django.contrib.auth import get_user_model
from .models import Organization, ExternalTenantMapping, ExternalUserMapping, Role
from master_setup.models import Workspace
from .mapping_services import (
    create_tenant_mapping,
    lookup_tenant_mapping,
    create_user_mapping,
    lookup_user_mapping,
    MappingConflictError,
    MappingValidationError,
)

logger = logging.getLogger(__name__)
User = get_user_model()

ALLOWED_TENANT_STATUSES = {
    'active': 'Active',
    'inactive': 'Inactive',
    'suspended': 'Suspended',
}

ALLOWED_PROVISIONING_ROLES = {
    'organization_admin',
    'member',
}


def ensure_tenant_default_roles(organization: Organization) -> Role:
    """
    Ensures that the default tenant-scoped LMS Organization Admin role exists
    for the given organization with all administrative privileges and workspaces assigned.
    Idempotent: returns existing role if already present.
    """
    admin_role = Role.objects.filter(organization=organization, is_admin_role=True).first()
    if not admin_role:
        admin_role = Role.objects.create(
            organization=organization,
            name='Organization Admin',
            is_default=True,
            is_admin_role=True,
            can_view_users=True,
            can_create_users=True,
            can_edit_users=True,
            can_delete_users=True,
            can_view_roles=True,
            can_create_roles=True,
            can_edit_roles=True,
            can_delete_roles=True,
            can_view_courses=True,
            can_create_courses=True,
            can_edit_courses=True,
            can_delete_courses=True,
            can_view_certificates=True,
            can_create_certificates=True,
            can_edit_certificates=True,
            can_delete_certificates=True,
            can_view_reports=True,
            can_create_reports=True,
            can_edit_reports=True,
            can_delete_reports=True,
            can_view_module_access=True,
            can_create_module_access=True,
            can_edit_module_access=True,
            can_delete_module_access=True,
            can_view_activity_log=True,
            can_create_activity_log=True,
            can_edit_activity_log=True,
            can_delete_activity_log=True,
        )

    # Ensure canonical workspaces exist if unseeded
    Workspace.objects.get_or_create(key='admin', defaults={'label': 'Administration', 'icon': 'ShieldCheck', 'order': 1})
    Workspace.objects.get_or_create(key='learner', defaults={'label': 'Learning', 'icon': 'GraduationCap', 'order': 2})

    # Assign workspaces idempotently
    admin_role.workspaces.set(Workspace.objects.all())
    return admin_role


class ProvisioningError(Exception):
    """Base exception for provisioning failures."""
    pass


class ProvisioningValidationError(ProvisioningError):
    """Raised when an incoming provisioning payload fails validation."""
    pass


class TenantNotFoundError(ProvisioningError):
    """Raised when a user is provisioned for an unmapped tenant."""
    pass


class ProvisioningConflictError(ProvisioningError):
    """Raised when provisioning encounters an unresolvable cross-tenant or identity conflict."""
    pass


def _validate_non_empty_str(val: Any, field_name: str) -> str:
    if not isinstance(val, str) or not val.strip():
        raise ProvisioningValidationError(f"{field_name} is required and cannot be blank.")
    return val.strip()


def _normalize_email(email: Any) -> str:
    val = _validate_non_empty_str(email, "email")
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', val):
        raise ProvisioningValidationError("Invalid email address format.")
    return val.lower()


def provision_tenant(
    provider: str,
    external_tenant_id: str,
    name: str,
    code: str,
    status: str
) -> Tuple[Organization, ExternalTenantMapping, str]:
    """
    Idempotently provisions or synchronizes an LMS Organization for an external tenant.

    Returns:
        Tuple of (Organization, ExternalTenantMapping, action_taken)
        where action_taken is either 'created' or 'existing'.
    """
    norm_provider = _validate_non_empty_str(provider, "provider").lower()
    norm_tenant_id = _validate_non_empty_str(external_tenant_id, "external_tenant_id")
    norm_name = _validate_non_empty_str(name, "name")
    norm_code = _validate_non_empty_str(code, "code")

    if not isinstance(status, str) or status.strip().lower() not in ALLOWED_TENANT_STATUSES:
        allowed = ", ".join(sorted(ALLOWED_TENANT_STATUSES.keys()))
        raise ProvisioningValidationError(
            f"Invalid status '{status}'. Allowed values are: {allowed}."
        )

    lms_status = ALLOWED_TENANT_STATUSES[status.strip().lower()]

    # 1. Check if mapping already exists
    existing_mapping = lookup_tenant_mapping(provider=norm_provider, external_tenant_id=norm_tenant_id)
    if existing_mapping:
        org = existing_mapping.organization
        # Synchronize allowed fields safely without overwriting LMS-owned fields
        org.name = norm_name
        org.company_name = norm_name
        org.entity_name = norm_name
        org.status = lms_status
        org.save(update_fields=['name', 'company_name', 'entity_name', 'status', 'updated_at'])
        ensure_tenant_default_roles(org)
        return org, existing_mapping, "existing"

    # 2. Concurrency-safe creation
    try:
        with transaction.atomic():
            # Re-check mapping within transaction
            existing_mapping = lookup_tenant_mapping(provider=norm_provider, external_tenant_id=norm_tenant_id)
            if existing_mapping:
                org = existing_mapping.organization
                org.name = norm_name
                org.company_name = norm_name
                org.entity_name = norm_name
                org.status = lms_status
                org.save(update_fields=['name', 'company_name', 'entity_name', 'status', 'updated_at'])
                ensure_tenant_default_roles(org)
                return org, existing_mapping, "existing"

            # Derive unique sub_domain
            base_subdomain = slugify(norm_code) or f"tenant-{slugify(norm_tenant_id)[:10]}"
            candidate_subdomain = base_subdomain
            if Organization.objects.filter(sub_domain=candidate_subdomain).exists():
                candidate_subdomain = f"{base_subdomain[:40]}-{slugify(norm_tenant_id)[:8]}"

            org = Organization.objects.create(
                name=norm_name,
                company_name=norm_name,
                entity_name=norm_name,
                sub_domain=candidate_subdomain,
                status=lms_status,
                subdomain_routing_enabled=True,
            )

            # Ensure default organization admin role exists for this tenant
            ensure_tenant_default_roles(org)

            mapping = create_tenant_mapping(
                provider=norm_provider,
                external_tenant_id=norm_tenant_id,
                organization=org
            )
            return org, mapping, "created"

    except (MappingConflictError, IntegrityError):
        # Race condition: concurrent worker created the mapping
        existing_mapping = lookup_tenant_mapping(provider=norm_provider, external_tenant_id=norm_tenant_id)
        if existing_mapping:
            org = existing_mapping.organization
            org.name = norm_name
            org.company_name = norm_name
            org.entity_name = norm_name
            org.status = lms_status
            org.save(update_fields=['name', 'company_name', 'entity_name', 'status', 'updated_at'])
            ensure_tenant_default_roles(org)
            return org, existing_mapping, "existing"
        raise


def provision_user(
    provider: str,
    external_tenant_id: str,
    external_user_id: str,
    email: str,
    first_name: Optional[str] = "",
    last_name: Optional[str] = "",
    is_active: bool = True,
    role: Optional[str] = None
) -> Tuple[User, ExternalUserMapping, str]:
    """
    Idempotently provisions or synchronizes an LMS User for an external user identity.
    Accepts an optional constrained role key ('organization_admin' or 'member').

    Returns:
        Tuple of (User, ExternalUserMapping, action_taken)
        where action_taken is either 'created' or 'existing'.
    """
    norm_provider = _validate_non_empty_str(provider, "provider").lower()
    norm_tenant_id = _validate_non_empty_str(external_tenant_id, "external_tenant_id")
    norm_user_id = _validate_non_empty_str(external_user_id, "external_user_id")
    norm_email = _normalize_email(email)

    if not isinstance(is_active, bool):
        raise ProvisioningValidationError("is_active must be a boolean value.")

    clean_first_name = (first_name or "").strip() if isinstance(first_name, str) else ""
    clean_last_name = (last_name or "").strip() if isinstance(last_name, str) else ""

    norm_role = None
    if role is not None:
        if not isinstance(role, str) or not role.strip():
            raise ProvisioningValidationError("role must be a non-empty string when provided.")
        norm_role = role.strip().lower()
        if norm_role not in ALLOWED_PROVISIONING_ROLES:
            allowed = ", ".join(sorted(ALLOWED_PROVISIONING_ROLES))
            raise ProvisioningValidationError(
                f"Invalid role '{role}'. Allowed values are: {allowed}."
            )

    # 1. Tenant mapping MUST exist
    tenant_mapping = lookup_tenant_mapping(provider=norm_provider, external_tenant_id=norm_tenant_id)
    if not tenant_mapping:
        raise TenantNotFoundError(
            f"Tenant '{norm_tenant_id}' is not mapped in LMS. Provision tenant first."
        )

    lms_org = tenant_mapping.organization

    def _apply_role(target_user: User) -> bool:
        """
        Applies constrained role logic to target_user.
        Returns True if target_user.role was changed, False otherwise.
        Raises ProvisioningConflictError if an incoming role contradicts an existing LMS role.
        """
        if norm_role is None:
            # Backward compatibility: do not grant admin privileges; preserve existing role
            return False

        if norm_role == 'organization_admin':
            admin_role = ensure_tenant_default_roles(lms_org)
            if target_user.role is None:
                target_user.role = admin_role
                return True
            elif target_user.role.is_admin_role:
                # Already an admin role; ensure correct tenant-scoped admin role
                if target_user.role_id != admin_role.id:
                    target_user.role = admin_role
                    return True
                return False
            else:
                # Existing user has a non-admin role; refuse silent overwrite
                raise ProvisioningConflictError(
                    f"Role conflict: User '{target_user.email}' already has LMS role '{target_user.role.name}'. "
                    f"Cannot overwrite with 'organization_admin'."
                )

        elif norm_role == 'member':
            if target_user.role and target_user.role.is_admin_role:
                # Cannot demote an existing Organization Admin via member provisioning
                raise ProvisioningConflictError(
                    f"Role conflict: User '{target_user.email}' is an Organization Admin. "
                    f"Cannot demote to 'member' via provisioning."
                )
            # For non-admin or None, preserve existing role; do not grant admin privileges
            return False

        return False

    # 2. Check if user mapping already exists
    existing_user_mapping = lookup_user_mapping(provider=norm_provider, external_user_id=norm_user_id)
    if existing_user_mapping:
        # Strict tenant isolation check
        if (
            existing_user_mapping.organization_id != lms_org.id
            or existing_user_mapping.user.organization_id != lms_org.id
        ):
            raise ProvisioningConflictError(
                f"Tenant isolation mismatch: External user '{norm_user_id}' belongs to Organization "
                f"{existing_user_mapping.organization_id}, cannot provision into Organization {lms_org.id}."
            )

        user = existing_user_mapping.user
        user.is_active = is_active
        update_fields = ['is_active']
        if clean_first_name:
            user.first_name = clean_first_name
            update_fields.append('first_name')
        if clean_last_name:
            user.last_name = clean_last_name
            update_fields.append('last_name')

        if _apply_role(user):
            update_fields.append('role')

        user.save(update_fields=update_fields)
        return user, existing_user_mapping, "existing"

    # 3. Check if user with same email exists in LMS
    existing_user = User.objects.filter(email__iexact=norm_email).first()
    if existing_user:
        # Never allow provisioning or mapping of Platform Super Admins
        if getattr(existing_user, 'is_platform_super_admin', False):
            raise ProvisioningConflictError(
                f"User with email '{norm_email}' is a Platform Super Admin and cannot be mapped as a tenant user."
            )

        # Cross-tenant check: user belongs to different org -> reject!
        if existing_user.organization_id != lms_org.id:
            raise ProvisioningConflictError(
                f"Cross-tenant conflict: User with email '{norm_email}' belongs to Organization "
                f"{existing_user.organization_id}, not Organization {lms_org.id}."
            )

        # Check if already mapped to a different external user ID under this provider
        other_mapping = ExternalUserMapping.objects.filter(
            provider=norm_provider,
            user=existing_user
        ).first()
        if other_mapping and other_mapping.external_user_id != norm_user_id:
            raise ProvisioningConflictError(
                f"User with email '{norm_email}' is already mapped to external user '{other_mapping.external_user_id}'."
            )

        # Safe same-org binding
        existing_user.is_active = is_active
        update_fields = ['is_active']
        if clean_first_name:
            existing_user.first_name = clean_first_name
            update_fields.append('first_name')
        if clean_last_name:
            existing_user.last_name = clean_last_name
            update_fields.append('last_name')

        if _apply_role(existing_user):
            update_fields.append('role')

        existing_user.save(update_fields=update_fields)

        mapping = create_user_mapping(
            provider=norm_provider,
            external_user_id=norm_user_id,
            organization=lms_org,
            user=existing_user
        )
        return existing_user, mapping, "created"

    # 4. Concurrency-safe creation of new user
    try:
        with transaction.atomic():
            # Re-check user mapping inside transaction
            existing_user_mapping = lookup_user_mapping(provider=norm_provider, external_user_id=norm_user_id)
            if existing_user_mapping:
                user = existing_user_mapping.user
                user.is_active = is_active
                update_fields = ['is_active']
                if clean_first_name:
                    user.first_name = clean_first_name
                    update_fields.append('first_name')
                if clean_last_name:
                    user.last_name = clean_last_name
                    update_fields.append('last_name')
                if _apply_role(user):
                    update_fields.append('role')
                user.save(update_fields=update_fields)
                return user, existing_user_mapping, "existing"

            # Derive unique username
            base_username = norm_email
            username = base_username
            if User.objects.filter(username__iexact=username).exists():
                username = f"{base_username[:130]}_{slugify(norm_user_id)[:10]}"

            initial_role = None
            if norm_role == 'organization_admin':
                initial_role = ensure_tenant_default_roles(lms_org)

            new_user = User.objects.create_user(
                username=username,
                email=norm_email,
                first_name=clean_first_name,
                last_name=clean_last_name,
                organization=lms_org,
                role=initial_role,
                is_active=is_active,
                is_platform_super_admin=False
            )
            new_user.set_unusable_password()
            new_user.save()

            mapping = create_user_mapping(
                provider=norm_provider,
                external_user_id=norm_user_id,
                organization=lms_org,
                user=new_user
            )
            return new_user, mapping, "created"

    except (MappingConflictError, IntegrityError):
        # Race condition: concurrent worker created the mapping
        existing_user_mapping = lookup_user_mapping(provider=norm_provider, external_user_id=norm_user_id)
        if existing_user_mapping:
            user = existing_user_mapping.user
            user.is_active = is_active
            update_fields = ['is_active']
            if clean_first_name:
                user.first_name = clean_first_name
                update_fields.append('first_name')
            if clean_last_name:
                user.last_name = clean_last_name
                update_fields.append('last_name')
            if _apply_role(user):
                update_fields.append('role')
            user.save(update_fields=update_fields)
            return user, existing_user_mapping, "existing"
        raise
