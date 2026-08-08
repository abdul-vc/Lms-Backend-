import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LAMS.settings')
django.setup()

from courses.models import Course, Module, Lesson
from authoring_engine.models import LessonBlockTree, LessonBlock, ReadingContent
from users.models import User
from rest_framework.test import APIRequestFactory, force_authenticate
from authoring_engine.views import LessonBlockViewSet, reorder_blocks
from courses.views import CourseViewSet, LessonViewSet

def run_phase3_test():
    print("=== PHASE 3 CONTENT BUILDER (BLOCK EDITOR) REGRESSION CHECK ===")

    # 1. Fetch test course and non-video lesson
    course = Course.objects.first()
    assert course is not None, "Course exists"
    module = course.modules.first()
    assert module is not None, "Module exists"

    admin_user = User.objects.filter(is_platform_super_admin=True).first() or User.objects.first()
    factory = APIRequestFactory()

    # Get or create a reading lesson
    lesson = Lesson.objects.filter(module=module, type='reading').first()
    if not lesson:
        lesson = Lesson.objects.create(module=module, title="Block Builder Test Reading Lesson", type="reading", order=50)

    # Get block tree
    tree, _ = LessonBlockTree.objects.get_or_create(lesson=lesson, defaults={'organization': course.organization})
    print(f"Testing against Tree ID {tree.id} for Lesson ID {lesson.id}")

    # A. Test Creating Blocks of Various Types
    block_types_to_create = ['heading', 'paragraph', 'callout', 'quiz', 'scenario', 'interaction']
    created_block_ids = []

    block_view = LessonBlockViewSet.as_view({'post': 'create'})

    for b_type in block_types_to_create:
        payload = {
            'tree': tree.id,
            'block_type': b_type,
            'order': len(created_block_ids),
            'settings': {'align': 'left', 'width': 'full'}
        }
        req = factory.post('/api/authoring/blocks/', payload, format='json')
        force_authenticate(req, user=admin_user)
        res = block_view(req)
        assert res.status_code == 201, f"Block creation failed for {b_type}: {res.data}"
        b_data = res.data
        b_id = b_data['id']
        created_block_ids.append(b_id)
        print(f"  [OK] Created block type '{b_type}' (UUID: {b_id}).")

    # Refresh tree from DB
    tree.refresh_from_db()
    assert len(tree.root_block_ids) >= len(block_types_to_create), "Root block IDs auto-updated on tree"
    print(f"  [OK] Tree root_block_ids contains {len(tree.root_block_ids)} entries.")

    # B. Test Updating Block Settings
    target_block_id = created_block_ids[0]
    update_view = LessonBlockViewSet.as_view({'patch': 'partial_update'})
    patch_req = factory.patch(f'/api/authoring/blocks/{target_block_id}/', {'settings': {'align': 'center', 'width': 'constrained'}}, format='json')
    force_authenticate(patch_req, user=admin_user)
    patch_res = update_view(patch_req, pk=target_block_id)
    assert patch_res.status_code == 200, f"Block patch failed: {patch_res.data}"
    assert patch_res.data['settings']['align'] == 'center'
    print("  [OK] Block settings update (PATCH) successful.")

    # C. Test Block Reordering Endpoint
    # Reverse the order of created blocks
    reversed_order = list(reversed(created_block_ids))
    reorder_req = factory.post(f'/api/authoring/trees/{tree.id}/reorder/', {'parent_block_id': None, 'ordered_block_ids': reversed_order}, format='json')
    force_authenticate(reorder_req, user=admin_user)
    reorder_res = reorder_blocks(reorder_req, tree_id=tree.id)
    assert reorder_res.status_code == 200, f"Reorder failed: {reorder_res.data}"
    tree.refresh_from_db()
    assert tree.root_block_ids == reversed_order, "Reordered block IDs match updated list"
    print("  [OK] Block reorder endpoint (POST /api/authoring/trees/{id}/reorder/) verified.")

    # D. Test Deleting a Block
    delete_block_id = created_block_ids.pop()
    del_view = LessonBlockViewSet.as_view({'delete': 'destroy'})
    del_req = factory.delete(f'/api/authoring/blocks/{delete_block_id}/')
    force_authenticate(del_req, user=admin_user)
    del_res = del_view(del_req, pk=delete_block_id)
    assert del_res.status_code == 204, f"Block deletion failed: {del_res.status_code}"
    tree.refresh_from_db()
    assert delete_block_id not in tree.root_block_ids, "Deleted block removed from root_block_ids"
    print(f"  [OK] Block deletion (DELETE /api/authoring/blocks/{delete_block_id}/) verified.")

    # E. Check existing Course Builder Navigation
    c_view = CourseViewSet.as_view({'get': 'retrieve'})
    c_req = factory.get(f'/api/courses/{course.id}/')
    force_authenticate(c_req, user=admin_user)
    c_res = c_view(c_req, pk=course.id)
    assert c_res.status_code == 200
    print("  [OK] Course builder tree navigation & CourseViewSet unaffected.")

    print("\n=== PHASE 3 REGRESSION CHECK PASSED 100% ===")

if __name__ == '__main__':
    run_phase3_test()
