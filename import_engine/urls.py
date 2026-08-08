from django.urls import path
from .views import ImportJobViewSet, upload_and_convert

urlpatterns = [
    path('import/jobs/', ImportJobViewSet.as_view({'get': 'list', 'post': 'create'}), name='importjob-list'),
    path('import/jobs/<uuid:pk>/', ImportJobViewSet.as_view({'get': 'retrieve'}), name='importjob-detail'),
    path('import/upload/', upload_and_convert, name='import-upload'),
]
