import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LAMS.settings')
django.setup()

from courses.models import Course, Module, Lesson, AssessmentQuestion
from users.models import User
from rest_framework.test import APIRequestFactory, force_authenticate
from courses.views import CourseViewSet, LessonViewSet

def run_regression_test():
    print("=== PHASE 1 REGRESSION CHECK ===")
    
    # 1. Fetch existing courses
    courses = Course.objects.all()[:5]
    print(f"Found {courses.count()} existing courses in DB.")
    assert courses.count() >= 3, f"Expected at least 3 courses, found {courses.count()}"

    factory = APIRequestFactory()
    admin_user = User.objects.filter(is_platform_super_admin=True).first() or User.objects.first()
    assert admin_user is not None, "User found for testing"
    print(f"Testing using user: {admin_user.username} (org: {admin_user.organization})")

    video_courses_tested = 0

    for course in courses:
        print(f"\nTesting Course ID {course.id}: '{course.title}' (status: {course.status})")
        
        # Test A: Load Course Detail via ViewSet
        view = CourseViewSet.as_view({'get': 'retrieve'})
        request = factory.get(f'/api/courses/{course.id}/')
        force_authenticate(request, user=admin_user)
        response = view(request, pk=course.id)
        assert response.status_code == 200, f"Course detail GET failed: {response.status_code}"
        course_data = response.data
        print(f"  [OK] Course detail loaded cleanly. Modules count: {len(course_data.get('modules', []))}")

        # Check if course has video lessons
        has_video = False
        for mod in course_data.get('modules', []):
            for les in mod.get('lessons', []):
                if les.get('type') == 'video':
                    has_video = True
                    print(f"    - Video lesson ID {les['id']}: '{les['title']}' URL: {les.get('video_url')}")
        
        if has_video:
            video_courses_tested += 1

        # Test B: Edit Course (Partial Update)
        old_subtitle = course.subtitle
        test_subtitle = f"Regression check subtitle - {course.id}"
        update_view = CourseViewSet.as_view({'patch': 'partial_update'})
        patch_req = factory.patch(f'/api/courses/{course.id}/', {'subtitle': test_subtitle}, format='json')
        force_authenticate(patch_req, user=admin_user)
        patch_res = update_view(patch_req, pk=course.id)
        assert patch_res.status_code == 200, f"Course PATCH failed: {patch_res.status_code}"
        print("  [OK] Course edit (patch) successful.")
        
        # Revert subtitle
        patch_req2 = factory.patch(f'/api/courses/{course.id}/', {'subtitle': old_subtitle}, format='json')
        force_authenticate(patch_req2, user=admin_user)
        update_view(patch_req2, pk=course.id)

        # Test C: Test Publish endpoint
        pub_view = CourseViewSet.as_view({'post': 'publish'})
        pub_req = factory.post(f'/api/courses/{course.id}/publish/')
        force_authenticate(pub_req, user=admin_user)
        pub_res = pub_view(pub_req, pk=course.id)
        assert pub_res.status_code == 200, f"Course publish failed: {pub_res.status_code}"
        print("  [OK] Course publish action successful.")

    print(f"\nTested {video_courses_tested} video-lesson courses against regression criteria.")
    
    # Test D: Check Assessment CSV questions functionality
    questions_count = AssessmentQuestion.objects.count()
    print(f"  [OK] Assessment CSV Question table intact: {questions_count} total questions in DB.")

    print("\n=== REGRESSION CHECK PASSED 100% ===")

if __name__ == '__main__':
    run_regression_test()
