from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from organizations.permissions import IsOrgScoped
from .models import ImportJob
from .serializers import ImportJobSerializer
from .pipeline import run_import_pipeline

class ImportJobViewSet(viewsets.ModelViewSet):
    serializer_class = ImportJobSerializer
    permission_classes = [IsAuthenticated, IsOrgScoped]
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        if self.request.user.is_platform_super_admin:
            return ImportJob.objects.all()
        return ImportJob.objects.filter(organization_id=self.request.user.organization_id)

    def perform_create(self, serializer):
        org = self.request.user.organization
        job = serializer.save(organization=org, created_by=self.request.user)
        # Execute pipeline synchronously
        run_import_pipeline(job.id)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsOrgScoped])
@parser_classes([MultiPartParser, FormParser])
def upload_and_convert(request):
    """
    POST /api/import/upload/
    Form params: source_file (file), source_format (pptx|pdf|docx|video|audio|html|zip|scorm), target_course_id (optional)
    """
    source_file = request.FILES.get('source_file')
    source_format = request.data.get('source_format')
    target_course_id = request.data.get('target_course_id')

    if not source_file or not source_format:
        return Response({'detail': 'source_file and source_format are required.'}, status=status.HTTP_400_BAD_REQUEST)

    org = request.user.organization
    if not org and target_course_id:
        try:
            c = Course.objects.get(id=target_course_id)
            org = c.organization
        except Course.DoesNotExist:
            pass
    if not org:
        from organizations.models import Organization
        org = Organization.objects.first()

    job = ImportJob.objects.create(
        organization=org,
        created_by=request.user,
        target_course_id=target_course_id,
        source_file=source_file,
        source_format=source_format
    )

    try:
        run_import_pipeline(job.id)
        job.refresh_from_db()
        return Response({
            'import_job_id': str(job.id),
            'status': job.status,
            'target_course_id': job.target_course_id,
            'progress_percent': job.progress_percent,
            'warnings': job.error_log
        }, status=status.HTTP_201_CREATED)
    except Exception as err:
        job.refresh_from_db()
        return Response({
            'import_job_id': str(job.id),
            'status': 'failed',
            'error': str(err),
            'error_log': job.error_log
        }, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
