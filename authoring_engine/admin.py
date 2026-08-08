from django.contrib import admin
from .models import (
    AuthoringAsset, LessonBlockTree, LessonBlock,
    ReadingContent, InteractionBlock, KCQuestion,
    ScenarioNode, CourseVersion
)

@admin.register(AuthoringAsset)
class AuthoringAssetAdmin(admin.ModelAdmin):
    list_display = ('id', 'organization', 'original_filename', 'mime_type', 'file_size', 'created_at')
    search_fields = ('original_filename', 'file_hash')

@admin.register(LessonBlockTree)
class LessonBlockTreeAdmin(admin.ModelAdmin):
    list_display = ('id', 'organization', 'lesson', 'version', 'created_at', 'updated_at')

@admin.register(LessonBlock)
class LessonBlockAdmin(admin.ModelAdmin):
    list_display = ('id', 'organization', 'tree', 'block_type', 'order', 'created_at')
    list_filter = ('block_type',)

@admin.register(ReadingContent)
class ReadingContentAdmin(admin.ModelAdmin):
    list_display = ('id', 'block')

@admin.register(InteractionBlock)
class InteractionBlockAdmin(admin.ModelAdmin):
    list_display = ('id', 'block', 'interaction_type')

@admin.register(KCQuestion)
class KCQuestionAdmin(admin.ModelAdmin):
    list_display = ('id', 'organization', 'block', 'question_type', 'points', 'order')

@admin.register(ScenarioNode)
class ScenarioNodeAdmin(admin.ModelAdmin):
    list_display = ('id', 'block', 'title', 'is_start_node', 'is_ending_node', 'ending_type', 'score_delta')

@admin.register(CourseVersion)
class CourseVersionAdmin(admin.ModelAdmin):
    list_display = ('id', 'organization', 'course', 'version_number', 'created_by', 'created_at')
