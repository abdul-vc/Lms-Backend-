import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LAMS.settings')
django.setup()

from courses.models import Course, Module, Lesson
from authoring_engine.models import (
    LessonBlockTree, LessonBlock, KCQuestion, ScenarioNode, CourseVersion
)
from organizations.models import Organization
from users.models import User
from rest_framework.test import APIRequestFactory, force_authenticate
from courses.views import CourseViewSet

def run_validation_failure_checks():
    print("=== PHASE 6 PUBLISHING PRE-FLIGHT VALIDATION FAILURE CHECKS ===")

    admin_user = User.objects.filter(is_platform_super_admin=True).first() or User.objects.first()
    test_org = admin_user.organization or Organization.objects.first()
    factory = APIRequestFactory()

    # -------------------------------------------------------------------------
    # TEST 1: KNOWLEDGE CHECK LESSON WITH ZERO QUESTIONS
    # -------------------------------------------------------------------------
    print("\n--- Test 1: Knowledge Check Lesson with Zero Questions ---")
    c1 = Course.objects.create(
        organization=test_org,
        author=admin_user,
        title="Invalid KC Course (Zero Questions)",
        status="draft"
    )
    m1 = Module.objects.create(course=c1, title="Module 1", order=1)
    l1 = Lesson.objects.create(module=m1, title="Empty KC Lesson", type="knowledge_check", order=1)
    t1, _ = LessonBlockTree.objects.get_or_create(lesson=l1, defaults={'organization': test_org})
    b1 = LessonBlock.objects.create(organization=test_org, tree=t1, block_type="quiz", order=0)
    # Zero KCQuestion objects attached to b1

    c_view = CourseViewSet.as_view({'post': 'publish'})
    req1 = factory.post(f'/api/courses/{c1.id}/publish/')
    force_authenticate(req1, user=admin_user)
    res1 = c_view(req1, pk=c1.id)

    assert res1.status_code == 422, f"Expected 422 UNPROCESSABLE ENTITY, got {res1.status_code}: {res1.data}"
    assert "must contain at least 1 question" in str(res1.data.get('errors')), f"Error message missing: {res1.data}"
    
    c1.refresh_from_db()
    assert c1.status == 'draft', f"Expected status 'draft', got '{c1.status}'"
    v1_count = CourseVersion.objects.filter(course=c1).count()
    assert v1_count == 0, f"Expected 0 CourseVersion snapshots, found {v1_count}"
    print("  [PASS] Zero-question Knowledge Check course rejected with HTTP 422. Course remains 'draft'. 0 snapshots created.")

    # -------------------------------------------------------------------------
    # TEST 2: SCENARIO LESSON WITH NO START NODE
    # -------------------------------------------------------------------------
    print("\n--- Test 2: Scenario Lesson with Missing Start Node ---")
    c2 = Course.objects.create(
        organization=test_org,
        author=admin_user,
        title="Invalid Scenario Course (Missing Start Node)",
        status="draft"
    )
    m2 = Module.objects.create(course=c2, title="Module 1", order=1)
    l2 = Lesson.objects.create(module=m2, title="Invalid Scenario Lesson", type="scenario", order=1)
    t2, _ = LessonBlockTree.objects.get_or_create(lesson=l2, defaults={'organization': test_org})
    b2 = LessonBlock.objects.create(organization=test_org, tree=t2, block_type="scenario", order=0)
    # Create ending node only, missing start node
    ScenarioNode.objects.create(block=b2, title="Ending Node Only", content="Outcome", is_start_node=False, is_ending_node=True)

    req2 = factory.post(f'/api/courses/{c2.id}/publish/')
    force_authenticate(req2, user=admin_user)
    res2 = c_view(req2, pk=c2.id)

    assert res2.status_code == 422, f"Expected 422 UNPROCESSABLE ENTITY, got {res2.status_code}: {res2.data}"
    assert "must have exactly 1 start node" in str(res2.data.get('errors')), f"Error message missing: {res2.data}"

    c2.refresh_from_db()
    assert c2.status == 'draft', f"Expected status 'draft', got '{c2.status}'"
    v2_count = CourseVersion.objects.filter(course=c2).count()
    assert v2_count == 0, f"Expected 0 CourseVersion snapshots, found {v2_count}"
    print("  [PASS] Missing-Start-Node Scenario course rejected with HTTP 422. Course remains 'draft'. 0 snapshots created.")

    print("\n=== ALL PUBLISHING VALIDATION FAILURE TESTS PASSED 100% ===")

if __name__ == '__main__':
    run_validation_failure_checks()
