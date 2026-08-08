from rest_framework import serializers
from .models import (
    Feature, SiteFeatureAccess, OrganizationFeatureAccess, Plan,
    PlatformSettings, NotificationTemplate, Notification,
    LookupType, LookupValue, TerminologyOverride
)

class FeatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feature
        fields = '__all__'

class SiteFeatureAccessSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteFeatureAccess
        fields = '__all__'

class OrganizationFeatureAccessSerializer(serializers.ModelSerializer):
    feature_key = serializers.CharField(source='feature.key', read_only=True)
    feature_name = serializers.CharField(source='feature.name', read_only=True)

    class Meta:
        model = OrganizationFeatureAccess
        fields = '__all__'

class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = '__all__'

class PlatformSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlatformSettings
        fields = '__all__'

class NotificationTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationTemplate
        fields = '__all__'
        read_only_fields = ['key']

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'

class LookupTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LookupType
        fields = '__all__'

class LookupValueSerializer(serializers.ModelSerializer):
    class Meta:
        model = LookupValue
        fields = '__all__'

class TerminologyOverrideSerializer(serializers.ModelSerializer):
    class Meta:
        model = TerminologyOverride
        fields = '__all__'


# ─── TOOLKIT SERIALIZERS ───────────────────────────────────────────────────────
from .models import (
    ToolkitCategory, ToolkitArticle, ToolkitArticleVersion,
    ToolkitAttachment, ToolkitBookmark, ToolkitRecentlyViewed,
    ToolkitChangeLog, ToolkitReleaseNote, ToolkitDependencyNode,
    ToolkitAuditLog, ToolkitBackup
)

class ToolkitCategorySerializer(serializers.ModelSerializer):
    article_count = serializers.IntegerField(source='articles.count', read_only=True)

    class Meta:
        model = ToolkitCategory
        fields = '__all__'


class ToolkitAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ToolkitAttachment
        fields = '__all__'


class ToolkitArticleVersionSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.full_name', read_only=True, default='')

    class Meta:
        model = ToolkitArticleVersion
        fields = '__all__'


class ToolkitArticleSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    category_icon = serializers.CharField(source='category.icon', read_only=True)
    created_by_name = serializers.CharField(source='created_by.full_name', read_only=True, default='')
    versions = ToolkitArticleVersionSerializer(many=True, read_only=True)
    attachments = ToolkitAttachmentSerializer(many=True, read_only=True)
    is_bookmarked = serializers.SerializerMethodField()

    class Meta:
        model = ToolkitArticle
        fields = '__all__'

    def get_is_bookmarked(self, obj):
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            return ToolkitBookmark.objects.filter(user=request.user, article=obj).exists()
        return False


class ToolkitChangeLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ToolkitChangeLog
        fields = '__all__'


class ToolkitReleaseNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ToolkitReleaseNote
        fields = '__all__'


class ToolkitDependencyNodeSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()

    class Meta:
        model = ToolkitDependencyNode
        fields = '__all__'

    def get_children(self, obj):
        return ToolkitDependencyNodeSerializer(obj.children.all(), many=True).data


class ToolkitAuditLogSerializer(serializers.ModelSerializer):
    performed_by_name = serializers.CharField(source='performed_by.full_name', read_only=True, default='')

    class Meta:
        model = ToolkitAuditLog
        fields = '__all__'


class ToolkitBackupSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.full_name', read_only=True, default='')

    class Meta:
        model = ToolkitBackup
        fields = '__all__'

