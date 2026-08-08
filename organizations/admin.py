from django.contrib import admin
from .models import (
    Organization, BillingConfiguration, Site, 
    Department, Role, CertificateTemplate, ActivityLog
)

@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'sub_domain', 'company_name', 'status', 'contact_email', 'contact_phone', 'created_at')
    list_filter = ('status', 'country')
    search_fields = ('name', 'company_name', 'sub_domain', 'contact_email')
    ordering = ('-id',)


@admin.register(BillingConfiguration)
class BillingConfigurationAdmin(admin.ModelAdmin):
    list_display = ('id', 'organization', 'plan', 'status', 'payment_status', 'billing_cycle', 'rate', 'next_payment_due')
    list_filter = ('status', 'payment_status', 'billing_cycle')
    search_fields = ('organization__name', 'solution_type')


@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'organization', 'product_type', 'status', 'site_code', 'contact_email', 'created_at')
    list_filter = ('status', 'product_type', 'organization')
    search_fields = ('name', 'site_code', 'contact_email', 'organization__name')


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'organization', 'parent', 'created_at')
    list_filter = ('organization',)
    search_fields = ('name', 'organization__name')


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'organization', 'is_default', 'is_admin_role', 'can_manage_users', 'can_create_courses')
    list_filter = ('is_default', 'is_admin_role', 'organization')
    search_fields = ('name', 'organization__name')


@admin.register(CertificateTemplate)
class CertificateTemplateAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'organization', 'created_at')
    search_fields = ('title', 'organization__name')


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'created_at', 'action', 'actor', 'organization', 'target_type', 'target_label')
    list_filter = ('action', 'organization')
    search_fields = ('action', 'target_label', 'actor__username', 'organization__name')
    ordering = ('-created_at',)
