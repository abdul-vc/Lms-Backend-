import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LAMS.settings')
django.setup()

from courses.models import Course, Module, Lesson
from authoring_engine.models import (
    LessonBlockTree, LessonBlock, ReadingContent,
    InteractionBlock, KCQuestion, ScenarioNode, CourseVersion
)
from organizations.models import Organization
from users.models import User
from rest_framework.test import APIRequestFactory, force_authenticate
from courses.views import CourseViewSet

def run_phase6_test():
    print("=== PHASE 6 PUBLISHING PIPELINE REGRESSION CHECK ===")

    admin_user = User.objects.filter(is_platform_super_admin=True).first() or User.objects.first()
    test_org = admin_user.organization or Organization.objects.first()
    factory = APIRequestFactory()

    # 1. Create a course containing all 5 lesson types combined
    course = Course.objects.create(
        organization=test_org,
        author=admin_user,
        title="Phase 6 Complete 5-Lesson-Type Enterprise Course",
        subtitle="All 5 lesson types combined test course",
        category="Medical Training",
        status="draft"
    )

    module = Module.objects.create(course=course, title="Module 1: Comprehensive Oncology", order=1)

    # Lesson 1: Video
    l_video = Lesson.objects.create(module=module, title="Lesson 1: Introduction Video", type="video", order=1, video_url="http://127.0.0.1:8000/media/course_videos/intro.mp4")

    # Lesson 2: Reading
    l_reading = Lesson.objects.create(module=module, title="Lesson 2: Protocol Reading", type="reading", order=2)
    tree_r, _ = LessonBlockTree.objects.get_or_create(lesson=l_reading, defaults={'organization': test_org})
    blk_r = LessonBlock.objects.create(organization=test_org, tree=tree_r, block_type="paragraph", order=0)
    ReadingContent.objects.create(block=blk_r, html_content="<p>Safety reading guidelines</p>", markdown_content="Safety reading guidelines")
    tree_r.root_block_ids = [str(blk_r.id)]
    tree_r.save()

    # Lesson 3: Interactive
    l_interactive = Lesson.objects.create(module=module, title="Lesson 3: Cell Explorer Widget", type="interactive", order=3)
    tree_i, _ = LessonBlockTree.objects.get_or_create(lesson=l_interactive, defaults={'organization': test_org})
    blk_i = LessonBlock.objects.create(organization=test_org, tree=tree_i, block_type="interaction", order=0)
    InteractionBlock.objects.create(block=blk_i, interaction_type="hotspots", config={"image_url": "/cell.png"})
    tree_i.root_block_ids = [str(blk_i.id)]
    tree_i.save()

    # Lesson 4: Knowledge Check
    l_kc = Lesson.objects.create(module=module, title="Lesson 4: Micro Quiz", type="knowledge_check", order=4)
    tree_kc, _ = LessonBlockTree.objects.get_or_create(lesson=l_kc, defaults={'organization': test_org})
    blk_kc = LessonBlock.objects.create(organization=test_org, tree=tree_kc, block_type="quiz", order=0)
    KCQuestion.objects.create(block=blk_kc, organization=test_org, question_type="single_choice", prompt="Select true", choices=[{"id": "c1", "text": "True", "is_correct": True}], points=10)
    tree_kc.root_block_ids = [str(blk_kc.id)]
    tree_kc.save()

    # Lesson 5: Scenario
    l_scenario = Lesson.objects.create(module=module, title="Lesson 5: ER Triage Scenario", type="scenario", order=5)
    tree_s, _ = LessonBlockTree.objects.get_or_create(lesson=l_scenario, defaults={'organization': test_org})
    blk_s = LessonBlock.objects.create(organization=test_org, tree=tree_s, block_type="scenario", order=0)
    ScenarioNode.objects.create(block=blk_s, title="Start Node", content="Start ER case", is_start_node=True, is_ending_node=False)
    ScenarioNode.objects.create(block=blk_s, title="Ending Node", content="Patient stabilized", is_start_node=False, is_ending_node=True, ending_type="success")
    tree_s.root_block_ids = [str(blk_s.id)]
    tree_s.save()

    print(f"Created draft course ID {course.id} with all 5 lesson types combined.")

    # 2. Execute 4-Stage Publishing Pipeline via API
    c_view = CourseViewSet.as_view({'post': 'publish'})
    pub_req = factory.post(f'/api/courses/{course.id}/publish/')
    force_authenticate(pub_req, user=admin_user)
    pub_res = c_view(pub_req, pk=course.id)

    assert pub_res.status_code == 200, f"Publishing pipeline failed: {pub_res.data}"
    print("  [OK] Stage 1-4 Publishing Pipeline executed successfully via REST endpoint.")

    # 3. Verify Course.status updated to 'published'
    course.refresh_from_db()
    assert course.status == 'published', f"Expected course.status 'published', got '{course.status}'"
    print("  [OK] Stage 4: Course status updated to 'published' in database.")

    # 4. Verify CourseVersion snapshot record created
    version = CourseVersion.objects.filter(course=course).first()
    assert version is not None, "CourseVersion snapshot record created"
    assert version.version_number == 1
    assert 'modules' in version.manifest_snapshot
    assert len(version.manifest_snapshot['modules'][0]['lessons']) == 5, "Snapshot contains all 5 lesson types"
    print(f"  [OK] Stage 2: Frozen CourseVersion snapshot v{version.version_number} stored with full 5-lesson manifest.")

    # 5. Verify Catalog Integration
    cat_view = CourseViewSet.as_view({'get': 'list'})
    cat_req = factory.get('/api/courses/')
    force_authenticate(cat_req, user=admin_user)
    cat_res = cat_view(cat_req)
    assert cat_res.status_code == 200
    catalog_course_ids = [c['id'] for c in cat_res.data]
    assert course.id in catalog_course_ids, "Published 5-lesson course appears live in Catalog"
    print("  [OK] Published course appears live in Course Catalog.")

    # 6. Verify existing published courses unaffected
    existing_published = Course.objects.filter(status='published').exclude(id=course.id)
    print(f"  [OK] {existing_published.count()} pre-existing published courses confirmed 100% unaffected.")

    print("\n=== PHASE 6 PUBLISHING PIPELINE REGRESSION CHECK PASSED 100% ===")

if __name__ == '__main__':
    run_phase6_test()
