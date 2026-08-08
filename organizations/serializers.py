from rest_framework import serializers
from .models import Organization, Site, Department, Role, BillingConfiguration

class BillingConfigurationSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    company_name = serializers.CharField(source='organization.company_name', read_only=True)
    plan_name = serializers.CharField(source='plan.name', read_only=True, default=None)
    billing_amount = serializers.SerializerMethodField()

    class Meta:
        model = BillingConfiguration
        fields = '__all__'

    def get_billing_amount(self, obj):
        if not obj.plan:
            return None
        return float(obj.plan.yearly_price) if obj.billing_cycle == 'yearly' else float(obj.plan.monthly_price)

class SiteSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    url = serializers.CharField(required=False, allow_blank=True, allow_null=True, default='')
    contact_email = serializers.CharField(required=False, allow_blank=True, allow_null=True, default='')

    class Meta:
        model = Site
        fields = '__all__'
        extra_kwargs = {
            'url': {'validators': []}
        }

    def validate_url(self, value):
        if not value:
            return ""
        import re
        val = str(value).strip()
        cleaned = re.sub(r'^https?:?\/*', '', val)
        if cleaned:
            return f"https://{cleaned}"
        return ""

class OrganizationSerializer(serializers.ModelSerializer):
    billing = BillingConfigurationSerializer(read_only=True)
    sites = SiteSerializer(many=True, read_only=True)
    company_name = serializers.CharField(required=False, allow_blank=True, default='')
    entity_name = serializers.CharField(required=False, allow_blank=True, default='')
    sub_domain = serializers.CharField(required=False, allow_blank=True, default='')

    class Meta:
        model = Organization
        fields = '__all__'

    def validate(self, attrs):
        if not attrs.get('company_name'):
            attrs['company_name'] = attrs.get('name', 'Organization')
        if not attrs.get('entity_name'):
            attrs['entity_name'] = attrs.get('name', 'Organization')

        sub_domain = attrs.get('sub_domain')
        if sub_domain:
            sub_domain = str(sub_domain).lower().strip()
            qs = Organization.objects.filter(sub_domain=sub_domain)
            if self.instance:
                qs = qs.exclude(id=self.instance.id)
            if qs.exists():
                raise serializers.ValidationError({
                    'sub_domain': f"The subdomain '{sub_domain}' is already taken. Please enter a unique subdomain."
                })
            attrs['sub_domain'] = sub_domain
        else:
            import re, time
            name_val = attrs.get('name', '')
            base_slug = re.sub(r'[^a-z0-9]+', '-', name_val.lower()).strip('-')
            if not base_slug:
                base_slug = f"org-{int(time.time())}"
            slug = base_slug
            counter = 1
            qs = Organization.objects.filter(sub_domain=slug)
            if self.instance:
                qs = qs.exclude(id=self.instance.id)
            while qs.exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
                qs = Organization.objects.filter(sub_domain=slug)
                if self.instance:
                    qs = qs.exclude(id=self.instance.id)
            attrs['sub_domain'] = slug
        return attrs

    def create(self, validated_data):
        billing_data = self.initial_data.get('billing')
        initial_admin_email = self.initial_data.get('initial_admin_email') or self.initial_data.get('admin_email') or validated_data.get('contact_email')
        initial_admin_password = self.initial_data.get('initial_admin_password') or self.initial_data.get('admin_password')

        instance = super().create(validated_data)

        if billing_data and isinstance(billing_data, dict):
            billing, _ = BillingConfiguration.objects.get_or_create(organization=instance)
            plan_id = billing_data.get('plan') or billing_data.get('plan_id')
            if plan_id:
                from master_setup.models import Plan
                billing.plan = Plan.objects.filter(id=plan_id).first()
            for key in ['billing_cycle', 'rate', 'solution_type', 'solution_for', 'billing_term', 'duration_type', 'start_date', 'end_date', 'billing_date']:
                if key in billing_data:
                    setattr(billing, key, billing_data[key])
            billing.save()

        if initial_admin_email:
            from .services import provision_org_admin_user
            request = self.context.get('request')
            provision_org_admin_user(
                org=instance,
                admin_email=initial_admin_email,
                raw_password=initial_admin_password,
                contact_name=instance.contact_name,
                request=request
            )

        return instance

    def update(self, instance, validated_data):
        billing_data = self.initial_data.get('billing')
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if billing_data and isinstance(billing_data, dict):
            billing, _ = BillingConfiguration.objects.get_or_create(organization=instance)
            plan_id = billing_data.get('plan') or billing_data.get('plan_id')
            if plan_id:
                from master_setup.models import Plan
                billing.plan = Plan.objects.filter(id=plan_id).first()
            if 'billing_cycle' in billing_data:
                billing.billing_cycle = billing_data['billing_cycle']
            if 'rate' in billing_data:
                billing.rate = billing_data['rate']
            if 'solution_type' in billing_data:
                billing.solution_type = billing_data['solution_type']
            if 'solution_for' in billing_data:
                billing.solution_for = billing_data['solution_for']
            if 'billing_term' in billing_data:
                billing.billing_term = billing_data['billing_term']
            if 'duration_type' in billing_data:
                billing.duration_type = billing_data['duration_type']
            if 'start_date' in billing_data:
                billing.start_date = billing_data['start_date']
            if 'end_date' in billing_data:
                billing.end_date = billing_data['end_date']
            if 'billing_date' in billing_data:
                billing.billing_date = billing_data['billing_date']
            billing.save()

        return instance

class DepartmentSerializer(serializers.ModelSerializer):
    user_count = serializers.SerializerMethodField()

    class Meta:
        model = Department
        fields = ['id', 'organization', 'name', 'parent', 'user_count', 'created_at']
        read_only_fields = ['organization']

    def get_user_count(self, obj):
        return obj.users.count()


class RoleSerializer(serializers.ModelSerializer):
    user_count = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = [
            'id', 'organization', 'name', 'is_default', 'is_admin_role', 'user_count',
            'can_view_users', 'can_create_users', 'can_edit_users', 'can_delete_users',
            'can_view_roles', 'can_create_roles', 'can_edit_roles', 'can_delete_roles',
            'can_view_courses', 'can_create_courses', 'can_edit_courses', 'can_delete_courses',
            'can_view_certificates', 'can_create_certificates', 'can_edit_certificates', 'can_delete_certificates',
            'can_view_reports', 'can_create_reports', 'can_edit_reports', 'can_delete_reports',
            'can_view_module_access', 'can_create_module_access', 'can_edit_module_access', 'can_delete_module_access',
            'can_view_activity_log', 'can_create_activity_log', 'can_edit_activity_log', 'can_delete_activity_log',
            'can_manage_users', 'can_manage_departments', 'can_manage_roles',
            'can_publish_courses', 'can_manage_module_access', 'can_manage_certificates',
            'created_at',
        ]
        read_only_fields = ['organization', 'is_admin_role']

    def get_user_count(self, obj):
        return obj.users.count()

from .models import CertificateTemplate
class CertificateTemplateSerializer(serializers.ModelSerializer):
    assigned_courses = serializers.SerializerMethodField()

    class Meta:
        model = CertificateTemplate
        fields = ['id', 'organization', 'title', 'body_html', 'created_at', 'assigned_courses']
        read_only_fields = ['organization', 'assigned_courses']

    def get_assigned_courses(self, obj):
        return [
            {'id': c.id, 'title': c.title, 'status': c.status}
            for c in obj.courses.all()
        ]

from .models import ActivityLog
class ActivityLogActorSerializer(serializers.ModelSerializer):
    class Meta:
        from django.contrib.auth import get_user_model
        model = get_user_model()
        fields = ['id', 'username', 'email']

class ActivityLogOrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ['id', 'name']

class ActivityLogSerializer(serializers.ModelSerializer):
    actor = ActivityLogActorSerializer(read_only=True)
    organization = ActivityLogOrganizationSerializer(read_only=True)

    class Meta:
        model = ActivityLog
        fields = '__all__'
