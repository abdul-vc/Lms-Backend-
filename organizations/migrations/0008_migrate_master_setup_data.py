from django.db import migrations

def migrate_module_access_to_site_feature(apps, schema_editor):
    try:
        ModuleAccess = apps.get_model('organizations', 'ModuleAccess')
        SiteFeatureAccess = apps.get_model('master_setup', 'SiteFeatureAccess')
        Feature = apps.get_model('master_setup', 'Feature')
    except LookupError:
        return # Skip if models aren't available

    features_to_create = [
        {'key': 'dashboard', 'name': 'Dashboard', 'category': 'core'},
        {'key': 'course_catalog', 'name': 'Course Catalog', 'category': 'core'},
        {'key': 'learning_paths', 'name': 'Learning Paths', 'category': 'core'},
        {'key': 'certifications', 'name': 'Certifications', 'category': 'core'},
        {'key': 'ai_assistant', 'name': 'AI Assistant', 'category': 'advanced'},
        {'key': 'content_authoring', 'name': 'Content Authoring', 'category': 'advanced'},
        {'key': 'admin_console', 'name': 'Admin Console', 'category': 'advanced'},
    ]

    feature_map = {}
    for f_data in features_to_create:
        feature, _ = Feature.objects.get_or_create(key=f_data['key'], defaults=f_data)
        feature_map[f_data['key']] = feature

    for ma in ModuleAccess.objects.all():
        for key, feature in feature_map.items():
            enabled = getattr(ma, key, True)
            SiteFeatureAccess.objects.get_or_create(
                site=ma.site,
                feature=feature,
                defaults={'enabled': enabled}
            )

def migrate_plan_type_to_plan(apps, schema_editor):
    try:
        BillingConfiguration = apps.get_model('organizations', 'BillingConfiguration')
        Plan = apps.get_model('master_setup', 'Plan')
    except LookupError:
        return

    for billing in BillingConfiguration.objects.all():
        if getattr(billing, 'plan_type', None):
            plan, _ = Plan.objects.get_or_create(name=billing.plan_type, defaults={'description': 'Migrated Plan'})
            billing.plan = plan
            billing.save(update_fields=['plan'])

def seed_role_blueprints(apps, schema_editor):
    try:
        RoleBlueprint = apps.get_model('master_setup', 'RoleBlueprint')
    except LookupError:
        return

    RoleBlueprint.objects.get_or_create(
        name='Org Admin',
        defaults={
            'description': 'Full organization administrator',
            'can_manage_users': True,
            'can_manage_departments': True,
            'can_manage_roles': True,
            'can_create_courses': True,
            'can_edit_courses': True,
            'can_publish_courses': True,
            'can_manage_module_access': True,
            'can_view_reports': True,
            'can_manage_certificates': True,
            'is_org_admin_default': True,
        }
    )
    RoleBlueprint.objects.get_or_create(
        name='Instructor',
        defaults={
            'description': 'Course creator and manager',
            'can_manage_users': False,
            'can_manage_departments': False,
            'can_manage_roles': False,
            'can_create_courses': True,
            'can_edit_courses': True,
            'can_publish_courses': True,
            'can_manage_module_access': False,
            'can_view_reports': True,
            'can_manage_certificates': False,
            'is_org_admin_default': False,
        }
    )
    RoleBlueprint.objects.get_or_create(
        name='Learner',
        defaults={
            'description': 'Default student role',
            'can_manage_users': False,
            'can_manage_departments': False,
            'can_manage_roles': False,
            'can_create_courses': False,
            'can_edit_courses': False,
            'can_publish_courses': False,
            'can_manage_module_access': False,
            'can_view_reports': False,
            'can_manage_certificates': False,
            'is_org_admin_default': False,
        }
    )

def seed_notification_templates(apps, schema_editor):
    try:
        NotificationTemplate = apps.get_model('master_setup', 'NotificationTemplate')
    except LookupError:
        return
        
    templates = [
        {'key': 'welcome_admin', 'subject': 'Welcome to {{ platform_name }}', 'body_html': '<p>Welcome, {{ user_name }}!</p>'},
        {'key': 'access_request_submitted', 'subject': 'Access Request Submitted', 'body_html': '<p>Your request is under review.</p>'},
        {'key': 'access_request_accepted', 'subject': 'Access Request Approved', 'body_html': '<p>Your access has been granted.</p>'},
        {'key': 'certificate_issued', 'subject': 'New Certificate Issued', 'body_html': '<p>Congratulations on your new certificate.</p>'},
        {'key': 'billing_reminder', 'subject': 'Billing Reminder', 'body_html': '<p>Your payment is due soon.</p>'},
        {'key': 'password_reset', 'subject': 'Password Reset Request', 'body_html': '<p>Click here to reset your password.</p>'},
    ]
    for tmpl in templates:
        NotificationTemplate.objects.get_or_create(key=tmpl['key'], defaults=tmpl)

class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0007_role_is_admin_role'),
        ('master_setup', '__first__'),
    ]

    operations = [
        migrations.RunPython(migrate_module_access_to_site_feature),
        migrations.RunPython(migrate_plan_type_to_plan),
        migrations.RunPython(seed_role_blueprints),
        migrations.RunPython(seed_notification_templates),
    ]
