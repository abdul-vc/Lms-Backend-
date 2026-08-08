from django.db import models

class Feature(models.Model):
    key = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=50, default='core')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Workspace(models.Model):
    key = models.SlugField(max_length=50, unique=True)
    label = models.CharField(max_length=100)
    icon = models.CharField(max_length=50, blank=True)
    order = models.PositiveIntegerField(default=0)
    
    def __str__(self):
        return self.label

class NavItem(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='nav_items')
    key = models.SlugField(max_length=50)
    label = models.CharField(max_length=100)
    icon = models.CharField(max_length=50, blank=True)
    route = models.CharField(max_length=255)
    feature = models.ForeignKey('master_setup.Feature', on_delete=models.SET_NULL, null=True, blank=True)
    required_permission = models.CharField(max_length=100, blank=True)
    order = models.PositiveIntegerField(default=0)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name='children')

    class Meta:
        ordering = ['order']

class DashboardWidget(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='widgets')
    key = models.SlugField(max_length=50)
    label = models.CharField(max_length=100)
    component_key = models.CharField(max_length=100)
    feature = models.ForeignKey('master_setup.Feature', on_delete=models.SET_NULL, null=True, blank=True)
    order = models.PositiveIntegerField(default=0)

class SiteFeatureAccess(models.Model):
    site = models.ForeignKey('organizations.Site', on_delete=models.CASCADE, related_name='feature_access')
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE, related_name='site_access')
    enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('site', 'feature')

class OrganizationFeatureAccess(models.Model):
    organization = models.ForeignKey('organizations.Organization', on_delete=models.CASCADE, related_name='feature_access')
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE, related_name='org_access')
    enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('organization', 'feature')

    def __str__(self):
        return f"{self.organization.name} - {self.feature.key}: {'Enabled' if self.enabled else 'Disabled'}"

class Plan(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    monthly_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    yearly_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_users = models.IntegerField(null=True, blank=True)
    max_courses = models.IntegerField(null=True, blank=True)
    max_sites = models.IntegerField(null=True, blank=True)
    included_features = models.ManyToManyField(Feature, blank=True, related_name='included_in_plans')
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class PlatformSettings(models.Model):
    # General Tab
    platform_name = models.CharField(max_length=150, default='Halyard Learn')
    logo_url = models.URLField(blank=True, default='')
    favicon_url = models.URLField(blank=True, default='')
    primary_color = models.CharField(max_length=7, default='#10b981')
    support_email = models.EmailField(blank=True, default='support@halyardlearn.com')
    terms_url = models.URLField(blank=True, default='')
    privacy_url = models.URLField(blank=True, default='')
    default_timezone = models.CharField(max_length=50, default='UTC')
    default_currency = models.CharField(max_length=3, default='USD')
    
    # Security Tab
    password_min_length = models.IntegerField(default=8)
    session_timeout_minutes = models.IntegerField(default=480)
    max_upload_size_mb = models.IntegerField(default=500)
    activity_log_retention_days = models.IntegerField(default=365)
    require_mfa = models.BooleanField(default=False)
    allowed_ip_range = models.CharField(max_length=255, blank=True, default='')
    
    # Notifications Tab
    smtp_host = models.CharField(max_length=150, blank=True, default='')
    smtp_port = models.IntegerField(default=587)
    smtp_username = models.CharField(max_length=150, blank=True, default='')
    smtp_password = models.CharField(max_length=150, blank=True, default='')
    smtp_use_tls = models.BooleanField(default=True)
    from_email = models.EmailField(blank=True, default='noreply@halyardlearn.com')
    enable_email_notifications = models.BooleanField(default=True)
    enable_system_notifications = models.BooleanField(default=True)
    
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        from django.db import connection
        table_name = cls._meta.db_table
        try:
            with connection.cursor() as cursor:
                columns = [col.name for col in connection.introspection.get_table_description(cursor, table_name)]
                fields_to_add = [
                    ('platform_name', "VARCHAR(150) DEFAULT 'Halyard Learn'"),
                    ('logo_url', "TEXT DEFAULT ''"),
                    ('favicon_url', "TEXT DEFAULT ''"),
                    ('primary_color', "VARCHAR(7) DEFAULT '#10b981'"),
                    ('support_email', "VARCHAR(254) DEFAULT 'support@halyardlearn.com'"),
                    ('terms_url', "TEXT DEFAULT ''"),
                    ('privacy_url', "TEXT DEFAULT ''"),
                    ('default_timezone', "VARCHAR(50) DEFAULT 'UTC'"),
                    ('default_currency', "VARCHAR(3) DEFAULT 'USD'"),
                    ('password_min_length', "INTEGER DEFAULT 8"),
                    ('session_timeout_minutes', "INTEGER DEFAULT 480"),
                    ('max_upload_size_mb', "INTEGER DEFAULT 500"),
                    ('activity_log_retention_days', "INTEGER DEFAULT 365"),
                    ('require_mfa', "BOOLEAN DEFAULT 0"),
                    ('allowed_ip_range', "VARCHAR(255) DEFAULT ''"),
                    ('smtp_host', "VARCHAR(150) DEFAULT ''"),
                    ('smtp_port', "INTEGER DEFAULT 587"),
                    ('smtp_username', "VARCHAR(150) DEFAULT ''"),
                    ('smtp_password', "VARCHAR(150) DEFAULT ''"),
                    ('smtp_use_tls', "BOOLEAN DEFAULT 1"),
                    ('from_email', "VARCHAR(254) DEFAULT 'noreply@halyardlearn.com'"),
                    ('enable_email_notifications', "BOOLEAN DEFAULT 1"),
                    ('enable_system_notifications', "BOOLEAN DEFAULT 1"),
                ]
                for col_name, col_def in fields_to_add:
                    if col_name not in columns:
                        try:
                            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def}")
                        except Exception:
                            pass
        except Exception as err:
            print("Introspection error in PlatformSettings:", err)

        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

class Notification(models.Model):
    recipient = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=255)
    message = models.TextField()
    type = models.CharField(max_length=50, default='system')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} to {self.recipient.email}"

class NotificationTemplate(models.Model):
    TEMPLATE_KEYS = [
        ('welcome_admin', 'Welcome — New Org Admin'),
        ('access_request_submitted', 'Access Request Submitted'),
        ('access_request_accepted', 'Access Request Accepted'),
        ('certificate_issued', 'Certificate Issued'),
        ('billing_reminder', 'Billing Reminder'),
        ('password_reset', 'Password Reset'),
    ]
    key = models.CharField(max_length=50, choices=TEMPLATE_KEYS, unique=True)
    subject = models.CharField(max_length=255)
    body_html = models.TextField(help_text='Use {{ variable }} placeholders, e.g. {{ user_name }}')
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.get_key_display()

class LookupType(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class LookupValue(models.Model):
    lookup_type = models.ForeignKey(LookupType, on_delete=models.CASCADE, related_name='values')
    code = models.CharField(max_length=50)
    label = models.CharField(max_length=100)
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('lookup_type', 'code')
        ordering = ['sort_order', 'label']

    def __str__(self):
        return f"{self.lookup_type.name} - {self.label}"

class TerminologyOverride(models.Model):
    organization = models.ForeignKey('organizations.Organization', on_delete=models.CASCADE, related_name='terminologies')
    standard_term = models.CharField(max_length=100)
    custom_term = models.CharField(max_length=100)
    custom_term_plural = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('organization', 'standard_term')

    def __str__(self):
        return f"{self.organization.name}: {self.standard_term} -> {self.custom_term}"


# ─── MASTER TOOLKIT ENTERPRISE MODELS ────────────────────────────────────────

class ToolkitCategory(models.Model):
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=150, unique=True)
    icon = models.CharField(max_length=50, default='BookOpen')
    description = models.TextField(blank=True)
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'toolkit_category'
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


STATUS_CHOICES = [
    ('draft', 'Draft'),
    ('in_review', 'In Review'),
    ('approved', 'Approved'),
    ('published', 'Published'),
    ('archived', 'Archived'),
]

class ToolkitArticle(models.Model):
    category = models.ForeignKey(ToolkitCategory, on_delete=models.CASCADE, related_name='articles')
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    summary = models.TextField(blank=True)
    content = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    version = models.IntegerField(default=1)
    error_code = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    tags = models.JSONField(default=list, blank=True)
    related_article_ids = models.JSONField(default=list, blank=True)
    view_count = models.IntegerField(default=0)
    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='created_toolkit_articles')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Future-ready AI fields
    ai_summary = models.TextField(blank=True, null=True)
    ai_metadata = models.JSONField(default=dict, blank=True)
    ai_embeddings_index = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = 'toolkit_article'
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.title} ({self.status})"


class ToolkitArticleVersion(models.Model):
    article = models.ForeignKey(ToolkitArticle, on_delete=models.CASCADE, related_name='versions')
    version_number = models.IntegerField()
    title = models.CharField(max_length=255)
    summary = models.TextField(blank=True)
    content = models.TextField()
    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'toolkit_article_version'
        ordering = ['-version_number']

    def __str__(self):
        return f"{self.article.title} - v{self.version_number}"


class ToolkitAttachment(models.Model):
    article = models.ForeignKey(ToolkitArticle, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='toolkit_attachments/')
    file_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=100)
    file_size = models.IntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'toolkit_attachment'

    def __str__(self):
        return self.file_name


class ToolkitBookmark(models.Model):
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='toolkit_bookmarks')
    article = models.ForeignKey(ToolkitArticle, on_delete=models.CASCADE, related_name='bookmarks')
    bookmarked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'toolkit_bookmark'
        unique_together = ('user', 'article')


class ToolkitRecentlyViewed(models.Model):
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='toolkit_recently_viewed')
    article = models.ForeignKey(ToolkitArticle, on_delete=models.CASCADE, related_name='recent_views')
    viewed_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'toolkit_recently_viewed'
        ordering = ['-viewed_at']
        unique_together = ('user', 'article')


class ToolkitChangeLog(models.Model):
    CHANGE_STATUS = [
        ('completed', 'Completed'),
        ('in_progress', 'In Progress'),
        ('deprecated', 'Deprecated'),
    ]
    version = models.CharField(max_length=50)
    date_time = models.DateTimeField(auto_now_add=True)
    module_name = models.CharField(max_length=150)
    feature_name = models.CharField(max_length=150)
    description = models.TextField()
    files_modified = models.JSONField(default=list, blank=True)
    developer_name = models.CharField(max_length=150, default='System Core')
    status = models.CharField(max_length=20, choices=CHANGE_STATUS, default='completed')
    notes = models.TextField(blank=True)
    is_published = models.BooleanField(default=True)

    class Meta:
        db_table = 'toolkit_changelog'
        ordering = ['-date_time']

    def __str__(self):
        return f"v{self.version} - {self.feature_name}"


class ToolkitReleaseNote(models.Model):
    version_number = models.CharField(max_length=50)
    release_date = models.DateField()
    new_features = models.JSONField(default=list, blank=True)
    improvements = models.JSONField(default=list, blank=True)
    bug_fixes = models.JSONField(default=list, blank=True)
    breaking_changes = models.JSONField(default=list, blank=True)
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'toolkit_releasenote'
        ordering = ['-release_date']

    def __str__(self):
        return f"Release {self.version_number}"


class ToolkitDependencyNode(models.Model):
    name = models.CharField(max_length=150)
    category = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    parent_node = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='children')
    affected_models = models.JSONField(default=list, blank=True)
    affected_apis = models.JSONField(default=list, blank=True)
    affected_components = models.JSONField(default=list, blank=True)
    risk_level = models.CharField(max_length=20, default='Low')

    class Meta:
        db_table = 'toolkit_dependencynode'

    def __str__(self):
        return self.name


class ToolkitAuditLog(models.Model):
    action = models.CharField(max_length=100)
    article_title = models.CharField(max_length=255, blank=True)
    category_name = models.CharField(max_length=150, blank=True)
    performed_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True)
    details = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'toolkit_auditlog'
        ordering = ['-timestamp']


class ToolkitBackup(models.Model):
    name = models.CharField(max_length=255)
    file = models.FileField(upload_to='toolkit_backups/')
    file_size = models.IntegerField(default=0)
    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'toolkit_backup'
        ordering = ['-created_at']

