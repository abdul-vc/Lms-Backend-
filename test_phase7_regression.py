import os
import django
import zipfile
from io import BytesIO
import xml.etree.ElementTree as ET

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LAMS.settings')
django.setup()

from courses.models import Course, Module, Lesson
from authoring_engine.models import (
    LessonBlockTree, LessonBlock, ReadingContent
)
from organizations.models import Organization
from users.models import User
from rest_framework.test import APIRequestFactory, force_authenticate
from scorm_export.views import export_scorm12, export_scorm2004
from courses.scorm_engine import parse_imsmanifest

def run_phase7_test():
    print("=== PHASE 7 SCORM EXPORT ENGINE REGRESSION CHECK ===")

    admin_user = User.objects.filter(is_platform_super_admin=True).first() or User.objects.first()
    test_org = admin_user.organization or Organization.objects.first()
    factory = APIRequestFactory()

    # 1. Create a test course to export
    course = Course.objects.create(
        organization=test_org,
        author=admin_user,
        title="Phase 7 Exportable Enterprise SCORM Course",
        subtitle="Export test course for SCORM 1.2 and SCORM 2004",
        status="published"
    )
    mod = Module.objects.create(course=course, title="Module 1: SCORM Exporter Test", order=1)
    les = Lesson.objects.create(module=mod, title="Lesson 1: Exporter Content", type="reading", order=1)
    tree, _ = LessonBlockTree.objects.get_or_create(lesson=les, defaults={'organization': test_org})
    blk = LessonBlock.objects.create(organization=test_org, tree=tree, block_type="paragraph", order=0)
    ReadingContent.objects.create(block=blk, html_content="<p>SCORM export payload content</p>", markdown_content="SCORM export payload content")

    print(f"Created course ID {course.id} ('{course.title}') for SCORM export testing.")

    # 2. TEST SCORM 1.2 EXPORT
    req12 = factory.post('/api/authoring/export/scorm12/', {'course_id': course.id}, format='json')
    force_authenticate(req12, user=admin_user)
    res12 = export_scorm12(req12)
    assert res12.status_code == 200, f"SCORM 1.2 export failed: {res12.data}"
    assert res12['Content-Type'] == 'application/zip'

    # Unpack zip and validate SCORM 1.2 schema
    zip12 = zipfile.ZipFile(BytesIO(res12.content))
    assert 'imsmanifest.xml' in zip12.namelist()
    assert 'index.html' in zip12.namelist()

    manifest_xml12 = zip12.read('imsmanifest.xml').decode('utf-8')
    assert '<schemaversion>1.2</schemaversion>' in manifest_xml12, "SCORM 1.2 schemaversion verified"
    assert 'http://www.imsproject.org/xsd/imscp_rootv1p1p2' in manifest_xml12, "SCORM 1.2 namespace verified"

    index_html12 = zip12.read('index.html').decode('utf-8')
    assert 'findAPI(window)' in index_html12, "SCORM 1.2 API adapter present in standalone HTML"
    assert 'LMSInitialize' in index_html12, "SCORM 1.2 LMSInitialize call present"
    print("  [OK] SCORM 1.2 Export: Validated zip archive, imsmanifest.xml schema, and standalone HTML player.")

    # 3. TEST SCORM 2004 4TH EDITION EXPORT
    req2004 = factory.post('/api/authoring/export/scorm2004/', {'course_id': course.id}, format='json')
    force_authenticate(req2004, user=admin_user)
    res2004 = export_scorm2004(req2004)
    assert res2004.status_code == 200, f"SCORM 2004 export failed: {res2004.data}"
    assert res2004['Content-Type'] == 'application/zip'

    zip2004 = zipfile.ZipFile(BytesIO(res2004.content))
    assert 'imsmanifest.xml' in zip2004.namelist()
    assert 'index.html' in zip2004.namelist()

    manifest_xml2004 = zip2004.read('imsmanifest.xml').decode('utf-8')
    assert '<schemaversion>2004 4th Edition</schemaversion>' in manifest_xml2004, "SCORM 2004 schemaversion verified"
    assert 'imsss:sequencing' in manifest_xml2004, "SCORM 2004 sequencing tags verified"

    index_html2004 = zip2004.read('index.html').decode('utf-8')
    assert 'API_1484_11' in index_html2004, "SCORM 2004 API_1484_11 handle present"
    assert 'Initialize' in index_html2004, "SCORM 2004 Initialize call present"
    print("  [OK] SCORM 2004 4th Edition Export: Validated zip archive, 2004 manifest schema, and sequencing tags.")

    # 4. TEST ROUND-TRIP INGESTION OF EXPORTED PACKAGE VIA scorm_engine.py
    import tempfile
    temp_dir = tempfile.mkdtemp()
    manifest_temp = os.path.join(temp_dir, 'imsmanifest.xml')
    with open(manifest_temp, 'w', encoding='utf-8') as f:
        f.write(manifest_xml12)
    
    parsed_data = parse_imsmanifest(manifest_temp)
    assert parsed_data['title'] == course.title
    assert parsed_data['version'] == '1.2'
    print("  [OK] SCORM Round-Trip: Exported SCORM 1.2 manifest cleanly re-parsed by internal LMS SCORM engine.")

    print("\n=== PHASE 7 SCORM EXPORT ENGINE REGRESSION CHECK PASSED 100% ===")

if __name__ == '__main__':
    run_phase7_test()
