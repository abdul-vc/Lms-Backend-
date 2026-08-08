from django.contrib import admin
from .models import ImportJob

@admin.register(ImportJob)
class ImportJobAdmin(admin.ModelAdmin):
    list_display = ('id', 'organization', 'created_by', 'target_course', 'source_format', 'status', 'progress_percent', 'created_at')
    list_filter = ('source_format', 'status')
