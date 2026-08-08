from rest_framework import serializers
from django.contrib.auth import get_user_model

User = get_user_model()


class RoleSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    is_default = serializers.BooleanField()
    is_admin_role = serializers.BooleanField()

    can_view_users = serializers.BooleanField(required=False, default=False)
    can_create_users = serializers.BooleanField(required=False, default=False)
    can_edit_users = serializers.BooleanField(required=False, default=False)
    can_delete_users = serializers.BooleanField(required=False, default=False)

    can_view_roles = serializers.BooleanField(required=False, default=False)
    can_create_roles = serializers.BooleanField(required=False, default=False)
    can_edit_roles = serializers.BooleanField(required=False, default=False)
    can_delete_roles = serializers.BooleanField(required=False, default=False)

    can_view_courses = serializers.BooleanField(required=False, default=False)
    can_create_courses = serializers.BooleanField(required=False, default=False)
    can_edit_courses = serializers.BooleanField(required=False, default=False)
    can_delete_courses = serializers.BooleanField(required=False, default=False)

    can_view_certificates = serializers.BooleanField(required=False, default=False)
    can_create_certificates = serializers.BooleanField(required=False, default=False)
    can_edit_certificates = serializers.BooleanField(required=False, default=False)
    can_delete_certificates = serializers.BooleanField(required=False, default=False)

    can_view_reports = serializers.BooleanField(required=False, default=False)
    can_create_reports = serializers.BooleanField(required=False, default=False)
    can_edit_reports = serializers.BooleanField(required=False, default=False)
    can_delete_reports = serializers.BooleanField(required=False, default=False)

    can_view_module_access = serializers.BooleanField(required=False, default=False)
    can_create_module_access = serializers.BooleanField(required=False, default=False)
    can_edit_module_access = serializers.BooleanField(required=False, default=False)
    can_delete_module_access = serializers.BooleanField(required=False, default=False)

    can_view_activity_log = serializers.BooleanField(required=False, default=False)
    can_create_activity_log = serializers.BooleanField(required=False, default=False)
    can_edit_activity_log = serializers.BooleanField(required=False, default=False)
    can_delete_activity_log = serializers.BooleanField(required=False, default=False)

    can_manage_users = serializers.BooleanField(required=False, default=False)
    can_manage_departments = serializers.BooleanField(required=False, default=False)
    can_manage_roles = serializers.BooleanField(required=False, default=False)
    can_publish_courses = serializers.BooleanField(required=False, default=False)
    can_manage_module_access = serializers.BooleanField(required=False, default=False)
    can_manage_certificates = serializers.BooleanField(required=False, default=False)


class DepartmentSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class OrganizationBriefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    logo_url = serializers.URLField(required=False, allow_blank=True)
    primary_color = serializers.CharField(required=False, allow_blank=True)


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    avatar_initials = serializers.ReadOnlyField()
    full_name = serializers.ReadOnlyField()

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'password',
            'first_name',
            'last_name',
            'full_name',
            'is_platform_super_admin',
            'is_active',
            'organization',
            'department',
            'role',
            'bio',
            'profile_picture',
            'job_title',
            'region',
            'points',
            'streak_days',
            'level',
            'badges',
            'theme_preference',
            'avatar_initials',
        ]
        read_only_fields = ['id', 'avatar_initials', 'full_name']

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user = super().create(validated_data)
        if password:
            user.set_password(password)
            user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        user = super().update(instance, validated_data)
        if password:
            user.set_password(password)
            user.save()
        return user

    def to_representation(self, instance):
        repr = super().to_representation(instance)
        
        # Populate nested objects for read
        if instance.organization:
            org_data = OrganizationBriefSerializer(instance.organization).data
            from master_setup.models import OrganizationFeatureAccess
            enabled_features = list(OrganizationFeatureAccess.objects.filter(
                organization=instance.organization, enabled=True
            ).values_list('feature__key', flat=True))
            org_data['enabled_features'] = enabled_features
            repr['organization'] = org_data
        if instance.department:
            repr['department'] = DepartmentSerializer(instance.department).data
        if instance.role:
            repr['role'] = RoleSerializer(instance.role).data
            
        return repr


from .models import ChatMessage

class ChatMessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source='sender.full_name', read_only=True)
    sender_email = serializers.CharField(source='sender.email', read_only=True)
    sender_initials = serializers.CharField(source='sender.avatar_initials', read_only=True)
    recipient_name = serializers.CharField(source='recipient.full_name', read_only=True)

    class Meta:
        model = ChatMessage
        fields = [
            'id', 'organization', 'sender', 'recipient', 'message',
            'is_read', 'created_at', 'sender_name', 'sender_email',
            'sender_initials', 'recipient_name'
        ]
        read_only_fields = ['id', 'organization', 'sender', 'created_at']

