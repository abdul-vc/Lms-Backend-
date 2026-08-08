from django.db import models

class Organization(models.Model):
    name = models.CharField(max_length=255)
    company_name = models.CharField(max_length=255)
    entity_name = models.CharField(max_length=255)
    sub_domain = models.SlugField(max_length=255, unique=True)
    status = models.CharField(max_length=50, default='Active')
    
    # Location Details
    country = models.CharField(max_length=100, blank=True, null=True)
    region = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    zone = models.CharField(max_length=100, blank=True, null=True)
    company_address = models.TextField(blank=True, null=True)
    
    # Contact Person
    contact_name = models.CharField(max_length=255, blank=True, null=True)
    contact_phone = models.CharField(max_length=50, blank=True, null=True)
    contact_email = models.EmailField(blank=True, null=True)
    subdomain_routing_enabled = models.BooleanField(default=True)

    # Branding
    logo_url = models.URLField(
        blank=True, default='',
        help_text="This organization's logo, shown on their branded login page and elsewhere their identity appears."
    )
    primary_color = models.CharField(
        max_length=7, blank=True, default='',
        help_text='Hex color, e.g. #1E40AF. Used for the login hero panel background and accent elements.'
    )
    tagline = models.CharField(
        max_length=255, blank=True, default='',
        help_text='Short headline on this organization\'s login page, e.g. "Excellence in patient care."'
    )
    login_hero_description = models.TextField(
        blank=True, default='',
        help_text='Optional longer paragraph under the tagline. Left blank = not shown, not a placeholder.'
    )
    login_welcome_message = models.CharField(
        max_length=255, blank=True, default='',
        help_text='Heading above the login form for this org\'s employees, e.g. "Welcome to Halyard Learn". Blank = falls back to platform default at render time, not stored as a duplicate default here.'
    )
    compliance_badges = models.JSONField(
        default=list, blank=True,
        help_text='This organization\'s own trust badges, independent of the platform\'s. Only true, verified claims.'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class BillingConfiguration(models.Model):
    organization = models.OneToOneField(Organization, on_delete=models.CASCADE, related_name='billing')
    plan = models.ForeignKey('master_setup.Plan', on_delete=models.SET_NULL, null=True, blank=True, related_name='subscriptions')
    status = models.CharField(
        max_length=20,
        choices=[('active', 'Active'), ('paused', 'Paused'), ('cancelled', 'Cancelled')],
        default='active',
    )
    solution_type = models.CharField(max_length=100, blank=True, null=True)
    solution_for = models.CharField(max_length=100, blank=True, null=True)
    billing_term = models.CharField(max_length=100, blank=True, null=True)
    rate = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    billing_cycle = models.CharField(
        max_length=20,
        choices=[('monthly', 'Monthly'), ('quarterly', 'Quarterly'), ('yearly', 'Yearly')],
        blank=True, null=True,
    )
    duration_type = models.CharField(
        max_length=20,
        choices=[('6_months', '6 Months'), ('1_year', '1 Year'), ('custom', 'Custom')],
        blank=True, null=True,
    )
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    billing_date = models.DateField(blank=True, null=True)
    next_payment_due = models.DateField(null=True, blank=True)
    payment_status = models.CharField(
        max_length=20,
        choices=[('paid', 'Paid'), ('pending', 'Pending'), ('overdue', 'Overdue')],
        default='paid'
    )

    def save(self, *args, **kwargs):
        import datetime
        import calendar

        if isinstance(self.start_date, str):
            try:
                self.start_date = datetime.date.fromisoformat(self.start_date)
            except (ValueError, TypeError):
                self.start_date = None

        if isinstance(self.end_date, str):
            try:
                self.end_date = datetime.date.fromisoformat(self.end_date)
            except (ValueError, TypeError):
                self.end_date = None

        if isinstance(self.billing_date, str):
            try:
                self.billing_date = datetime.date.fromisoformat(self.billing_date)
            except (ValueError, TypeError):
                self.billing_date = None

        def add_months(sourcedate, months):
            month = sourcedate.month - 1 + months
            year = sourcedate.year + month // 12
            month = month % 12 + 1
            day = min(sourcedate.day, calendar.monthrange(year, month)[1])
            return datetime.date(year, month, day)

        if self.start_date and self.billing_cycle:
            today = datetime.date.today()
            current_due = self.start_date
            
            # Always step forward until the due date is strictly in the future
            while current_due <= today:
                if self.billing_cycle == 'monthly':
                    current_due = add_months(current_due, 1)
                elif self.billing_cycle == 'quarterly':
                    current_due = add_months(current_due, 3)
                elif self.billing_cycle == 'yearly':
                    current_due = add_months(current_due, 12)
                else:
                    break
                
            if self.end_date and current_due > self.end_date:
                self.next_payment_due = None
            else:
                self.next_payment_due = current_due
        else:
            self.next_payment_due = None
            
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Billing for {self.organization.name}"


class Site(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='sites')
    name = models.CharField(max_length=255)
    url = models.URLField(blank=True, null=True, help_text="Public URL for this site instance")
    site_code = models.CharField(max_length=100, blank=True, null=True)
    product_type = models.CharField(max_length=100, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)
    location_address = models.TextField(blank=True, null=True)
    activate_date = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=50, default='Active')

    contact_name = models.CharField(max_length=255, blank=True, null=True)
    contact_phone = models.CharField(max_length=50, blank=True, null=True)
    contact_email = models.EmailField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.organization.name})"


class Department(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='departments')
    name = models.CharField(max_length=255)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='children')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('organization', 'name')

    def __str__(self):
        return f"{self.organization.name} / {self.name}"


class Role(models.Model):
    """Custom per-org role. Super-admin platform role is NOT stored here — it's a flag on User."""
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='roles')
    name = models.CharField(max_length=100)
    is_default = models.BooleanField(default=False)  # seeded roles (Admin/Instructor/Student) can't be deleted
    is_admin_role = models.BooleanField(default=False)  # True for Org Admin roles managed by Super Admins
    workspaces = models.ManyToManyField('master_setup.Workspace', related_name='roles')

    # Granular Module & Action Permissions (100% independent)
    can_view_users = models.BooleanField(default=False)
    can_create_users = models.BooleanField(default=False)
    can_edit_users = models.BooleanField(default=False)
    can_delete_users = models.BooleanField(default=False)

    can_view_roles = models.BooleanField(default=False)
    can_create_roles = models.BooleanField(default=False)
    can_edit_roles = models.BooleanField(default=False)
    can_delete_roles = models.BooleanField(default=False)

    can_view_courses = models.BooleanField(default=False)
    can_create_courses = models.BooleanField(default=False)
    can_edit_courses = models.BooleanField(default=False)
    can_delete_courses = models.BooleanField(default=False)

    can_view_certificates = models.BooleanField(default=False)
    can_create_certificates = models.BooleanField(default=False)
    can_edit_certificates = models.BooleanField(default=False)
    can_delete_certificates = models.BooleanField(default=False)

    can_view_reports = models.BooleanField(default=False)
    can_create_reports = models.BooleanField(default=False)
    can_edit_reports = models.BooleanField(default=False)
    can_delete_reports = models.BooleanField(default=False)

    can_view_module_access = models.BooleanField(default=False)
    can_create_module_access = models.BooleanField(default=False)
    can_edit_module_access = models.BooleanField(default=False)
    can_delete_module_access = models.BooleanField(default=False)

    can_view_activity_log = models.BooleanField(default=False)
    can_create_activity_log = models.BooleanField(default=False)
    can_edit_activity_log = models.BooleanField(default=False)
    can_delete_activity_log = models.BooleanField(default=False)

    # Legacy computed properties for backward compatibility
    @property
    def can_manage_users(self):
        return self.can_view_users or self.can_create_users or self.can_edit_users or self.can_delete_users

    @property
    def can_manage_departments(self):
        return self.can_view_users or self.can_create_users or self.can_edit_users or self.can_delete_users

    @property
    def can_manage_roles(self):
        return self.can_view_roles or self.can_create_roles or self.can_edit_roles or self.can_delete_roles

    @property
    def can_publish_courses(self):
        return self.can_create_courses or self.can_edit_courses

    @property
    def can_manage_module_access(self):
        return self.can_view_module_access or self.can_create_module_access or self.can_edit_module_access or self.can_delete_module_access

    @property
    def can_manage_certificates(self):
        return self.can_view_certificates or self.can_create_certificates or self.can_edit_certificates or self.can_delete_certificates

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('organization', 'name')

    def __str__(self):
        return f"{self.organization.name} / {self.name}"

class CertificateTemplate(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='certificate_templates')
    title = models.CharField(max_length=255, default='Completion Certificate')
    body_html = models.TextField(default='<h1>Certificate of Completion</h1><p>Awarded to {{ user.full_name }}</p>')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} ({self.organization.name})"

class ActivityLog(models.Model):
    # Who did it — nullable because some events (failed login, system jobs) may not have a resolved user
    actor = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='activity_logs')
    actor_role_snapshot = models.CharField(max_length=100, blank=True, null=True)  # role name at time of action, since roles can change later

    # Scope — always set when resolvable, this is what makes org-admin filtering trivial later
    organization = models.ForeignKey('organizations.Organization', on_delete=models.CASCADE, null=True, blank=True, related_name='activity_logs')

    # What happened — keep this a small closed vocabulary, not free text, so filtering/analytics stay usable
    ACTION_CHOICES = [
        ('login', 'Logged in'),
        ('logout', 'Logged out'),
        ('login_failed', 'Failed login attempt'),
        ('org_created', 'Organization created'),
        ('org_updated', 'Organization updated'),
        ('org_deleted', 'Organization deleted'),
        ('site_created', 'Site created'),
        ('site_updated', 'Site updated'),
        ('site_deleted', 'Site deleted'),
        ('user_created', 'User created'),
        ('user_updated', 'User updated'),
        ('user_deactivated', 'User deactivated'),
        ('role_created', 'Role created'),
        ('role_updated', 'Role updated'),
        ('role_deleted', 'Role deleted'),
        ('course_created', 'Course created'),
        ('course_published', 'Course published'),
        ('course_updated', 'Course updated'),
        ('lesson_video_uploaded', 'Lesson video uploaded'),
        ('assessment_imported', 'Assessment questions imported'),
        ('billing_updated', 'Billing configuration updated'),
        ('billing_status_changed', 'Billing status changed'),
        ('module_access_changed', 'Module access changed'),
        ('course_completed', 'Course completed'),          # learner-side event, feeds "who's using it" view
        ('assessment_attempted', 'Assessment attempt submitted'),
        ('certificate_issued', 'Certificate issued'),
    ]
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)

    # What it happened to — generic so one table covers every entity type instead of N separate log tables
    target_type = models.CharField(max_length=50, blank=True, null=True)   # e.g. "Course", "Site", "User"
    target_id = models.IntegerField(null=True, blank=True)
    target_label = models.CharField(max_length=255, blank=True, null=True)  # denormalized display name, e.g. the course title — survives target deletion

    metadata = models.JSONField(default=dict, blank=True)  # small structured extras, e.g. {"old_status": "active", "new_status": "paused"}
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', '-created_at']),
            models.Index(fields=['actor', '-created_at']),
            models.Index(fields=['action', '-created_at']),
        ]
