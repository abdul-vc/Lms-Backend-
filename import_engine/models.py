import uuid
from django.db import models

SOURCE_FORMAT_CHOICES = [
    ('pdf', 'PDF Document'),
    ('pptx', 'PowerPoint Presentation'),
    ('docx', 'Word Document'),
    ('video', 'Video File'),
    ('audio', 'Audio File'),
    ('html', 'HTML Package'),
    ('zip', 'ZIP Archive'),
    ('scorm', 'SCORM Package'),
]

STATUS_CHOICES = [
    ('queued', 'Queued'),
    ('extracting', 'Extracting'),
    ('parsing', 'Parsing'),
    ('converting', 'Converting'),
    ('normalizing', 'Normalizing'),
    ('completed', 'Completed'),
    ('failed', 'Failed'),
]

class ImportJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'organizations.Organization', on_delete=models.CASCADE,
        related_name='import_jobs', db_index=True
    )
    created_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_import_jobs'
    )
    target_course = models.ForeignKey(
        'courses.Course', on_delete=models.CASCADE, null=True, blank=True,
        related_name='import_jobs'
    )
    source_file = models.FileField(upload_to='import_scratch/')
    source_format = models.CharField(max_length=20, choices=SOURCE_FORMAT_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued')
    progress_percent = models.IntegerField(default=0)
    error_log = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'import_job'
        ordering = ['-created_at']

    def __str__(self):
        return f"ImportJob [{self.source_format}] ({self.status}) - {self.id}"
