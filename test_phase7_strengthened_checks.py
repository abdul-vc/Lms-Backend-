import os
import django
from django.core.files.uploadedfile import SimpleUploadedFile

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LAMS.settings')
django.setup()

from courses.models import Course, Module, Lesson, ScormPackage
from authoring_engine.models import LessonBlockTree, LessonBlock, ReadingContent
from organizations.models import Organization
from users.models import User
from rest_framework.test import APIRequestFactory, force_authenticate
from scorm_export.views import export_scorm12, export_scorm2004
from import_engine.views import upload_and_convert

def run_strengthened_checks():
    print("=== PHASE 7 STRENGTHENED VERIFICATION CHECKS ===")

    admin_user = User.objects.filter(is_platform_super_admin=True).first() or User.objects.first()
    test_org = admin_user.organization or Organization.objects.first()
    factory = APIRequestFactory()

    # -------------------------------------------------------------------------
    # CHECK 1: FULL UPLOAD PIPELINE INGESTION ROUND-TRIP (SCORM 1.2 & SCORM 2004)
    # -------------------------------------------------------------------------
    print("\n--- Check 1: Full Upload Pipeline SCORM Ingestion Round-Trip ---")
    pub_course = Course.objects.create(
        organization=test_org,
        author=admin_user,
        title="Published SCORM Export Course",
        status="published"
    )
    mod = Module.objects.create(course=pub_course, title="Module 1", order=1)
    les = Lesson.objects.create(module=mod, title="Lesson 1", type="reading", order=1)
    tree, _ = LessonBlockTree.objects.get_or_create(lesson=les, defaults={'organization': test_org})
    blk = LessonBlock.objects.create(organization=test_org, tree=tree, block_type="paragraph", order=0)
    ReadingContent.objects.create(block=blk, html_content="<p>Payload</p>", markdown_content="Payload")

    # A. Export to SCORM 1.2
    req12 = factory.post('/api/authoring/export/scorm12/', {'course_id': pub_course.id}, format='json')
    force_authenticate(req12, user=admin_user)
    res12 = export_scorm12(req12)
    assert res12.status_code == 200

    # Ingest SCORM 1.2 ZIP via Universal Import (upload_and_convert)
    uf12 = SimpleUploadedFile("exported_scorm12.zip", res12.content, content_type="application/zip")
    ingest_req12 = factory.post('/api/import/upload/', {'source_file': uf12, 'source_format': 'scorm'}, format='multipart')
    force_authenticate(ingest_req12, user=admin_user)
    ingest_res12 = upload_and_convert(ingest_req12)

    assert ingest_res12.status_code == 201, f"SCORM 1.2 upload pipeline failed: {ingest_res12.data}"
    target_c1 = Course.objects.get(id=ingest_res12.data['target_course_id'])
    print(f"  [PASS] SCORM 1.2 Round-Trip: Exported ZIP successfully imported via Universal Import -> Course ID {target_c1.id} ('{target_c1.title}').")

    # B. Export to SCORM 2004
    req2004 = factory.post('/api/authoring/export/scorm2004/', {'course_id': pub_course.id}, format='json')
    force_authenticate(req2004, user=admin_user)
    res2004 = export_scorm2004(req2004)
    assert res2004.status_code == 200

    # Ingest SCORM 2004 ZIP via Universal Import (upload_and_convert)
    uf2004 = SimpleUploadedFile("exported_scorm2004.zip", res2004.content, content_type="application/zip")
    ingest_req2004 = factory.post('/api/import/upload/', {'source_file': uf2004, 'source_format': 'scorm'}, format='multipart')
    force_authenticate(ingest_req2004, user=admin_user)
    ingest_res2004 = upload_and_convert(ingest_req2004)

    assert ingest_res2004.status_code == 201, f"SCORM 2004 upload pipeline failed: {ingest_res2004.data}"
    target_c2 = Course.objects.get(id=ingest_res2004.data['target_course_id'])
    print(f"  [PASS] SCORM 2004 Round-Trip: Exported ZIP successfully imported via Universal Import -> Course ID {target_c2.id} ('{target_c2.title}').")

    # -------------------------------------------------------------------------
    # CHECK 2: DRAFT COURSE EXPORT PROTECTION CHECK
    # -------------------------------------------------------------------------
    print("\n--- Check 2: Draft Course Export Protection Check ---")
    draft_course = Course.objects.create(
        organization=test_org,
        author=admin_user,
        title="Unpublished Draft Course",
        status="draft"
    )

    req_d12 = factory.post('/api/authoring/export/scorm12/', {'course_id': draft_course.id}, format='json')
    force_authenticate(req_d12, user=admin_user)
    res_d12 = export_scorm12(req_d12)

    assert res_d12.status_code == 400, f"Expected HTTP 400 for draft SCORM 1.2 export, got {res_d12.status_code}"
    assert "Course must be published before exporting to SCORM." in str(res_d12.data.get('detail'))
    print("  [PASS] Draft SCORM 1.2 Export blocked with HTTP 400 ('Course must be published before exporting to SCORM.').")

    req_d2004 = factory.post('/api/authoring/export/scorm2004/', {'course_id': draft_course.id}, format='json')
    force_authenticate(req_d2004, user=admin_user)
    res_d2004 = export_scorm2004(req_d2004)

    assert res_d2004.status_code == 400, f"Expected HTTP 400 for draft SCORM 2004 export, got {res_d2004.status_code}"
    assert "Course must be published before exporting to SCORM." in str(res_d2004.data.get('detail'))
    print("  [PASS] Draft SCORM 2004 Export blocked with HTTP 400 ('Course must be published before exporting to SCORM.').")

    print("\n=== ALL STRENGTHENED PHASE 7 CHECKS PASSED 100% ===")

if __name__ == '__main__':
    run_strengthened_checks()
