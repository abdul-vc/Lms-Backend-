from django.contrib import admin
from .models import (
    Feature, Workspace, NavItem, DashboardWidget, SiteFeatureAccess,
    Plan, PlatformSettings, Notification, NotificationTemplate,
    LookupType, LookupValue, TerminologyOverride
)

@admin.register(Feature)
class FeatureAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'key', 'category', 'is_active', 'created_at')
    list_filter = ('category', 'is_active')
    search_fields = ('name', 'key')


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'monthly_price', 'yearly_price', 'max_users', 'max_courses', 'max_sites', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)


@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    list_display = ('id', 'label', 'key', 'order')


@admin.register(NavItem)
class NavItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'label', 'workspace', 'route', 'order')
    list_filter = ('workspace',)


@admin.register(DashboardWidget)
class DashboardWidgetAdmin(admin.ModelAdmin):
    list_display = ('id', 'label', 'workspace', 'component_key', 'order')


@admin.register(SiteFeatureAccess)
class SiteFeatureAccessAdmin(admin.ModelAdmin):
    list_display = ('id', 'site', 'feature', 'enabled', 'updated_at')
    list_filter = ('enabled', 'feature', 'site')


@admin.register(PlatformSettings)
class PlatformSettingsAdmin(admin.ModelAdmin):
    list_display = ('id', 'platform_name', 'support_email', 'default_currency', 'updated_at')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'recipient', 'type', 'is_read', 'created_at')
    list_filter = ('type', 'is_read')
    search_fields = ('title', 'message', 'recipient__email')


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = ('id', 'key', 'subject', 'is_active', 'updated_at')
    list_filter = ('is_active',)


@admin.register(LookupType)
class LookupTypeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'description')


@admin.register(LookupValue)
class LookupValueAdmin(admin.ModelAdmin):
    list_display = ('id', 'lookup_type', 'code', 'label', 'sort_order', 'is_active')
    list_filter = ('lookup_type', 'is_active')


@admin.register(TerminologyOverride)
class TerminologyOverrideAdmin(admin.ModelAdmin):
    list_display = ('id', 'organization', 'standard_term', 'custom_term')
    list_filter = ('organization',)
