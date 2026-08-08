from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        'id', 'username', 'email', 'full_name_display', 'organization', 
        'role', 'department', 'is_platform_super_admin', 'is_staff', 'is_active'
    )
    list_filter = (
        'is_platform_super_admin', 'is_staff', 'is_superuser', 'is_active', 
        'organization', 'role', 'department'
    )
    search_fields = ('username', 'email', 'first_name', 'last_name', 'organization__name')
    ordering = ('-id',)

    fieldsets = BaseUserAdmin.fieldsets + (
        ('Multi-Tenant Platform Attributes', {
            'fields': (
                'is_platform_super_admin',
                'organization',
                'department',
                'role',
            )
        }),
        ('Profile Details & Gamification', {
            'fields': (
                'bio',
                'profile_picture',
                'job_title',
                'region',
                'points',
                'streak_days',
                'level',
                'badges',
            )
        }),
    )

    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Multi-Tenant Platform Attributes', {
            'fields': (
                'is_platform_super_admin',
                'organization',
                'department',
                'role',
            )
        }),
    )

    @admin.display(description='Full Name')
    def full_name_display(self, obj):
        return obj.full_name
