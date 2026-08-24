from django.conf import settings
import csv
from django.http import HttpResponse
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import Organization, Site, BillingConfiguration, Department, Role
from .serializers import OrganizationSerializer, SiteSerializer, BillingConfigurationSerializer, DepartmentSerializer, RoleSerializer
from .permissions import IsOrgScoped
from .audit import log_activity


class PlatformStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not (
            getattr(request.user, 'is_platform_super_admin', False)
            or getattr(request.user, 'is_superuser', False)
            or getattr(request.user, 'is_staff', False)
        ):
            return Response({'detail': 'Forbidden'}, status=403)

        from django.contrib.auth import get_user_model
        User = get_user_model()

        total_orgs = Organization.objects.count()
        # "active_organizations" = orgs whose status field is active (case-insensitive)
        active_orgs = Organization.objects.filter(status__iexact='active').count()
        total_sites = Site.objects.count()
        total_users = User.objects.filter(is_active=True).count()

        return Response({
            'organizations': total_orgs,
            'active_organizations': active_orgs,
            'sites': total_sites,
            'active_users': total_users,
        })

class OrganizationViewSet(viewsets.ModelViewSet):
    """
    Platform super-admins see all organizations.
    Org-admins should use /api/organizations/my/ to see only their own org.
    This list endpoint is super-admin only for safety.
    """
    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated, IsOrgScoped]

    def get_queryset(self):
        if self.request.user.is_platform_super_admin:
            return Organization.objects.all()
        # Org-scoped users can only see their own organization
        return Organization.objects.filter(id=self.request.user.organization_id)

    def perform_create(self, serializer):
        org = serializer.save()
        log_activity(self.request, 'org_created', target=org, organization=org)

    def perform_update(self, serializer):
        org = serializer.save()
        log_activity(self.request, 'org_updated', target=org, organization=org)

    def perform_destroy(self, instance):
        log_activity(self.request, 'org_deleted', target=instance, organization=instance)
        instance.delete()

    @action(detail=False, methods=['get'], url_path='export')
    def export_organizations(self, request):
        queryset = self.filter_queryset(self.get_queryset())

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="organizations_export.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'Organization ID',
            'Organization Name',
            'Subdomain',
            'Company Name',
            'Entity Name',
            'Contact Name',
            'Contact Email',
            'Contact Phone',
            'Company Address',
            'City',
            'State',
            'Region',
            'Country',
            'Total Sites',
            'Status',
            'Created At'
        ])

        for org in queryset:
            writer.writerow([
                org.id,
                org.name or '',
                org.sub_domain or '',
                org.company_name or '',
                org.entity_name or '',
                org.contact_name or '',
                org.contact_email or '',
                org.contact_phone or '',
                org.company_address or '',
                org.city or '',
                org.state or '',
                org.region or '',
                org.country or '',
                org.sites.count() if hasattr(org, 'sites') else 0,
                org.status or '',
                org.created_at.strftime('%Y-%m-%d %H:%M:%S') if getattr(org, 'created_at', None) else ''
            ])

        return response


class MyOrganizationView(APIView):
    """Returns the requesting user's own organization including enabled feature keys."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.organization:
            return Response({'detail': 'Not associated with any organization.'}, status=404)
        org = request.user.organization
        data = OrganizationSerializer(org).data
        
        from master_setup.models import OrganizationFeatureAccess
        enabled_features = list(OrganizationFeatureAccess.objects.filter(
            organization=org, enabled=True
        ).values_list('feature__key', flat=True))
        
        data['enabled_features'] = enabled_features
        return Response(data)


class MyOrganizationStatsView(APIView):
    """Returns rich real-time stats for the user's organization."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.organization:
            return Response({'detail': 'Not associated with any organization.'}, status=404)
        
        org = request.user.organization
        from django.contrib.auth import get_user_model
        from courses.models import Course, AssessmentAttempt, AccessRequest
        from .models import Department, Site, ActivityLog
        User = get_user_model()
        
        total_users = User.objects.filter(organization=org).count()
        active_learners = User.objects.filter(organization=org, is_active=True).count()
        total_depts = Department.objects.filter(organization=org).count()
        total_courses = Course.objects.filter(organization=org).count()
        published_courses = Course.objects.filter(organization=org, status='published').count()
        total_sites = Site.objects.filter(organization=org).count()
        pending_regs = AccessRequest.objects.filter(course__organization=org, status='pending').count()

        attempts = AssessmentAttempt.objects.filter(user__organization=org)
        avg_score = 0
        if attempts.exists():
            from django.db.models import Avg
            avg_result = attempts.aggregate(Avg('score_percent'))
            if avg_result['score_percent__avg'] is not None:
                avg_score = int(avg_result['score_percent__avg'])

        logs = ActivityLog.objects.filter(organization=org).order_by('-created_at')[:6]
        recent_activity = [
            {
                'id': log.id,
                'action': log.action,
                'action_display': log.get_action_display(),
                'actor_name': log.actor.full_name if log.actor else 'System',
                'target_label': log.target_label or '',
                'created_at': log.created_at.isoformat()
            }
            for log in logs
        ]

        return Response({
            'active_learners': active_learners,
            'total_users': total_users,
            'total_departments': total_depts,
            'total_courses': total_courses,
            'published_courses': published_courses,
            'total_sites': total_sites,
            'pending_registrations': pending_regs,
            'avg_assessment_score': avg_score,
            'recent_activity': recent_activity,
        })


class SiteViewSet(viewsets.ModelViewSet):
    serializer_class = SiteSerializer
    permission_classes = [IsAuthenticated, IsOrgScoped]

    def get_queryset(self):
        qs = Site.objects.all()
        if self.request.user.is_platform_super_admin:
            return qs
        return qs.filter(organization_id=self.request.user.organization_id)

    def perform_create(self, serializer):
        site = serializer.save()
        log_activity(self.request, 'site_created', target=site, organization=site.organization)
        
        # Send dynamic welcome email with login portal URL link & credentials
        if site.organization:
            from .emails import send_tenant_welcome_email
            target_email = site.contact_email or site.organization.contact_email
            if target_email:
                send_tenant_welcome_email(
                    org=site.organization,
                    recipient_email=target_email,
                    admin_username=target_email,
                    site=site
                )

    def perform_update(self, serializer):
        site = serializer.save()
        log_activity(self.request, 'site_updated', target=site, organization=site.organization)

    def perform_destroy(self, instance):
        log_activity(self.request, 'site_deleted', target=instance, organization=instance.organization)
        instance.delete()


class BillingConfigurationViewSet(viewsets.ModelViewSet):
    serializer_class = BillingConfigurationSerializer
    permission_classes = [IsAuthenticated, IsOrgScoped]

    def get_queryset(self):
        qs = BillingConfiguration.objects.all()
        org_id = self.request.query_params.get('organization')
        if org_id:
            qs = qs.filter(organization_id=org_id)
        if self.request.user.is_platform_super_admin:
            return qs
        return qs.filter(organization_id=self.request.user.organization_id)

    def perform_update(self, serializer):
        old_status = getattr(self.get_object(), 'status', None) if self.get_object() else None
        billing = serializer.save()
        new_status = billing.status
        if old_status and old_status != new_status:
            log_activity(self.request, 'billing_status_changed', target=billing, organization=billing.organization, metadata={'old_status': old_status, 'new_status': new_status})
        else:
            log_activity(self.request, 'billing_updated', target=billing, organization=billing.organization)

    def perform_create(self, serializer):
        billing = serializer.save()
        log_activity(self.request, 'billing_updated', target=billing, organization=billing.organization)

class HasRolePermission(permissions.BasePermission):
    """
    Evaluates role permissions dynamically for DRF ViewSets based on action method:
    - View (list/retrieve/GET): can_view_* or is_admin_role
    - Create (create/POST): can_create_* or is_admin_role
    - Edit (update/partial_update/PUT/PATCH): can_edit_* or is_admin_role
    - Delete (destroy/DELETE): can_delete_* or is_admin_role
    """
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_platform_super_admin:
            return True
        if not user.role:
            return False
        if user.role.is_admin_role:
            return True

        perm = getattr(view, 'required_permission', None)
        if not perm:
            return True

        role = user.role
        action = getattr(view, 'action', None) or request.method.lower()

        if 'user' in perm or 'department' in perm:
            domain = 'users'
        elif 'role' in perm:
            domain = 'roles'
        elif 'course' in perm:
            domain = 'courses'
        elif 'certificate' in perm:
            domain = 'certificates'
        elif 'report' in perm:
            domain = 'reports'
        elif 'module_access' in perm:
            domain = 'module_access'
        elif 'activity' in perm:
            domain = 'activity_log'
        else:
            return bool(getattr(role, perm, False))

        if action in ['list', 'retrieve', 'get']:
            has_cap = getattr(role, f'can_view_{domain}', False) or getattr(role, perm, False)
        elif action in ['create', 'post']:
            has_cap = getattr(role, f'can_create_{domain}', False) or getattr(role, perm, False)
        elif action in ['update', 'partial_update', 'put', 'patch']:
            has_cap = getattr(role, f'can_edit_{domain}', False) or getattr(role, perm, False)
        elif action in ['destroy', 'delete']:
            has_cap = getattr(role, f'can_delete_{domain}', False) or getattr(role, perm, False)
        else:
            has_cap = getattr(role, perm, False)

        if not has_cap:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied(f"Permission denied for action '{action}' on {domain}.")

        return True


class DepartmentViewSet(viewsets.ModelViewSet):
    serializer_class = DepartmentSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrgScoped, HasRolePermission]
    required_permission = 'can_manage_departments'

    def get_queryset(self):
        if self.request.user.is_platform_super_admin:
            return Department.objects.all()
        return Department.objects.filter(organization_id=self.request.user.organization_id)

    def perform_create(self, serializer):
        serializer.save(organization=self.request.user.organization)


class RoleViewSet(viewsets.ModelViewSet):
    serializer_class = RoleSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrgScoped, HasRolePermission]
    required_permission = 'can_manage_roles'

    def get_queryset(self):
        if self.request.user.is_platform_super_admin:
            return Role.objects.all()
        return Role.objects.filter(organization_id=self.request.user.organization_id)

    def perform_create(self, serializer):
        if self.request.user.is_platform_super_admin:
            org_id = self.request.data.get('organization')
            if not org_id:
                from rest_framework.exceptions import ValidationError
                raise ValidationError({'organization': 'Organization is required when creating a role as super-admin.'})
            role = serializer.save(organization_id=org_id, is_admin_role=True)
        else:
            role = serializer.save(organization=self.request.user.organization, is_admin_role=False)
        log_activity(self.request, 'role_created', target=role, organization=role.organization)

    def perform_update(self, serializer):
        if not self.request.user.is_platform_super_admin and self.get_object().is_admin_role:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Org Admins cannot modify Admin roles.")
        role = serializer.save()
        log_activity(self.request, 'role_updated', target=role, organization=role.organization)

    def perform_destroy(self, instance):
        if not self.request.user.is_platform_super_admin and instance.is_admin_role:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Org Admins cannot delete Admin roles.")
        if instance.is_default:
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Default roles (Admin/Instructor/Student) can't be deleted.")
        if instance.users.exists():
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Reassign users off this role before deleting it.")
        log_activity(self.request, 'role_deleted', target=instance, organization=instance.organization)
        instance.delete()



from .serializers import CertificateTemplateSerializer
from .models import CertificateTemplate
class CertificateTemplateViewSet(viewsets.ModelViewSet):
    serializer_class = CertificateTemplateSerializer
    required_permission = 'can_manage_certificates'

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.IsAuthenticated(), IsOrgScoped()]
        return [permissions.IsAuthenticated(), IsOrgScoped(), HasRolePermission()]

    def get_queryset(self):
        qs = CertificateTemplate.objects.all()
        if self.request.user.is_platform_super_admin:
            return qs
        return qs.filter(organization_id=self.request.user.organization_id)

    def _assign_courses(self, template, course_ids):
        """Assign courses to this template via Course.certificate_template FK."""
        from courses.models import Course
        org = template.organization
        # Remove this template from courses that are no longer selected
        Course.objects.filter(certificate_template=template).exclude(id__in=course_ids).update(certificate_template=None)
        # Assign new courses — scoped to org and only draft/published
        if course_ids:
            qs = Course.objects.filter(id__in=course_ids, status__in=['draft', 'published'])
            if org:
                qs = qs.filter(organization=org)
            qs.update(certificate_template=template)

    def perform_create(self, serializer):
        if not self.request.user.is_platform_super_admin:
            template = serializer.save(organization=self.request.user.organization)
        else:
            template = serializer.save()
        course_ids = self.request.data.get('course_ids', [])
        if course_ids:
            self._assign_courses(template, course_ids)

    def perform_update(self, serializer):
        template = serializer.save()
        if 'course_ids' in self.request.data:
            self._assign_courses(template, self.request.data.get('course_ids', []))

from .models import ActivityLog
from .serializers import ActivityLogSerializer

class ActivityLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only — logs are never edited or deleted through the API, that would defeat the point of an audit trail."""
    serializer_class = ActivityLogSerializer
    permission_classes = [permissions.IsAuthenticated, HasRolePermission]
    required_permission = 'can_view_activity_log'

    def get_queryset(self):
        from django.db import models
        qs = ActivityLog.objects.select_related('actor', 'organization').all()
        # Only Super Admin and Org/Site Admin actions belong in this feed — never students or instructors
        qs = qs.filter(
            models.Q(actor__is_platform_super_admin=True) | models.Q(actor__role__is_admin_role=True)
        )
        user = self.request.user
        if not user.is_platform_super_admin:
            # Org-admins only ever see their own org's activity — never cross-tenant, even here
            qs = qs.filter(organization_id=user.organization_id)

        # Filters — all optional query params
        params = self.request.query_params
        if org_id := params.get('organization'):
            qs = qs.filter(organization_id=org_id)
        if actor_id := params.get('actor'):
            qs = qs.filter(actor_id=actor_id)
        if action := params.get('action'):
            qs = qs.filter(action=action)
        if date_from := params.get('date_from'):
            qs = qs.filter(created_at__gte=date_from)
        if date_to := params.get('date_to'):
            qs = qs.filter(created_at__lte=date_to)
        return qs

    from rest_framework.decorators import action
    @action(detail=False, methods=['get'])
    def recent(self, request):
        qs = self.get_queryset()
        try:
            limit = int(request.query_params.get('limit', 10))
        except ValueError:
            limit = 10
        qs = qs[:limit]
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

class MyWorkspacesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        role = user.role
        from master_setup.models import Workspace, NavItem, SiteFeatureAccess
        from django.core.management import call_command

        try:
            from organizations.management.commands.seed_workspaces import ADMIN_NAV_ITEMS, LEARNER_NAV_ITEMS
            expected_keys = {item[0] for item in ADMIN_NAV_ITEMS} | {item[0] for item in LEARNER_NAV_ITEMS}
            existing_keys = set(NavItem.objects.values_list('key', flat=True))
            if not expected_keys.issubset(existing_keys):
                call_command('seed_workspaces')
        except Exception:
            pass

        # Resolve workspaces dynamically based on account type and role
        if user.is_platform_super_admin:
            workspaces = Workspace.objects.all().order_by('order')
        elif role and role.is_admin_role:
            workspaces = Workspace.objects.filter(key='admin').order_by('order')
            if not workspaces.exists():
                workspaces = Workspace.objects.all().order_by('order')
        else:
            # End Users (Manager, HR, Learner, Instructor, Employee, etc.) get ONLY the learner/user workspace
            workspaces = Workspace.objects.filter(key='learner').order_by('order')
            if not workspaces.exists():
                workspaces = Workspace.objects.all().order_by('order')

        result = []
        for ws in workspaces:
            all_candidate_items = list(ws.nav_items.select_related('feature').order_by('order'))

            visible_items = []
            seen_keys = set()
            for item in all_candidate_items:
                if item.key in seen_keys:
                    continue

                # Gate 1: Dynamic Organization & Site Feature Check
                if user.organization and not user.is_platform_super_admin:
                    # Overview / Dashboard / Profile is core platform landing page - always accessible
                    if item.key not in ['overview', 'dashboard', 'my_profile', 'profile']:
                        from master_setup.models import OrganizationFeatureAccess
                        feat_key = item.feature.key if item.feature else None
                        if not feat_key:
                            key_map = {
                                'messenger': 'internal_messenger',
                                'content_authoring': 'content_authoring',
                                'certificates_admin': 'certifications',
                                'certifications': 'certifications',
                                'course_catalog_admin': 'course_catalog',
                                'course_catalog': 'course_catalog',
                                'learning_paths': 'learning_paths',
                                'ai_assistant': 'ai_assistant',
                                'users_departments': 'users_departments',
                                'roles_permissions': 'roles_permissions',
                                'module_access': 'module_access',
                                'activity_log': 'activity_log',
                                'assessment_activity': 'assessment_activity',
                                'pending_registration': 'pending_registration',
                            }
                            feat_key = key_map.get(item.key, item.key)

                        if feat_key:
                            org_access = OrganizationFeatureAccess.objects.filter(
                                organization=user.organization,
                                feature__key=feat_key
                            ).first()
                            # Only hide if explicitly disabled. No row = default allow.
                            if org_access is not None and not org_access.enabled:
                                continue

                # Gate 2: Permission check against the user's role
                if not user.is_platform_super_admin:
                    if item.required_permission:
                        if item.required_permission == 'is_admin_role':
                            if not role or not role.is_admin_role:
                                continue
                        elif not role:
                            continue
                        else:
                            perm_key = item.required_permission
                            view_perm_map = {
                                'can_manage_users': 'can_view_users',
                                'can_manage_departments': 'can_view_users',
                                'can_manage_roles': 'can_view_roles',
                                'can_create_courses': 'can_view_courses',
                                'can_edit_courses': 'can_view_courses',
                                'can_manage_module_access': 'can_view_module_access',
                                'can_manage_certificates': 'can_view_certificates',
                                'can_view_reports': 'can_view_reports',
                                'can_view_activity_log': 'can_view_activity_log',
                            }
                            granular_perm = view_perm_map.get(perm_key, perm_key)
                            has_perm = (
                                getattr(role, perm_key, False) or 
                                getattr(role, granular_perm, False) or 
                                (role.is_admin_role and ws.key == 'admin')
                            )
                            if not has_perm:
                                continue

                seen_keys.add(item.key)
                route_path = '/org-admin' if (ws.key == 'admin' and item.key == 'overview') else item.route

                visible_items.append({
                    'key': item.key,
                    'label': item.label,
                    'icon': item.icon,
                    'route': route_path,
                    'order': item.order,
                })
                
            widgets = ws.widgets.select_related('feature').order_by('order')
            visible_widgets = []
            for w in widgets:
                if w.feature and user.organization:
                    from master_setup.models import OrganizationFeatureAccess
                    org_access = OrganizationFeatureAccess.objects.filter(
                        organization=user.organization, feature=w.feature
                    ).first()
                    if org_access and not org_access.enabled and not user.is_platform_super_admin:
                        continue

                visible_widgets.append({
                    'key': w.key,
                    'label': w.label,
                    'component_key': w.component_key,
                    'order': w.order
                })
                
            result.append({
                'workspace_key': ws.key,
                'workspace_label': ws.label,
                'workspace_icon': ws.icon,
                'nav_items': visible_items,
                'widgets': visible_widgets,
            })

        return Response({
            'user_display_name': user.full_name or user.username,
            'user_email': user.email,
            'organization_name': user.organization.name if user.organization else None,
            'workspaces': result,
        })


class GlobalSearchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        query = request.GET.get('q', '').strip()
        workspace_key = request.GET.get('workspace', 'learner')
        user = request.user

        results = []
        if not query:
            return Response({'results': []})
            
        lower_q = query.lower()
        from django.contrib.auth import get_user_model
        from django.db.models import Q
        from courses.models import Course, LearningPath, IssuedCertificate
        from organizations.models import Department, Role, CertificateTemplate, Organization, Site
        User = get_user_model()
        
        # ── 1. CONSOLE-SCOPED NAV SHORTCUTS & PAGE SEARCH ────────────────────
        if workspace_key == 'admin':
            admin_pages = [
                {'name': 'Overview', 'route': '/org-admin', 'keywords': ['overview', 'dashboard', 'admin', 'home', 'o']},
                {'name': 'Users & Departments', 'route': '/org-admin/departments', 'keywords': ['users', 'user', 'departments', 'department', 'dept', 'u']},
                {'name': 'Roles & Permissions', 'route': '/org-admin/roles', 'keywords': ['roles', 'role', 'permissions', 'permission', 'rbac', 'r']},
                {'name': 'Module Access', 'route': '/org-admin/module-access', 'keywords': ['module access', 'modules', 'access', 'toggles']},
                {'name': 'Course Catalog Admin', 'route': '/org-admin/courses', 'keywords': ['courses', 'course', 'catalog']},
                {'name': 'Learning Paths Admin', 'route': '/org-admin/paths', 'keywords': ['learning paths', 'learning path', 'paths', 'path']},
                {'name': 'Certificates Admin', 'route': '/org-admin/certificates', 'keywords': ['certificates', 'certificate', 'cert', 'certs', 'templates']},
                {'name': 'Activity Log', 'route': '/org-admin/activity', 'keywords': ['activity log', 'activity', 'audit', 'logs', 'log']},
                {'name': 'Content Authoring', 'route': '/authoring', 'keywords': ['content authoring', 'authoring', 'builder', 'editor', 'create course']},
                {'name': 'Pending Registration', 'route': '/pending-registration', 'keywords': ['pending registration', 'pending', 'approvals', 'registrations']},
                {'name': 'Messenger', 'route': '/messenger', 'keywords': ['messenger', 'messages', 'message', 'chat', 'msg', 'm']},
                {'name': 'My Profile', 'route': '/org-admin/profile', 'keywords': ['my profile', 'profile', 'personal information', 'account', 'password', 'p']},
            ]
            for page in admin_pages:
                if any(kw.startswith(lower_q) or lower_q in kw for kw in page['keywords']):
                    results.append({'type': 'page', 'name': page['name'], 'id': page['route'], 'subtitle': 'Nav Shortcut'})

        elif workspace_key == 'super_admin':
            # ── SUPER ADMIN CONSOLE: Fully isolated — platform-level entities ONLY ─
            # NEVER searches org-scoped data: Courses, Paths, Certificates, Users,
            # Departments, Roles. Those belong to org/learner consoles, not super admin.

            super_pages = [
                {'name': 'Super Admin Dashboard', 'route': '/super-admin', 'keywords': ['super admin', 'dashboard', 'overview', 's']},
                {'name': 'Organizations (Tenants)', 'route': '/super-admin/organizations', 'keywords': ['organizations', 'organization', 'tenants', 'tenant', 'orgs', 'org']},
                {'name': 'Site Management', 'route': '/super-admin/sites', 'keywords': ['sites', 'site', 'portals', 'domains']},
                {'name': 'Subscription Plans', 'route': '/super-admin/plans', 'keywords': ['plans', 'subscriptions', 'billing', 'pricing', 'plan']},
                {'name': 'Access Control', 'route': '/super-admin/access-control', 'keywords': ['access control', 'access', 'control', 'workspaces', 'features']},
                {'name': 'Global Settings', 'route': '/super-admin/settings', 'keywords': ['global settings', 'settings', 'configuration', 'config']},
                {'name': 'Billing & Payments', 'route': '/super-admin/billing', 'keywords': ['billing', 'payments', 'payment', 'invoices', 'invoice']},
                {'name': 'Activity Log', 'route': '/super-admin/activity', 'keywords': ['activity log', 'activity', 'audit', 'logs', 'log']},
                {'name': 'Master Toolkit', 'route': '/super-admin/toolkit', 'keywords': ['master toolkit', 'toolkit', 'tools', 'utility', 'utilities']},
                {'name': 'My Profile', 'route': '/super-admin/profile', 'keywords': ['my profile', 'profile', 'personal information', 'account', 'password', 'p']},
            ]
            for page in super_pages:
                if any(kw.startswith(lower_q) or lower_q in kw for kw in page['keywords']):
                    results.append({'type': 'page', 'name': page['name'], 'id': page['route'], 'subtitle': 'Nav Shortcut'})

            # Organizations — primary platform-level entity
            from django.db.models import Q as Q2
            orgs = Organization.objects.filter(
                Q2(name__icontains=query) |
                Q2(company_name__icontains=query) |
                Q2(entity_name__icontains=query) |
                Q2(sub_domain__icontains=query)
            ).distinct()[:6]
            results += [
                {'type': 'organization', 'name': o.name, 'id': o.id, 'subtitle': f'Tenant • {o.sub_domain}'}
                for o in orgs
            ]

            # Sites — platform-managed deployment units
            sites = Site.objects.filter(
                Q2(name__icontains=query) |
                Q2(site_code__icontains=query)
            ).select_related('organization').distinct()[:5]
            results += [
                {'type': 'site', 'name': s.name, 'id': s.id,
                 'subtitle': f'Site • {s.organization.name if s.organization else ""}'}
                for s in sites
            ]

            # Plans — subscription plans managed at platform level
            try:
                from master_setup.models import Plan
                plans = Plan.objects.filter(
                    Q2(name__icontains=query)
                ).distinct()[:5]
                results += [
                    {'type': 'plan', 'name': p.name, 'id': p.id, 'subtitle': 'Subscription Plan'}
                    for p in plans
                ]
            except Exception:
                pass

            # Return immediately — do NOT fall through to org-scoped model searches
            return Response({'results': results})

        else:
            # Default: Learner / End-User Console (Strictly End-User Console Scope)
            learner_pages = [
                {'name': 'Dashboard', 'route': '/dashboard', 'keywords': ['dashboard', 'dash', 'home', 'overview', 'd']},
                {'name': 'Course Catalog', 'route': '/catalog', 'keywords': ['course catalog', 'catalog', 'courses', 'course', 'browse', 'cat', 'c']},
                {'name': 'Learning Paths', 'route': '/paths', 'keywords': ['learning paths', 'learning path', 'paths', 'path', 'curriculum', 'track', 'p']},
                {'name': 'Certifications', 'route': '/certificates', 'keywords': ['certifications', 'certification', 'certificates', 'certificate', 'cert', 'certs', 'qualification']},
                {'name': 'AI Assistant', 'route': '/ai-assistant', 'keywords': ['ai assistant', 'ai', 'assistant', 'tutor', 'bot', 'gpt', 'a']},
                {'name': 'Messenger', 'route': '/messenger', 'keywords': ['messenger', 'messages', 'message', 'msg', 'chat', 'm']},
                {'name': 'My Profile', 'route': '/profile', 'keywords': ['my profile', 'profile', 'personal information', 'account', 'password', 'p']},
            ]
            for page in learner_pages:
                if any(kw.startswith(lower_q) or lower_q in kw for kw in page['keywords']):
                    results.append({'type': 'page', 'name': page['name'], 'id': page['route'], 'subtitle': 'Nav Shortcut'})


        # ── 2. DYNAMIC MODEL SEARCH (Tenant Isolated) ───────────────────────
        if user.organization:
            org_filter = {'organization': user.organization}
        else:
            org_filter = {'organization__isnull': True}
        
        # Courses (Title, Subtitle, Category, Level)
        course_base_qs = Course.objects.filter(**org_filter)
        if workspace_key == 'learner':
            course_base_qs = course_base_qs.filter(status='published')
        if 'untitled' not in lower_q:
            course_base_qs = course_base_qs.exclude(title__icontains='Untitled')

        courses = course_base_qs.filter(
            Q(title__icontains=query) |
            Q(subtitle__icontains=query) |
            Q(category__icontains=query) |
            Q(level__icontains=query)
        ).distinct()[:5]

        for c in courses:
            sub = f"{c.category or 'Course'} • {c.status.capitalize()}" if workspace_key == 'admin' else (c.category or 'Course')
            results.append({'type': 'course', 'name': c.title, 'id': c.id, 'subtitle': sub})

        # Learning Paths (Title, Description)
        paths = LearningPath.objects.filter(
            **org_filter
        ).filter(
            Q(title__icontains=query) |
            Q(description__icontains=query)
        ).distinct()[:5]
        results += [{'type': 'path', 'name': p.title, 'id': p.id, 'subtitle': 'Learning Path'} for p in paths]

        # Certifications (IssuedCertificates for learner, CertificateTemplates for admin)
        if workspace_key == 'admin' or (user.role and user.role.is_admin_role):
            cert_tpls = CertificateTemplate.objects.filter(
                **org_filter
            ).filter(
                Q(title__icontains=query)
            ).distinct()[:5]
            results += [{'type': 'certificate', 'name': ct.title, 'id': ct.id, 'subtitle': 'Certificate Template'} for ct in cert_tpls]

        if workspace_key == 'learner':
            certs = IssuedCertificate.objects.filter(
                user=user
            ).filter(
                Q(course__title__icontains=query) |
                Q(certificate_id__icontains=query)
            ).select_related('course')[:5]

            results += [{
                'type': 'certificate', 
                'name': f"{c.course.title} Certificate", 
                'id': c.id, 
                'subtitle': 'Issued Certificate'
            } for c in certs]

        # Admin multi-domain search (Users, Departments, Roles)
        if workspace_key == 'admin' or (user.role and user.role.is_admin_role):
            users = User.objects.filter(
                **org_filter
            ).filter(
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query) |
                Q(username__icontains=query) |
                Q(email__icontains=query) |
                Q(job_title__icontains=query)
            ).distinct()[:5]
            results += [{'type': 'user', 'name': u.full_name or u.username or u.email, 'id': u.id, 'subtitle': 'User'} for u in users]

            departments = Department.objects.filter(
                **org_filter
            ).filter(
                Q(name__icontains=query)
            ).distinct()[:5]
            results += [{'type': 'department', 'name': d.name, 'id': d.id, 'subtitle': 'Department'} for d in departments]

            roles = Role.objects.filter(
                **org_filter
            ).filter(
                Q(name__icontains=query)
            ).distinct()[:5]
            results += [{'type': 'role', 'name': r.name, 'id': r.id, 'subtitle': 'Role'} for r in roles]

        return Response({'results': results})


class SendOrgWelcomeEmailView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not (getattr(request.user, 'is_platform_super_admin', False) or getattr(request.user, 'is_superuser', False) or getattr(request.user, 'is_staff', False)):
            return Response({'detail': 'Forbidden'}, status=403)
        try:
            org = Organization.objects.get(pk=pk)
        except Organization.DoesNotExist:
            return Response({'detail': 'Organization not found'}, status=404)

        from .emails import send_tenant_welcome_email
        from django.contrib.auth import get_user_model
        User = get_user_model()

        admin_u = User.objects.filter(organization=org).first()
        recipient = request.data.get('recipient_email') or (admin_u.email if admin_u else None) or org.contact_email
        if not recipient:
            return Response({'detail': 'No registered contact email address found for this organization.'}, status=400)

        raw_pass = request.data.get('password') or request.data.get('raw_password') or 'Admin123!'

        success, msg = send_tenant_welcome_email(
            org=org,
            recipient_email=recipient,
            admin_username=recipient,
            raw_password=raw_pass,
            request=request
        )
        from .emails import resolve_frontend_url
        base_url = resolve_frontend_url(request)
        return Response({
            'success': success,
            'message': msg,
            'recipient': recipient,
            'sub_domain': org.sub_domain,
            'login_url': f"{base_url}/login/{org.sub_domain}" if org.sub_domain else f"{base_url}/login"
        })


class SendSiteWelcomeEmailView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not (getattr(request.user, 'is_platform_super_admin', False) or getattr(request.user, 'is_superuser', False) or getattr(request.user, 'is_staff', False)):
            return Response({'detail': 'Forbidden'}, status=403)
        try:
            site = Site.objects.get(pk=pk)
        except Site.DoesNotExist:
            return Response({'detail': 'Site not found'}, status=404)

        if not site.organization:
            return Response({'detail': 'Site has no associated parent organization'}, status=400)

        from .emails import send_tenant_welcome_email, resolve_frontend_url
        recipient = request.data.get('recipient_email') or site.contact_email or site.organization.contact_email
        if not recipient:
            return Response({'detail': 'No registered contact email address found for this site.'}, status=400)

        success, msg = send_tenant_welcome_email(
            org=site.organization,
            recipient_email=recipient,
            admin_username=recipient,
            site=site,
            request=request
        )
        base_url = resolve_frontend_url(request)
        return Response({
            'success': success,
            'message': msg,
            'recipient': recipient,
            'site': site.name,
            'login_url': f"{base_url}/login/{site.organization.sub_domain}" if site.organization.sub_domain else f"{base_url}/login"
        })


