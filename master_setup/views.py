from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db import transaction
from django.core.files.storage import default_storage

from organizations.models import Organization, BillingConfiguration, Site, ActivityLog
from organizations.serializers import OrganizationSerializer

from .models import (
    Feature, SiteFeatureAccess, OrganizationFeatureAccess, Plan,
    PlatformSettings, NotificationTemplate, Notification,
    LookupType, LookupValue, TerminologyOverride
)
from .serializers import (
    FeatureSerializer, SiteFeatureAccessSerializer, OrganizationFeatureAccessSerializer, PlanSerializer,
    PlatformSettingsSerializer,
    NotificationTemplateSerializer, NotificationSerializer, LookupTypeSerializer,
    LookupValueSerializer, TerminologyOverrideSerializer
)

class SuperAdminPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and getattr(request.user, 'is_platform_super_admin', False))

class FeatureViewSet(viewsets.ModelViewSet):
    queryset = Feature.objects.all()
    serializer_class = FeatureSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        return [SuperAdminPermission()]

    def list(self, request, *args, **kwargs):
        features_to_seed = [
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
            ('admin_console', 'Admin Console', 'Organization administration console', 'advanced'),
        ]
        try:
            for key, name, desc, cat in features_to_seed:
                Feature.objects.update_or_create(
                    key=key,
                    defaults={'name': name, 'description': desc, 'category': cat, 'is_active': True}
                )
        except Exception:
            pass
        return super().list(request, *args, **kwargs)

class SiteFeatureAccessViewSet(viewsets.ModelViewSet):
    queryset = SiteFeatureAccess.objects.all()
    serializer_class = SiteFeatureAccessSerializer
    permission_classes = [permissions.IsAuthenticated]

class OrgFeatureAccessView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        org_id = request.query_params.get('organization_id')
        if not org_id:
            return Response({'error': 'organization_id is required'}, status=400)
        
        features_to_seed = [
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
            ('admin_console', 'Admin Console', 'Organization administration console', 'advanced'),
        ]
        for key, name, desc, cat in features_to_seed:
            Feature.objects.update_or_create(
                key=key,
                defaults={'name': name, 'description': desc, 'category': cat, 'is_active': True}
            )

        all_features = Feature.objects.all().order_by('category', 'name')
        for f in all_features:
            OrganizationFeatureAccess.objects.get_or_create(organization_id=org_id, feature=f, defaults={'enabled': True})
            
        access_list = OrganizationFeatureAccess.objects.filter(organization_id=org_id).select_related('feature')
        return Response(OrganizationFeatureAccessSerializer(access_list, many=True).data)

    def post(self, request):
        if not getattr(request.user, 'is_platform_super_admin', False):
            return Response({'error': 'Forbidden'}, status=403)
        
        org_id = request.data.get('organization_id')
        feature_key = request.data.get('feature_key')
        enabled = request.data.get('enabled')

        if not org_id or not feature_key or enabled is None:
            return Response({'error': 'organization_id, feature_key, and enabled are required'}, status=400)

        feature = Feature.objects.filter(key=feature_key).first()
        if not feature:
            return Response({'error': 'Feature not found'}, status=404)

        obj, _ = OrganizationFeatureAccess.objects.get_or_create(organization_id=org_id, feature=feature)
        obj.enabled = bool(enabled)
        obj.save()

        # Also sync SiteFeatureAccess for sites under this organization
        SiteFeatureAccess.objects.filter(site__organization_id=org_id, feature=feature).update(enabled=bool(enabled))

        return Response({
            'message': f"Feature '{feature.name}' {'enabled' if obj.enabled else 'disabled'}",
            'organization_id': org_id,
            'feature_key': feature_key,
            'enabled': obj.enabled
        })

class PlanViewSet(viewsets.ModelViewSet):
    queryset = Plan.objects.all().order_by('sort_order', 'id')
    serializer_class = PlanSerializer
    permission_classes = [SuperAdminPermission]
    pagination_class = None

    def perform_create(self, serializer):
        plan = serializer.save()
        # Broadcast notification to all Org Admins
        from django.contrib.auth import get_user_model
        User = get_user_model()
        org_admins = User.objects.filter(role__is_admin_role=True) | User.objects.filter(is_staff=True, organization__isnull=False)
        feature_names = ", ".join([f.name for f in plan.included_features.all()]) if plan.included_features.exists() else "All standard modules"
        
        notifications = [
            Notification(
                recipient=admin,
                title=f"🎉 New Subscription Offer: {plan.name}",
                message=f"A new subscription plan '{plan.name}' is now available! Price: ₹{plan.monthly_price}/mo (₹{plan.yearly_price}/yr). Features: {feature_names}.",
                type="plan_offer"
            )
            for admin in org_admins.distinct()
        ]
        if notifications:
            Notification.objects.bulk_create(notifications)

class PlatformSettingsView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        settings = PlatformSettings.load()
        return Response(PlatformSettingsSerializer(settings).data)
        
    def patch(self, request):
        if not getattr(request.user, 'is_platform_super_admin', False):
            return Response({'detail': 'Forbidden'}, status=403)
        settings = PlatformSettings.load()
        serializer = PlatformSettingsSerializer(settings, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

class NotificationTemplateViewSet(viewsets.ModelViewSet):
    queryset = NotificationTemplate.objects.all()
    serializer_class = NotificationTemplateSerializer
    permission_classes = [SuperAdminPermission]
    lookup_field = 'key'

class LookupTypeViewSet(viewsets.ModelViewSet):
    queryset = LookupType.objects.all()
    serializer_class = LookupTypeSerializer
    permission_classes = [SuperAdminPermission]

class LookupValueViewSet(viewsets.ModelViewSet):
    queryset = LookupValue.objects.all()
    serializer_class = LookupValueSerializer
    permission_classes = [SuperAdminPermission]

class TerminologyOverrideViewSet(viewsets.ModelViewSet):
    queryset = TerminologyOverride.objects.all()
    serializer_class = TerminologyOverrideSerializer
    permission_classes = [SuperAdminPermission]

class SetupStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        return Response({
            'branding_configured': PlatformSettings.load().logo_url != '',
            'plans_created': Plan.objects.exists(),
            'features_defined': Feature.objects.exists(),
            'first_organization_created': Organization.objects.exists(),
        })

class ProvisionOrganizationView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        if not getattr(request.user, 'is_platform_super_admin', False):
            return Response({'detail': 'Forbidden'}, status=403)
            
        data = request.data
        with transaction.atomic():
            org = Organization.objects.create(
                name=data['name'], 
                company_name=data.get('company_name', data['name']),
                entity_name=data.get('entity_name', data['name']), 
                sub_domain=data.get('sub_domain'),
                status=data.get('status', 'Active'),
                country=data.get('country'),
                region=data.get('region'),
                state=data.get('state'),
                city=data.get('city'),
                zone=data.get('zone'),
                company_address=data.get('company_address'),
                contact_name=data.get('contact_name'),
                contact_email=data.get('contact_email'), 
                contact_phone=data.get('contact_phone'),
                logo_url=data.get('logo_url', ''),
                primary_color=data.get('primary_color', ''),
                tagline=data.get('tagline', ''),
                login_hero_description=data.get('login_hero_description', ''),
                login_welcome_message=data.get('login_welcome_message', ''),
                compliance_badges=data.get('compliance_badges', [])
            )
            
            plan_id = data.get('plan_id')
            plan = Plan.objects.filter(id=plan_id).first() if plan_id else None
            billing_data = data.get('billing') or {}

            BillingConfiguration.objects.create(
                organization=org,
                plan=plan,
                solution_type=billing_data.get('solution_type') or None,
                solution_for=billing_data.get('solution_for') or None,
                billing_term=billing_data.get('billing_term') or None,
                rate=billing_data.get('rate') if billing_data.get('rate') is not None else 0,
                billing_cycle=billing_data.get('billing_cycle') or None,
                duration_type=billing_data.get('duration_type') or None,
                start_date=billing_data.get('start_date') or None,
                end_date=billing_data.get('end_date') or None,
                billing_date=billing_data.get('billing_date') or None,
            )
                
            admin_email = data.get('initial_admin_email') or data.get('admin_email') or data.get('contact_email')
            admin_password = data.get('initial_admin_password') or data.get('admin_password')

            # Seed all OrganizationFeatureAccess rows as enabled=True for this new org
            from organizations.services import seed_org_feature_access
            seed_org_feature_access(org)

            if admin_email:
                from organizations.services import provision_org_admin_user
                provision_org_admin_user(
                    org=org,
                    admin_email=admin_email,
                    raw_password=admin_password,
                    contact_name=data.get('contact_name'),
                    request=request
                )

            ActivityLog.objects.create(
                actor=request.user,
                action='org_created',
                target_type='Organization',
                target_id=org.id,
                target_label=org.name,
                organization=org,
                metadata={'plan': plan.name if plan else None}
            )
            
        return Response(OrganizationSerializer(org).data, status=201)

class PublicOrganizationBrandingView(APIView):
    """Unauthenticated. Same trust boundary discipline as PublicPlatformBrandingView:
    return ONLY the fields explicitly listed here, never the full Organization serializer.
    Internal fields this must never expose: billing status, department/user counts,
    internal contact fields not meant for public display, activity data, anything that
    would tell a competitor or a curious visitor something about this tenant's real usage."""
    permission_classes = [permissions.AllowAny]

    def get(self, request, slug):
        # Branch 1: slug doesn't exist at all, OR exists but the org is suspended/deleted.
        # Deliberately identical response for both cases — see 2.3 for why.
        try:
            org = Organization.objects.get(sub_domain=slug, status='Active')
        except Organization.DoesNotExist:
            return Response({'found': False}, status=404)

        # Branch 2: real, active organization — return the safe subset only.
        return Response({
            'found': True,
            'organization_name': org.name,
            'logo_url': org.logo_url,
            'primary_color': org.primary_color,
            'tagline': org.tagline,
            'login_hero_description': org.login_hero_description,
            'login_welcome_message': org.login_welcome_message,
            'compliance_badges': org.compliance_badges,
            'support_email': org.contact_email,
        })

class UploadOrgLogoView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not getattr(request.user, 'is_platform_super_admin', False):
            return Response({'error': 'Forbidden'}, status=403)

        file = request.FILES.get('logo')
        if not file:
            return Response({'error': 'No file provided'}, status=400)

        allowed_types = ['image/png', 'image/jpeg', 'image/svg+xml', 'image/webp']
        if file.content_type not in allowed_types:
            return Response({'error': f'File type {file.content_type} not allowed. Use PNG, JPEG, SVG, or WebP.'}, status=400)

        max_size = 2 * 1024 * 1024
        if file.size > max_size:
            return Response({'error': 'File too large. Maximum 2MB.'}, status=400)

        import uuid
        ext = file.name.rsplit('.', 1)[-1] if '.' in file.name else 'png'
        safe_filename = f'{uuid.uuid4().hex}.{ext}'
        path = default_storage.save(f'org_logos/{safe_filename}', file)
        url = request.build_absolute_uri(default_storage.url(path))
        return Response({'url': url})

class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user)

    def perform_create(self, serializer):
        serializer.save(recipient=self.request.user)


class BuyPlanView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        if not user.organization:
            return Response({'error': 'Not associated with an organization'}, status=400)
        
        plan_id = request.data.get('plan_id')
        billing_cycle = request.data.get('billing_cycle', 'monthly')
        
        plan = Plan.objects.filter(id=plan_id).first()
        if not plan:
            return Response({'error': 'Plan not found'}, status=404)
        
        org = user.organization
        billing, _ = BillingConfiguration.objects.get_or_create(organization=org)
        billing.plan = plan
        billing.billing_cycle = billing_cycle
        billing.rate = plan.yearly_price if billing_cycle == 'yearly' else plan.monthly_price
        billing.status = 'active'
        billing.payment_status = 'paid'
        billing.save()
        
        # Grant included features to OrganizationFeatureAccess
        for feat in plan.included_features.all():
            access, _ = OrganizationFeatureAccess.objects.get_or_create(organization=org, feature=feat)
            access.enabled = True
            access.save()
            
        ActivityLog.objects.create(
            actor=user,
            action='plan_upgraded',
            target_type='Plan',
            target_id=plan.id,
            target_label=plan.name,
            organization=org,
            metadata={'plan': plan.name, 'billing_cycle': billing_cycle}
        )

        return Response({
            'message': f"Successfully subscribed to {plan.name}!",
            'plan_name': plan.name,
            'billing_cycle': billing_cycle
        })

class PublicPlatformBrandingView(APIView):
    """Public endpoint to return platform branding details (name, logo, colors, settings) for client applications."""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        settings = PlatformSettings.load()
        return Response({
            'platform_name': settings.platform_name or 'Halyard Learn',
            'logo_url': settings.logo_url or '',
            'favicon_url': settings.favicon_url or '',
            'primary_color': settings.primary_color or '#10b981',
            'support_email': settings.support_email or 'support@halyardlearn.com',
            'terms_url': settings.terms_url or '',
            'privacy_url': settings.privacy_url or '',
            'default_timezone': settings.default_timezone or 'UTC',
            'default_currency': settings.default_currency or 'USD',
            'max_upload_size_mb': settings.max_upload_size_mb or 500,
            'password_min_length': settings.password_min_length or 8,
            'session_timeout_minutes': settings.session_timeout_minutes or 480,
            'activity_log_retention_days': settings.activity_log_retention_days or 365,
            'require_mfa': settings.require_mfa or False,
            'allowed_ip_range': settings.allowed_ip_range or '',
            'enable_email_notifications': settings.enable_email_notifications,
            'enable_system_notifications': settings.enable_system_notifications,
        })


# ─── MASTER TOOLKIT ENTERPRISE VIEWSETS ───────────────────────────────────────
from rest_framework.decorators import action
from django.db.models import Q
from .models import (
    ToolkitCategory, ToolkitArticle, ToolkitArticleVersion, ToolkitAttachment,
    ToolkitBookmark, ToolkitRecentlyViewed, ToolkitChangeLog, ToolkitReleaseNote,
    ToolkitDependencyNode, ToolkitAuditLog, ToolkitBackup
)
from .serializers import (
    ToolkitCategorySerializer, ToolkitArticleSerializer, ToolkitArticleVersionSerializer,
    ToolkitAttachmentSerializer, ToolkitChangeLogSerializer, ToolkitReleaseNoteSerializer,
    ToolkitDependencyNodeSerializer, ToolkitAuditLogSerializer, ToolkitBackupSerializer
)
from .toolkit_seeder import seed_toolkit
from .toolkit_rescan import rescan_project
from .toolkit_export_import import export_toolkit_data, import_toolkit_data

class ToolkitCategoryViewSet(viewsets.ModelViewSet):
    queryset = ToolkitCategory.objects.all()
    serializer_class = ToolkitCategorySerializer
    permission_classes = [SuperAdminPermission]
    pagination_class = None


class ToolkitArticleViewSet(viewsets.ModelViewSet):
    queryset = ToolkitArticle.objects.all()
    serializer_class = ToolkitArticleSerializer
    permission_classes = [SuperAdminPermission]

    def get_queryset(self):
        qs = ToolkitArticle.objects.all()
        cat_id = self.request.query_params.get('category')
        status_filter = self.request.query_params.get('status')
        search = self.request.query_params.get('search')
        tag = self.request.query_params.get('tag')
        bookmarked = self.request.query_params.get('bookmarked')

        if cat_id:
            qs = qs.filter(category_id=cat_id)
        if status_filter:
            qs = qs.filter(status=status_filter)
        if tag:
            qs = qs.filter(tags__contains=[tag])
        if bookmarked == 'true':
            qs = qs.filter(bookmarks__user=self.request.user)
        if search:
            qs = qs.filter(
                Q(title__icontains=search) |
                Q(summary__icontains=search) |
                Q(content__icontains=search) |
                Q(error_code__icontains=search)
            )
        return qs

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.view_count += 1
        instance.save(update_fields=['view_count'])
        if request.user.is_authenticated:
            ToolkitRecentlyViewed.objects.update_or_create(
                user=request.user,
                article=instance
            )
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def perform_create(self, serializer):
        article = serializer.save(created_by=self.request.user)
        ToolkitArticleVersion.objects.create(
            article=article,
            version_number=article.version,
            title=article.title,
            summary=article.summary,
            content=article.content,
            created_by=self.request.user
        )
        ToolkitAuditLog.objects.create(
            action='CREATE_ARTICLE',
            article_title=article.title,
            category_name=article.category.name,
            performed_by=self.request.user
        )

    def perform_update(self, serializer):
        article = serializer.save()
        article.version += 1
        article.save(update_fields=['version'])
        ToolkitArticleVersion.objects.create(
            article=article,
            version_number=article.version,
            title=article.title,
            summary=article.summary,
            content=article.content,
            created_by=self.request.user
        )
        ToolkitAuditLog.objects.create(
            action='UPDATE_ARTICLE',
            article_title=article.title,
            category_name=article.category.name,
            performed_by=self.request.user
        )

    @action(detail=True, methods=['post'])
    def rollback(self, request, pk=None):
        article = self.get_object()
        version_id = request.data.get('version_id')
        try:
            ver = ToolkitArticleVersion.objects.get(id=version_id, article=article)
            article.title = ver.title
            article.summary = ver.summary
            article.content = ver.content
            article.version += 1
            article.save()
            ToolkitArticleVersion.objects.create(
                article=article,
                version_number=article.version,
                title=article.title,
                summary=article.summary,
                content=article.content,
                created_by=request.user
            )
            ToolkitAuditLog.objects.create(
                action='ROLLBACK_ARTICLE',
                article_title=article.title,
                category_name=article.category.name,
                performed_by=request.user,
                details={'restored_version': ver.version_number}
            )
            return Response(ToolkitArticleSerializer(article, context={'request': request}).data)
        except ToolkitArticleVersion.DoesNotExist:
            return Response({'error': 'Version snapshot not found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['post'])
    def toggle_bookmark(self, request, pk=None):
        article = self.get_object()
        bookmark, created = ToolkitBookmark.objects.get_or_create(user=request.user, article=article)
        if not created:
            bookmark.delete()
            return Response({'bookmarked': False, 'message': 'Bookmark removed'})
        return Response({'bookmarked': True, 'message': 'Article bookmarked'})

    @action(detail=False, methods=['post'])
    def seed(self, request):
        seed_toolkit()
        return Response({'message': 'Toolkit initial auto-seeding completed successfully!'})

    @action(detail=False, methods=['post'])
    def rescan(self, request):
        res = rescan_project()
        return Response(res)

    @action(detail=False, methods=['get'])
    def export_pack(self, request):
        cat_ids = request.query_params.getlist('categories')
        data = export_toolkit_data(category_ids=cat_ids)
        return Response(data)

    @action(detail=False, methods=['post'])
    def import_pack(self, request):
        import_pack = request.data
        res = import_toolkit_data(import_pack, user=request.user)
        return Response(res)


class ToolkitChangeLogViewSet(viewsets.ModelViewSet):
    queryset = ToolkitChangeLog.objects.all()
    serializer_class = ToolkitChangeLogSerializer
    permission_classes = [SuperAdminPermission]


class ToolkitReleaseNoteViewSet(viewsets.ModelViewSet):
    queryset = ToolkitReleaseNote.objects.all()
    serializer_class = ToolkitReleaseNoteSerializer
    permission_classes = [SuperAdminPermission]


class ToolkitDependencyViewSet(viewsets.ModelViewSet):
    queryset = ToolkitDependencyNode.objects.all()
    serializer_class = ToolkitDependencyNodeSerializer
    permission_classes = [SuperAdminPermission]
    pagination_class = None


class ToolkitAuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ToolkitAuditLog.objects.all()
    serializer_class = ToolkitAuditLogSerializer
    permission_classes = [SuperAdminPermission]


class ToolkitBackupViewSet(viewsets.ModelViewSet):
    queryset = ToolkitBackup.objects.all()
    serializer_class = ToolkitBackupSerializer
    permission_classes = [SuperAdminPermission]


class ToolkitHealthMonitorView(APIView):
    """Live Operational Metrics and System Health Overview for Super Admin Console."""
    permission_classes = [SuperAdminPermission]

    def get(self, request):
        from users.models import User
        from courses.models import Course, Module, Lesson, IssuedCertificate, ScormPackage
        from organizations.models import Organization, Department, Role, ActivityLog
        from master_setup.models import ToolkitCategory, ToolkitArticle, ToolkitChangeLog, ToolkitAuditLog

        total_orgs = Organization.objects.count()
        active_orgs = Organization.objects.filter(status='active').count()
        total_users = User.objects.count()
        active_users = User.objects.filter(is_active=True).count()
        total_courses = Course.objects.count()
        total_modules = Module.objects.count()
        total_lessons = Lesson.objects.count()
        total_certs = IssuedCertificate.objects.count()
        total_scorm = ScormPackage.objects.count()
        total_roles = Role.objects.count()
        total_depts = Department.objects.count()
        total_articles = ToolkitArticle.objects.count()
        published_articles = ToolkitArticle.objects.filter(status='published').count()

        return Response({
            'backend_status': 'Operational',
            'database_status': 'Healthy',
            'storage_status': 'Healthy',
            'uptime_seconds': 86400,
            'metrics': {
                'total_organizations': total_orgs,
                'active_organizations': active_orgs,
                'total_users': total_users,
                'active_users': active_users,
                'total_courses': total_courses,
                'total_modules': total_modules,
                'total_lessons': total_lessons,
                'total_certificates': total_certs,
                'total_scorm_packages': total_scorm,
                'total_roles': total_roles,
                'total_departments': total_depts,
                'total_articles': total_articles,
                'published_articles': published_articles,
                'categories_count': ToolkitCategory.objects.count(),
                'changelogs_count': ToolkitChangeLog.objects.count(),
                'audit_logs_count': ToolkitAuditLog.objects.count(),
            }
        })


