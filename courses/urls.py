from django.urls import path
from .views import CourseViewSet, ModuleViewSet, LessonViewSet, upload_hero_image, upload_lesson_video, download_assessment_template, import_assessment_csv, get_assessment_questions, start_assessment, submit_assessment, AccessRequestViewSet, request_access, MyCertificatesView, OrgIssuedCertificatesView, IssuedCertificateDetailView, dashboard_stats, dashboard_leaderboard, dashboard_badges, learner_dashboard_data, LearningPathViewSet, ScormRuntimeTrackingView, AssessmentQuestionViewSet
from .ai_views import ai_chat

# Manual URL patterns — no extra packages needed.
# Naming convention: api/courses/*, api/modules/*, api/lessons/*

urlpatterns = [
    # ── Courses ──────────────────────────────────────────────────────────────
    path(
        'courses/',
        CourseViewSet.as_view({'get': 'list', 'post': 'create'}),
        name='course-list',
    ),
    path(
        'courses/<int:pk>/',
        CourseViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}),
        name='course-detail',
    ),
    path(
        'courses/<int:pk>/progress/',
        CourseViewSet.as_view({'get': 'progress'}),
        name='course-progress',
    ),
    path(
        'courses/<int:pk>/publish/',
        CourseViewSet.as_view({'post': 'publish'}),
        name='course-publish',
    ),

    # ── Modules (nested under course + standalone) ────────────────────────
    path(
        'courses/<int:course_pk>/modules/',
        ModuleViewSet.as_view({'get': 'list', 'post': 'create'}),
        name='course-module-list',
    ),
    path(
        'modules/<int:pk>/',
        ModuleViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}),
        name='module-detail',
    ),

    # ── Lessons (nested under module + standalone) ────────────────────────
    path(
        'modules/<int:module_pk>/lessons/',
        LessonViewSet.as_view({'get': 'list', 'post': 'create'}),
        name='module-lesson-list',
    ),
    path(
        'lessons/<int:pk>/',
        LessonViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}),
        name='lesson-detail',
    ),
    path(
        'lessons/<int:pk>/progress/',
        LessonViewSet.as_view({'get': 'progress', 'patch': 'progress'}),
        name='lesson-progress',
    ),

    # ── Image & Video upload ─────────────────────────────────────────────────
    path(
        'upload/hero/',
        upload_hero_image,
        name='upload-hero',
    ),
    path(
        'upload/video/',
        upload_lesson_video,
        name='upload-video',
    ),

    # ── Assessments ──────────────────────────────────────────────────────────
    path(
        'courses/<int:course_pk>/questions/',
        AssessmentQuestionViewSet.as_view({'get': 'list', 'post': 'create'}),
        name='course-question-list',
    ),
    path(
        'questions/<int:pk>/',
        AssessmentQuestionViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}),
        name='question-detail',
    ),
    path(
        'courses/<int:course_pk>/assessment/template/',
        download_assessment_template,
        name='assessment-template',
    ),
    path(
        'courses/<int:course_pk>/assessment/import/',
        import_assessment_csv,
        name='assessment-import',
    ),
    path(
        'courses/<int:course_pk>/assessment/questions/',
        get_assessment_questions,
        name='assessment-questions',
    ),
    path(
        'courses/<int:course_pk>/assessment/start/',
        start_assessment,
        name='assessment-start',
    ),
    path(
        'courses/<int:course_pk>/assessment/<int:attempt_id>/submit/',
        submit_assessment,
        name='assessment-submit',
    ),
    path(
        'courses/<int:course_pk>/request-access/',
        request_access,
        name='request-access',
    ),
    path(
        'access-requests/',
        AccessRequestViewSet.as_view({'get': 'list'}),
        name='access-request-list',
    ),
    path(
        'access-requests/<int:pk>/accept/',
        AccessRequestViewSet.as_view({'post': 'accept'}),
        name='access-request-accept',
    ),
    path(
        'access-requests/<int:pk>/reject/',
        AccessRequestViewSet.as_view({'post': 'reject'}),
        name='access-request-reject',
    ),
    path(
        'certificates/',
        MyCertificatesView.as_view(),
        name='my-certificates',
    ),
    path(
        'certificates/org/',
        OrgIssuedCertificatesView.as_view(),
        name='org-issued-certificates',
    ),
    path(
        'certificates/<int:pk>/',
        IssuedCertificateDetailView.as_view(),
        name='issued-certificate-detail',
    ),
    path(
        'learner/dashboard/',
        learner_dashboard_data,
        name='learner-dashboard-data',
    ),
    path(
        'dashboard/',
        learner_dashboard_data,
        name='dashboard-stats',
    ),
    path(
        'dashboard/leaderboard/',
        dashboard_leaderboard,
        name='dashboard-leaderboard',
    ),
    path(
        'dashboard/badges/',
        dashboard_badges,
        name='dashboard-badges',
    ),
    path(
        'paths/',
        LearningPathViewSet.as_view({'get': 'list', 'post': 'create'}),
        name='learning-path-list',
    ),
    path(
        'paths/<int:pk>/',
        LearningPathViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}),
        name='learning-path-detail',
    ),
    path(
        'courses/<int:course_id>/scorm-runtime/',
        ScormRuntimeTrackingView.as_view(),
        name='scorm-runtime',
    ),
    path(
        'ai/chat/',
        ai_chat,
        name='ai-chat',
    ),
]
