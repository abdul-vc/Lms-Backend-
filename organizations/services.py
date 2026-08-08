import logging
from django.contrib.auth import get_user_model
from rest_framework.exceptions import ValidationError
from .models import Role
from .emails import send_tenant_welcome_email
from master_setup.models import Workspace

logger = logging.getLogger(__name__)
User = get_user_model()

def seed_org_feature_access(org):
    """Seed OrganizationFeatureAccess for all features with enabled=True (default-allow)."""
    from master_setup.models import Feature, OrganizationFeatureAccess
    for feature in Feature.objects.all():
        OrganizationFeatureAccess.objects.get_or_create(
            organization=org, feature=feature, defaults={'enabled': True}
        )

def provision_org_admin_user(org, admin_email, raw_password=None, contact_name=None, request=None):
    """
    Safely provisions an Organization Admin user for the given tenant and sends welcome email.
    
    CRITICAL SECURITY & TENANT ISOLATION GUARANTEES:
    1. NEVER update an existing Platform Super Admin or another tenant's user.
    2. Raise a clear ValidationError if the email belongs to an existing Super Admin or another tenant.
    3. Explicitly set is_platform_super_admin=False, is_staff=False, is_superuser=False.
    4. Automatically trigger welcome email containing the ACTUAL raw password.
    """
    if not admin_email or not str(admin_email).strip():
        return None, "No admin email provided."

    clean_email = str(admin_email).strip()
    clean_password = str(raw_password).strip() if (raw_password and str(raw_password).strip()) else "Admin123!"

    # 1. Tenant & User Isolation Check: Prevent overwriting any existing account!
    existing_user = User.objects.filter(email__iexact=clean_email).first() or User.objects.filter(username__iexact=clean_email).first()
    org_id_val = getattr(org, 'id', None)
    
    if existing_user:
        if existing_user.is_platform_super_admin:
            raise ValidationError({
                'initial_admin_email': f"The email address '{clean_email}' is reserved for the Platform Super Admin account. Please enter a distinct email for the tenant administrator."
            })
        elif existing_user.organization_id and org_id_val and existing_user.organization_id != org_id_val:
            org_name_str = existing_user.organization.name if existing_user.organization else "another tenant"
            raise ValidationError({
                'initial_admin_email': f"The email address '{clean_email}' is already registered to {org_name_str}. Please provide a unique email address for this organization admin."
            })

    # 2. Get or create Organization Admin role for this specific organization
    admin_role = None
    if org:
        admin_role = Role.objects.filter(organization=org, is_admin_role=True).first()
        if not admin_role:
            admin_role = Role.objects.create(
                organization=org,
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
        
        # Assign all workspaces to role (set is idempotent, ensures completeness)
        admin_role.workspaces.set(Workspace.objects.all())

    # 3. Create or update user cleanly
    if existing_user and org_id_val and existing_user.organization_id == org_id_val:
        # Existing user for THIS org - update role and password if provided
        if raw_password:
            existing_user.set_password(clean_password)
        if admin_role:
            existing_user.role = admin_role
        existing_user.is_platform_super_admin = False
        existing_user.save()
        admin_user = existing_user
    else:
        # Create brand NEW user record
        first_name = contact_name.strip() if (contact_name and str(contact_name).strip()) else org.name
        admin_user = User.objects.create_user(
            username=clean_email,
            email=clean_email,
            password=clean_password,
            first_name=first_name,
            last_name='Admin',
            organization=org,
            role=admin_role,
            is_platform_super_admin=False, # GUARANTEED FALSE!
            is_staff=False,                # GUARANTEED FALSE!
            is_superuser=False,            # GUARANTEED FALSE!
            is_active=True
        )

    # 4. Automatically trigger Welcome Email with the actual raw_password
    email_sent, email_msg = send_tenant_welcome_email(
        org=org,
        recipient_email=clean_email,
        admin_username=clean_email,
        raw_password=clean_password,
        request=request
    )

    return admin_user, email_msg
