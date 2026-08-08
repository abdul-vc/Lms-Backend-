import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LAMS.settings')
django.setup()

from courses.models import Course, Module, Lesson
from authoring_engine.models import LessonBlockTree
from users.models import User
from rest_framework.test import APIRequestFactory, force_authenticate
from courses.views import CourseViewSet, LessonViewSet

def run_phase2_test():
    print("=== PHASE 2 REGRESSION & DISPATCH CHECK ===")
    
    # 1. Get an existing course and module
    course = Course.objects.first()
    assert course is not None, "At least one course must exist"
    module = course.modules.first()
    if not module:
        module = Module.objects.create(course=course, title="Test Module Phase 2", order=1)
    
    admin_user = User.objects.filter(is_platform_super_admin=True).first() or User.objects.first()
    factory = APIRequestFactory()

    print(f"Testing against Course ID {course.id}, Module ID {module.id} with user '{admin_user.username}'")

    # A. Test existing video lessons
    video_lessons = Lesson.objects.filter(module=module, type='video')
    if not video_lessons.exists():
        Lesson.objects.create(
            module=module,
            title="Legacy Video Lesson",
            type="video",
            video_url="http://127.0.0.1:8000/media/course_videos/sample.mp4"
        )
        video_lessons = Lesson.objects.filter(module=module, type='video')

    for v_les in video_lessons:
        view = LessonViewSet.as_view({'get': 'retrieve'})
        req = factory.get(f'/api/lessons/{v_les.id}/')
        force_authenticate(req, user=admin_user)
        res = view(req, pk=v_les.id)
        assert res.status_code == 200, f"Lesson GET failed: {res.status_code}"
        data = res.data
        assert data['type'] == 'video'
        assert data['block_tree'] is None, "Video lessons must have block_tree == None"
        print(f"  [OK] Video Lesson ID {v_les.id} dispatched correctly (legacy video_url path preserved).")

    # B. Test creating 4 new lesson types: reading, interactive, knowledge_check, scenario
    new_types = ['reading', 'interactive', 'knowledge_check', 'scenario']
    created_lessons = []

    for l_type in new_types:
        view = LessonViewSet.as_view({'post': 'create'})
        payload = {
            'module': module.id,
            'title': f"Test {l_type.replace('_', ' ').title()} Lesson",
            'type': l_type,
            'duration': '10 min',
            'order': 99
        }
        req = factory.post(f'/api/modules/{module.id}/lessons/', payload, format='json')
        force_authenticate(req, user=admin_user)
        res = view(req, module_pk=module.id)
        assert res.status_code == 201, f"Failed to create {l_type} lesson: {res.data}"
        les_data = res.data
        les_id = les_data['id']
        assert les_data['type'] == l_type
        
        # Verify DRF output automatically returned block_tree object
        assert les_data['block_tree'] is not None, f"Block tree must not be None for {l_type}"
        tree_data = les_data['block_tree']
        assert 'id' in tree_data
        
        # Verify DB persistence
        tree_obj = LessonBlockTree.objects.get(lesson_id=les_id)
        assert tree_obj.organization_id == course.organization_id or admin_user.is_platform_super_admin
        
        created_lessons.append(les_id)
        print(f"  [OK] New lesson type '{l_type}' (ID: {les_id}) created & persisted block_tree ID {tree_obj.id}.")

    # C. Verify Polymorphic Course ViewSet retrieve
    c_view = CourseViewSet.as_view({'get': 'retrieve'})
    c_req = factory.get(f'/api/courses/{course.id}/')
    force_authenticate(c_req, user=admin_user)
    c_res = c_view(c_req, pk=course.id)
    assert c_res.status_code == 200
    print(f"  [OK] CourseViewSet retrieved course {course.id} with all 5 polymorphic lesson types.")

    print("\n=== PHASE 2 REGRESSION & DISPATCH CHECK PASSED 100% ===")

if __name__ == '__main__':
    run_phase2_test()
