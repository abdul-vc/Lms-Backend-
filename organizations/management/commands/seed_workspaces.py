from django.core.management.base import BaseCommand
from master_setup.models import Workspace, NavItem, Feature

# 1. Authoritative Feature Registry
FEATURES_TO_SEED = [
    ('dashboard', 'Dashboard', 'Core dashboard & metrics overview', 'core'),
    ('users_departments', 'Users & Departments', 'User accounts, organizational structure, & department hierarchy', 'core'),
    ('roles_permissions', 'Roles & Permissions', 'Custom RBAC permissions and role blueprints', 'core'),
    ('module_access', 'Module Access Control', 'Feature and module access rules per role', 'core'),
    ('course_catalog', 'Course Catalog', 'Course discovery and learner catalog', 'core'),
    ('certifications', 'Certifications & Badges', 'Certificates issuance and gamification badges', 'core'),
    ('activity_log', 'Activity Log & Audit', 'System audit logs and user activity tracking', 'core'),
    ('content_authoring', 'Content Authoring', 'Course builder, module creation, & lesson editor', 'advanced'),
    ('pending_registration', 'Pending Registration', 'User self-registration approval queue', 'core'),
    ('internal_messenger', 'Internal Messenger', 'Real-time internal chat and web messaging', 'communication'),
    ('scorm_player', 'SCORM 1.2 / 2004 Engine', 'Interactive SCORM package player and tracking', 'learning'),
    ('learning_paths', 'Learning Paths', 'Structured multi-course learning pathways', 'learning'),
    ('ai_assistant', 'AI Assistant', 'AI tutor, quiz generation, & assistant', 'advanced'),
    ('analytics', 'Reports & Analytics', 'Comprehensive platform & tenant analytics', 'reporting'),
    ('site_management', 'Multi-Site Management', 'Sub-domain routing and portal management', 'administration'),
    ('billing_management', 'Subscription & Billing', 'Tenant plans, subscriptions, and invoicing', 'billing'),
    ('assessment_activity', 'Assessment Activity', 'Track and review user lesson assessment attempts and performance', 'reporting'),
]

# 2. Authoritative Workspace Nav Items
ADMIN_NAV_ITEMS = [
    ('overview', 'Overview', 'LayoutDashboard', '/org-admin', 'dashboard', ''),
    ('users_departments', 'Users & Departments', 'Users', '/org-admin/departments', 'users_departments', 'can_manage_users'),
    ('roles_permissions', 'Roles & Permissions', 'Lock', '/org-admin/roles', 'roles_permissions', 'can_manage_roles'),
    ('module_access', 'Module Access', 'ToggleLeft', '/org-admin/module-access', 'module_access', 'can_manage_module_access'),
    ('course_catalog_admin', 'Course Catalog', 'BookOpen', '/org-admin/courses', 'course_catalog', 'can_edit_courses'),
    ('learning_paths_admin', 'Learning Paths', 'Route', '/org-admin/paths', 'learning_paths', 'can_edit_courses'),
    ('certificates_admin', 'Certificates', 'Award', '/org-admin/certificates', 'certifications', 'can_manage_certificates'),
    ('activity_log', 'Activity Log', 'History', '/org-admin/activity', 'activity_log', 'is_admin_role'),
    ('assessment_activity', 'Assessment Activity', 'CheckSquare', '/org-admin/assessment-activity', 'assessment_activity', 'can_view_reports'),
    ('content_authoring', 'Content Authoring', 'PenTool', '/authoring', 'content_authoring', 'can_create_courses'),
    ('pending_registration', 'Pending Registration', 'UserPlus', '/pending-registration', 'pending_registration', 'can_manage_users'),
    ('messenger', 'Messenger', 'MessageSquare', '/messenger', 'internal_messenger', ''),
    ('my_profile', 'My Profile', 'User', '/org-admin/profile', None, ''),
]

LEARNER_NAV_ITEMS = [
    ('dashboard', 'Dashboard', 'LayoutDashboard', '/dashboard', 'dashboard', ''),
    ('course_catalog', 'Course Catalog', 'BookOpen', '/catalog', 'course_catalog', ''),
    ('learning_paths', 'Learning Paths', 'Route', '/paths', 'learning_paths', ''),
    ('certifications', 'Certifications', 'Award', '/certificates', 'certifications', ''),
    ('ai_assistant', 'AI Assistant', 'Sparkles', '/ai-assistant', 'ai_assistant', ''),
    ('messenger', 'Messenger', 'MessageSquare', '/messenger', 'internal_messenger', ''),
    ('my_profile', 'My Profile', 'User', '/profile', None, ''),
]

class Command(BaseCommand):
    def handle(self, *args, **options):
        admin_ws, _ = Workspace.objects.get_or_create(key='admin', defaults={'label': 'Administration', 'icon': 'ShieldCheck', 'order': 1})
        learner_ws, _ = Workspace.objects.get_or_create(key='learner', defaults={'label': 'Learning', 'icon': 'GraduationCap', 'order': 2})

        # 1. Seed All Global Features Across Entire Project
        feature_map = {}
        for key, name, desc, cat in FEATURES_TO_SEED:
            feat, _ = Feature.objects.update_or_create(
                key=key,
                defaults={'name': name, 'description': desc, 'category': cat, 'is_active': True}
            )
            feature_map[key] = feat

        # 2. Seed Workspaces and Nav Items with update_or_create
        for i, (key, label, icon, route, feature_key, perm) in enumerate(ADMIN_NAV_ITEMS):
            feature = feature_map.get(feature_key)
            NavItem.objects.update_or_create(
                workspace=admin_ws, 
                key=key, 
                defaults={
                    'label': label,
                    'icon': icon,
                    'route': route,
                    'feature': feature,
                    'required_permission': perm,
                    'order': i
                }
            )
        
        for i, (key, label, icon, route, feature_key, perm) in enumerate(LEARNER_NAV_ITEMS):
            feature = feature_map.get(feature_key)
            NavItem.objects.update_or_create(
                workspace=learner_ws, 
                key=key, 
                defaults={
                    'label': label,
                    'icon': icon,
                    'route': route,
                    'feature': feature,
                    'required_permission': perm,
                    'order': i
                }
            )

            

        # Seed dashboard widgets
        from master_setup.models import DashboardWidget
        
        admin_widgets = [
            ('pending_registrations_count', 'Pending Registrations', 'pending_registrations_count', None),
            ('org_activity_summary', 'Activity Summary', 'org_activity_summary', None),
            ('module_status_summary', 'Module Status', 'module_status_summary', None),
            ('active_users_count', 'Active Users', 'active_users_count', None),
        ]
        
        for i, (key, label, comp, feat) in enumerate(admin_widgets):
            DashboardWidget.objects.get_or_create(workspace=admin_ws, key=key, defaults={
                'label': label, 'component_key': comp, 'order': i
            })
            
        learner_widgets = [
            ('daily_streak', 'Daily Streak', 'daily_streak', None),
            ('continue_learning', 'Continue Learning', 'continue_learning', None),
            ('browse_catalog', 'Browse Catalog', 'browse_catalog', None),
            ('leaderboard', 'Leaderboard', 'leaderboard', None),
            ('badges_earned', 'Badges Earned', 'badges_earned', None),
        ]
        
        for i, (key, label, comp, feat) in enumerate(learner_widgets):
            DashboardWidget.objects.get_or_create(workspace=learner_ws, key=key, defaults={
                'label': label, 'component_key': comp, 'order': i
            })
            
        # Also update actual Roles so existing users can see appropriate workspaces
        from organizations.models import Role
        for role in Role.objects.all():
            if role.is_admin_role:
                role.workspaces.set([admin_ws])
            else:
                role.workspaces.set([learner_ws])

        self.stdout.write(self.style.SUCCESS('Workspaces and nav items seeded successfully.'))
