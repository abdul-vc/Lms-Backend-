from django.urls import path
from .integration_views import TenantProvisionView, UserProvisionView, LaunchGrantView

urlpatterns = [
    path('tenants/provision/', TenantProvisionView.as_view(), name='api-v1-tenant-provision'),
    path('users/provision/', UserProvisionView.as_view(), name='api-v1-user-provision'),
    path('launch-grant/', LaunchGrantView.as_view(), name='api-v1-launch-grant'),
]
