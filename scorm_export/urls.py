from django.urls import path
from .views import export_scorm12, export_scorm2004

urlpatterns = [
    path('authoring/export/scorm12/', export_scorm12, name='export-scorm12'),
    path('authoring/export/scorm2004/', export_scorm2004, name='export-scorm2004'),
]
