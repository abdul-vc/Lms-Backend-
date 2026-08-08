from django.urls import path
from .views import (
    LessonBlockTreeViewSet, LessonBlockViewSet, ReadingContentViewSet,
    InteractionBlockViewSet, KCQuestionViewSet, ScenarioNodeViewSet, AuthoringAssetViewSet,
    CourseVersionViewSet, reorder_blocks, evaluate_kc_question, validate_scenario
)

urlpatterns = [
    path('authoring/trees/', LessonBlockTreeViewSet.as_view({'get': 'list', 'post': 'create'}), name='blocktree-list'),
    path('authoring/trees/<int:pk>/', LessonBlockTreeViewSet.as_view({'get': 'retrieve', 'put': 'update', 'delete': 'destroy'}), name='blocktree-detail'),
    path('authoring/trees/<int:tree_id>/reorder/', reorder_blocks, name='blocktree-reorder'),
    path('authoring/blocks/', LessonBlockViewSet.as_view({'get': 'list', 'post': 'create'}), name='block-list'),
    path('authoring/blocks/<uuid:pk>/', LessonBlockViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='block-detail'),
    path('authoring/reading/', ReadingContentViewSet.as_view({'get': 'list', 'post': 'create'}), name='reading-list'),
    path('authoring/reading/<int:pk>/', ReadingContentViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='reading-detail'),
    path('authoring/interactions/', InteractionBlockViewSet.as_view({'get': 'list', 'post': 'create'}), name='interaction-list'),
    path('authoring/interactions/<int:pk>/', InteractionBlockViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='interaction-detail'),
    path('authoring/kc-questions/', KCQuestionViewSet.as_view({'get': 'list', 'post': 'create'}), name='kcquestion-list'),
    path('authoring/kc-questions/<int:pk>/', KCQuestionViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='kcquestion-detail'),
    path('authoring/kc-questions/<int:question_id>/evaluate/', evaluate_kc_question, name='kcquestion-evaluate'),
    path('authoring/scenario-nodes/', ScenarioNodeViewSet.as_view({'get': 'list', 'post': 'create'}), name='scenarionode-list'),
    path('authoring/scenario-nodes/<uuid:pk>/', ScenarioNodeViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='scenarionode-detail'),
    path('authoring/scenarios/<uuid:block_id>/validate/', validate_scenario, name='scenario-validate'),
    path('authoring/assets/', AuthoringAssetViewSet.as_view({'get': 'list', 'post': 'create'}), name='asset-list'),
    path('authoring/assets/<uuid:pk>/', AuthoringAssetViewSet.as_view({'get': 'retrieve', 'delete': 'destroy'}), name='asset-detail'),
    path('authoring/versions/', CourseVersionViewSet.as_view({'get': 'list'}), name='version-list'),
    path('authoring/versions/<int:pk>/', CourseVersionViewSet.as_view({'get': 'retrieve'}), name='version-detail'),
    path('authoring/versions/<int:pk>/rollback/', CourseVersionViewSet.as_view({'post': 'rollback'}), name='version-rollback'),
]
