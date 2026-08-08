from django.db import models


LEVEL_CHOICES = [
    ('Foundational', 'Foundational'),
    ('Intermediate', 'Intermediate'),
    ('Advanced', 'Advanced'),
]

STATUS_CHOICES = [
    ('draft', 'Draft'),
    ('published', 'Published'),
    ('archived', 'Archived'),
]

LESSON_TYPE_CHOICES = [
    ('video', 'Video'),
    ('interactive', 'Interactive'),
    ('reading', 'Reading'),
    ('knowledge_check', 'Knowledge Check'),
    ('scenario', 'Scenario'),
]

# DEPRECATED: Legacy choices tuple removed to eliminate hardcoded options.
INTERACTION_CHOICES = []


class Course(models.Model):
    """Top-level course entity — mirrors frontend Course interface."""
    organization = models.ForeignKey(
        'organizations.Organization', on_delete=models.CASCADE,
        related_name='courses', null=True, blank=True
    )
    author = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL,
        related_name='authored_courses', null=True, blank=True
    )
    title = models.CharField(max_length=255)
    subtitle = models.TextField(blank=True, default='')
    certificate_template = models.ForeignKey(
        'organizations.CertificateTemplate', on_delete=models.SET_NULL,
        related_name='courses', null=True, blank=True
    )
    category = models.CharField(max_length=100, blank=True, null=True)
    hero_url = models.CharField(max_length=1000, blank=True, default='')
    duration_hrs = models.FloatField(default=1.0)
    passing_score = models.IntegerField(default=80)
    level = models.CharField(max_length=50, choices=LEVEL_CHOICES, default='Foundational')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    accent = models.CharField(max_length=100, default='var(--brand)', blank=True)
    skills = models.JSONField(default=list, blank=True)
    time_limit_minutes = models.IntegerField(default=0)
    badge_icon = models.CharField(max_length=50, blank=True, default="🎓")
    badge_name = models.CharField(max_length=255, blank=True, default="")
    is_scorm = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.status.upper()}] {self.title}"


class Module(models.Model):
    """A module (chapter) belonging to a course."""
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='modules')
    title = models.CharField(max_length=255)
    summary = models.TextField(blank=True, default='')
    order = models.IntegerField(default=0)
    locked = models.BooleanField(default=False)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.course.title} › {self.title}"


class Lesson(models.Model):
    """
    A single lesson within a module.
    - interaction: slug for interactive component type
    """
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='lessons')
    title = models.CharField(max_length=255)
    duration = models.CharField(max_length=50, default='5 min')
    type = models.CharField(max_length=20, choices=LESSON_TYPE_CHOICES, default='video')
    order = models.IntegerField(default=0)
    video_url = models.CharField(max_length=1000, blank=True, null=True, help_text="Direct URL to the uploaded video")
    # DEPRECATED: Retained for backward DB schema compatibility; no choices constraint.
    interaction = models.CharField(
        max_length=50, blank=True, null=True,
        help_text="[Deprecated] Legacy interaction component slug"
    )

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.module.title} › {self.title}"


class AssessmentQuestion(models.Model):
    """
    An assessment question for a course, imported via CSV.
    Uses a standard 4-option multiple choice format.
    """
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='assessment_questions')
    question_text = models.TextField()
    option_a = models.CharField(max_length=500)
    option_b = models.CharField(max_length=500)
    option_c = models.CharField(max_length=500)
    option_d = models.CharField(max_length=500)
    # The correct option key, e.g., 'A', 'B', 'C', or 'D'
    correct_option = models.CharField(max_length=1)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.course.title} - Q: {self.question_text[:30]}..."

class AccessRequest(models.Model):
    STATUS_CHOICES = [('pending', 'Pending'), ('accepted', 'Accepted'), ('rejected', 'Rejected')]
    student = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='access_requests')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='access_requests')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    requested_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='resolved_access_requests')

    class Meta:
        unique_together = ('student', 'course')

class AssessmentAttempt(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='attempts')
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='assessment_attempts')
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    auto_submitted = models.BooleanField(default=False)  # true if the timer expired, not a manual submit
    score_percent = models.IntegerField(null=True, blank=True)
    passed = models.BooleanField(null=True, blank=True)
    answers = models.JSONField(default=dict, blank=True)  # {question_id: "A", ...}

    class Meta:
        ordering = ['-started_at']

class LessonProgress(models.Model):
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='lesson_progress')
    lesson = models.ForeignKey('courses.Lesson', on_delete=models.CASCADE, related_name='progress_records')
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_position_seconds = models.FloatField(default=0)  # for resuming video playback

    class Meta:
        unique_together = ('user', 'lesson')

import uuid

class IssuedCertificate(models.Model):
    certificate_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='certificates')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='issued_certificates')
    template = models.ForeignKey('organizations.CertificateTemplate', on_delete=models.SET_NULL, null=True, blank=True, related_name='issued_certificates')
    template_html_snapshot = models.TextField(blank=True, default='')
    issued_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'course')

class LearningPath(models.Model):
    organization = models.ForeignKey(
        'organizations.Organization', on_delete=models.CASCADE,
        related_name='learning_paths', null=True, blank=True
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']

class LearningPathCourse(models.Model):
    learning_path = models.ForeignKey(LearningPath, on_delete=models.CASCADE, related_name='path_courses')
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    order = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['order']
        unique_together = ('learning_path', 'course')


class ScormPackage(models.Model):
    course = models.OneToOneField(Course, on_delete=models.CASCADE, related_name='scorm_package')
    organization = models.ForeignKey(
        'organizations.Organization', on_delete=models.CASCADE,
        related_name='scorm_packages', null=True, blank=True
    )
    package_file = models.FileField(upload_to='scorm_zips/', blank=True, null=True)
    extracted_dir = models.CharField(max_length=500)
    manifest_id = models.CharField(max_length=255, blank=True, default='')
    title = models.CharField(max_length=255, blank=True, default='')
    version = models.CharField(max_length=50, default='1.2')  # '1.2' or '2004'
    launch_url = models.CharField(max_length=500, blank=True, default='')
    schema_version = models.CharField(max_length=50, blank=True, default='')
    mastery_score = models.FloatField(null=True, blank=True)
    raw_manifest_xml = models.TextField(blank=True, default='')
    sco_structure = models.JSONField(default=list, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"SCORM Package ({self.version}) - {self.title or self.course.title}"


class ScormTracking(models.Model):
    STATUS_CHOICES = [
        ('not attempted', 'Not Attempted'),
        ('incomplete', 'Incomplete'),
        ('completed', 'Completed'),
        ('passed', 'Passed'),
        ('failed', 'Failed'),
        ('browsed', 'Browsed'),
    ]

    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='scorm_trackings')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='scorm_trackings')
    organization = models.ForeignKey(
        'organizations.Organization', on_delete=models.CASCADE,
        related_name='scorm_trackings', null=True, blank=True
    )
    
    lesson_status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='not attempted')
    lesson_location = models.CharField(max_length=255, blank=True, default='')
    suspend_data = models.TextField(blank=True, default='')
    score_raw = models.FloatField(null=True, blank=True)
    score_max = models.FloatField(null=True, blank=True)
    score_min = models.FloatField(null=True, blank=True)
    score_scaled = models.FloatField(null=True, blank=True)
    session_time = models.CharField(max_length=50, blank=True, default='')
    total_time_seconds = models.IntegerField(default=0)
    cmi_data = models.JSONField(default=dict, blank=True)
    
    first_accessed = models.DateTimeField(auto_now_add=True)
    last_accessed = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('user', 'course')

    def __str__(self):
        return f"SCORM Tracking - {self.user.username} on {self.course.title}: {self.lesson_status}"

