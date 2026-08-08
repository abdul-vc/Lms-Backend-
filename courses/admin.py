from django.contrib import admin
from .models import (
    Course, Module, Lesson, AssessmentQuestion, AccessRequest,
    AssessmentAttempt, LessonProgress, IssuedCertificate,
    LearningPath, LearningPathCourse
)

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'organization', 'status', 'level', 'created_at')
    list_filter = ('status', 'level', 'organization')
    search_fields = ('title', 'organization__name')


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'course', 'order')
    list_filter = ('course__organization',)
    search_fields = ('title', 'course__title')


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'module', 'type', 'order')
    list_filter = ('type',)
    search_fields = ('title', 'module__title')


@admin.register(AssessmentQuestion)
class AssessmentQuestionAdmin(admin.ModelAdmin):
    list_display = ('id', 'question_text', 'course', 'correct_option', 'created_at')
    list_filter = ('course',)
    search_fields = ('question_text', 'course__title')


@admin.register(AccessRequest)
class AccessRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'student', 'course', 'status', 'requested_at')
    list_filter = ('status',)
    search_fields = ('student__username', 'course__title')


@admin.register(AssessmentAttempt)
class AssessmentAttemptAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'course', 'score_percent', 'passed', 'started_at')
    list_filter = ('passed', 'course')
    search_fields = ('user__username', 'course__title')


@admin.register(LessonProgress)
class LessonProgressAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'lesson', 'completed', 'completed_at')
    list_filter = ('completed',)


@admin.register(IssuedCertificate)
class IssuedCertificateAdmin(admin.ModelAdmin):
    list_display = ('id', 'certificate_id', 'user', 'course', 'issued_at')
    search_fields = ('certificate_id', 'user__username', 'course__title')


@admin.register(LearningPath)
class LearningPathAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'organization', 'created_at')
    list_filter = ('organization',)


@admin.register(LearningPathCourse)
class LearningPathCourseAdmin(admin.ModelAdmin):
    list_display = ('id', 'learning_path', 'course', 'order')

