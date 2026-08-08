from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    FeatureViewSet, SiteFeatureAccessViewSet, OrgFeatureAccessView, PlanViewSet,
    PlatformSettingsView, NotificationTemplateViewSet,
    LookupTypeViewSet, LookupValueViewSet, TerminologyOverrideViewSet,
    SetupStatusView, ProvisionOrganizationView,
    PublicOrganizationBrandingView, UploadOrgLogoView,
    NotificationViewSet, PublicPlatformBrandingView, BuyPlanView,
    ToolkitCategoryViewSet, ToolkitArticleViewSet, ToolkitChangeLogViewSet,
    ToolkitReleaseNoteViewSet, ToolkitDependencyViewSet, ToolkitAuditLogViewSet,
    ToolkitBackupViewSet, ToolkitHealthMonitorView
)

router = DefaultRouter()
router.register(r'features', FeatureViewSet)
router.register(r'site-feature-access', SiteFeatureAccessViewSet)
router.register(r'plans', PlanViewSet)
router.register(r'notification-templates', NotificationTemplateViewSet)
router.register(r'notifications', NotificationViewSet, basename='notifications')
router.register(r'lookup-types', LookupTypeViewSet)
router.register(r'lookup-values', LookupValueViewSet)
router.register(r'terminology-overrides', TerminologyOverrideViewSet)

# Toolkit Endpoints
router.register(r'toolkit/categories', ToolkitCategoryViewSet, basename='toolkit-categories')
router.register(r'toolkit/articles', ToolkitArticleViewSet, basename='toolkit-articles')
router.register(r'toolkit/changelogs', ToolkitChangeLogViewSet, basename='toolkit-changelogs')
router.register(r'toolkit/releasenotes', ToolkitReleaseNoteViewSet, basename='toolkit-releasenotes')
router.register(r'toolkit/dependencies', ToolkitDependencyViewSet, basename='toolkit-dependencies')
router.register(r'toolkit/audit-logs', ToolkitAuditLogViewSet, basename='toolkit-audit-logs')
router.register(r'toolkit/backups', ToolkitBackupViewSet, basename='toolkit-backups')

urlpatterns = [
    path('', include(router.urls)),
    path('toolkit/health-monitor/', ToolkitHealthMonitorView.as_view(), name='toolkit-health-monitor'),
    path('platform-settings/', PlatformSettingsView.as_view(), name='platform-settings'),
    path('setup-status/', SetupStatusView.as_view(), name='setup-status'),
    path('provision-organization/', ProvisionOrganizationView.as_view(), name='provision-organization'),
    path('org-features/', OrgFeatureAccessView.as_view(), name='org-features'),
    path('toggle-org-feature/', OrgFeatureAccessView.as_view(), name='toggle-org-feature'),
    path('buy-plan/', BuyPlanView.as_view(), name='buy-plan'),
    path('public/platform-branding/', PublicPlatformBrandingView.as_view(), name='public-platform-branding'),
    path('public/organization-branding/<slug:slug>/', PublicOrganizationBrandingView.as_view(), name='public-org-branding'),
    path('upload/org-logo/', UploadOrgLogoView.as_view(), name='upload-org-logo'),
]

