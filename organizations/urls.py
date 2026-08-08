from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    OrganizationViewSet, SiteViewSet, BillingConfigurationViewSet, 
    MyOrganizationView, MyOrganizationStatsView, DepartmentViewSet, 
    RoleViewSet, CertificateTemplateViewSet, PlatformStatsView, 
    ActivityLogViewSet, MyWorkspacesView, GlobalSearchView,
    SendOrgWelcomeEmailView, SendSiteWelcomeEmailView
)

router = DefaultRouter()
router.register(r'organizations', OrganizationViewSet, basename='organization')
router.register(r'sites', SiteViewSet, basename='site')
router.register(r'billing', BillingConfigurationViewSet, basename='billing')
router.register(r'departments', DepartmentViewSet, basename='department')
router.register(r'roles', RoleViewSet, basename='role')
router.register(r'certificate-templates', CertificateTemplateViewSet, basename='certificate-template')
router.register(r'activity-log', ActivityLogViewSet, basename='activity-log')

urlpatterns = [
    path('organizations/platform-stats/', PlatformStatsView.as_view(), name='platform-stats'),
    path('organizations/my/', MyOrganizationView.as_view(), name='my-organization'),
    path('organizations/my/stats/', MyOrganizationStatsView.as_view(), name='my-organization-stats'),
    path('organizations/<int:pk>/send-welcome-email/', SendOrgWelcomeEmailView.as_view(), name='org-send-welcome-email'),
    path('sites/<int:pk>/send-welcome-email/', SendSiteWelcomeEmailView.as_view(), name='site-send-welcome-email'),
    path('me/workspaces/', MyWorkspacesView.as_view(), name='my-workspaces'),
    path('search/', GlobalSearchView.as_view(), name='global-search'),
    path('', include(router.urls)),
]

