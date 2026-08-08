from django.http import HttpResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from organizations.permissions import IsOrgScoped
from courses.models import Course
from .exporter import export_course_to_scorm

@api_view(['POST'])
@permission_classes([IsAuthenticated, IsOrgScoped])
def export_scorm12(request):
    """
    POST /api/authoring/export/scorm12/
    Body: { "course_id": int }
    """
    course_id = request.data.get('course_id')
    if not course_id:
        return Response({'detail': 'course_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        if request.user.is_platform_super_admin:
            course = Course.objects.get(id=course_id)
        else:
            course = Course.objects.get(id=course_id, organization_id=request.user.organization_id)
    except Course.DoesNotExist:
        return Response({'detail': 'Course not found.'}, status=status.HTTP_404_NOT_FOUND)

    if course.status != 'published':
        return Response({'detail': 'Course must be published before exporting to SCORM.'}, status=status.HTTP_400_BAD_REQUEST)

    zip_buffer = export_course_to_scorm(course, scorm_version="1.2")
    filename = f"{course.title.replace(' ', '_')}_SCORM12.zip"

    response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsOrgScoped])
def export_scorm2004(request):
    """
    POST /api/authoring/export/scorm2004/
    Body: { "course_id": int }
    """
    course_id = request.data.get('course_id')
    if not course_id:
        return Response({'detail': 'course_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        if request.user.is_platform_super_admin:
            course = Course.objects.get(id=course_id)
        else:
            course = Course.objects.get(id=course_id, organization_id=request.user.organization_id)
    except Course.DoesNotExist:
        return Response({'detail': 'Course not found.'}, status=status.HTTP_404_NOT_FOUND)

    if course.status != 'published':
        return Response({'detail': 'Course must be published before exporting to SCORM.'}, status=status.HTTP_400_BAD_REQUEST)

    zip_buffer = export_course_to_scorm(course, scorm_version="2004")
    filename = f"{course.title.replace(' ', '_')}_SCORM2004.zip"

    response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
