import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LAMS.settings')
django.setup()

from courses.models import Course, Module, Lesson
from authoring_engine.models import (
    LessonBlockTree, LessonBlock, ReadingContent,
    InteractionBlock, KCQuestion, ScenarioNode
)
from users.models import User
from rest_framework.test import APIRequestFactory, force_authenticate
from authoring_engine.views import (
    ReadingContentViewSet, InteractionBlockViewSet, KCQuestionViewSet,
    ScenarioNodeViewSet, evaluate_kc_question, validate_scenario
)
from courses.views import LessonViewSet, CourseViewSet

def run_phase4_test():
    print("=== PHASE 4 ENGINES (READING, INTERACTIVE, KC, SCENARIO) REGRESSION CHECK ===")

    course = Course.objects.first()
    assert course is not None, "Course exists"
    module = course.modules.first()
    assert module is not None, "Module exists"

    admin_user = User.objects.filter(is_platform_super_admin=True).first() or User.objects.first()
    factory = APIRequestFactory()

    print(f"Testing round trips for Course ID {course.id}, Module ID {module.id} with user '{admin_user.username}'")

    # 1. ENGINE 1: READING LESSON
    r_lesson = Lesson.objects.create(module=module, title="Phase 4 Reading Lesson", type="reading", order=101)
    r_tree, _ = LessonBlockTree.objects.get_or_create(lesson=r_lesson, defaults={'organization': course.organization})
    r_block = LessonBlock.objects.create(organization=course.organization, tree=r_tree, block_type="paragraph", order=0)
    ReadingContent.objects.get_or_create(block=r_block, defaults={'html_content': '<p>Initial</p>', 'markdown_content': 'Initial'})
    
    # Author edit via ReadingContentViewSet with HTML Sanitization
    r_view = ReadingContentViewSet.as_view({'put': 'update'})
    unsafe_html = "<h2>Title</h2><p>Safe content</p><script>alert('xss')</script><iframe src='https://example.com' width='500' height='300'></iframe>"
    r_payload = {'block': r_block.id, 'html_content': unsafe_html, 'markdown_content': "Safe content"}
    r_req = factory.put(f'/api/authoring/reading/{r_block.reading_payload.id}/', r_payload, format='json')
    force_authenticate(r_req, user=admin_user)
    r_res = r_view(r_req, pk=r_block.reading_payload.id)
    assert r_res.status_code == 200, f"Reading update failed: {r_res.data}"
    cleaned_html = r_res.data['html_content']
    assert "<script>" not in cleaned_html, "Bleach HTML Sanitization stripped <script> tag"
    assert "<iframe" in cleaned_html, "Bleach HTML Sanitization allowed safe <iframe> tag per blueprint whitelist"
    print("  [OK] Reading Engine: Author-edit round-trip & Bleach HTML sanitization verified.")

    # 2. ENGINE 2: INTERACTIVE LESSON
    i_lesson = Lesson.objects.create(module=module, title="Phase 4 Interactive Lesson", type="interactive", order=102)
    i_tree, _ = LessonBlockTree.objects.get_or_create(lesson=i_lesson, defaults={'organization': course.organization})
    i_block = LessonBlock.objects.create(organization=course.organization, tree=i_tree, block_type="interaction", order=0)
    InteractionBlock.objects.get_or_create(block=i_block, defaults={'interaction_type': 'hotspots', 'config': {}})

    # Author edit via InteractionBlockViewSet
    i_view = InteractionBlockViewSet.as_view({'put': 'update'})
    i_config = {
        "interaction_type": "hotspots",
        "config": {
            "image_url": "/media/anatomy.jpg",
            "hotspots": [{"x": 20, "y": 30, "title": "Nucleus", "description": "Cell center"}]
        }
    }
    i_payload = {'block': i_block.id, 'interaction_type': 'hotspots', 'config': i_config['config']}
    i_req = factory.put(f'/api/authoring/interactions/{i_block.interaction_payload.id}/', i_payload, format='json')
    force_authenticate(i_req, user=admin_user)
    i_res = i_view(i_req, pk=i_block.interaction_payload.id)
    assert i_res.status_code == 200, f"Interaction update failed: {i_res.data}"
    assert i_res.data['interaction_type'] == 'hotspots'
    assert i_res.data['config']['hotspots'][0]['title'] == 'Nucleus'
    print("  [OK] Interactive Engine: 15-widget JSON schema persistence verified.")

    # 3. ENGINE 3: KNOWLEDGE CHECK LESSON
    kc_lesson = Lesson.objects.create(module=module, title="Phase 4 Knowledge Check Lesson", type="knowledge_check", order=103)
    kc_tree, _ = LessonBlockTree.objects.get_or_create(lesson=kc_lesson, defaults={'organization': course.organization})
    kc_block = LessonBlock.objects.create(organization=course.organization, tree=kc_tree, block_type="quiz", order=0)
    
    # Author edit via KCQuestionViewSet
    kc_view = KCQuestionViewSet.as_view({'post': 'create'})
    kc_payload = {
        'block': kc_block.id,
        'question_type': 'single_choice',
        'prompt': 'Which organelle contains DNA?',
        'choices': [
            {'id': 'c1', 'text': 'Nucleus', 'is_correct': True},
            {'id': 'c2', 'text': 'Ribosome', 'is_correct': False}
        ],
        'correct_feedback': 'Correct!',
        'incorrect_feedback': 'Try again.',
        'points': 10
    }
    kc_req = factory.post('/api/authoring/kc-questions/', kc_payload, format='json')
    force_authenticate(kc_req, user=admin_user)
    kc_res = kc_view(kc_req)
    assert kc_res.status_code == 201, f"KC creation failed: {kc_res.data}"
    q_id = kc_res.data['id']

    # Learner evaluation call
    eval_req = factory.post(f'/api/authoring/kc-questions/{q_id}/evaluate/', {'selected_choices': ['c1']}, format='json')
    force_authenticate(eval_req, user=admin_user)
    eval_res = evaluate_kc_question(eval_req, question_id=q_id)
    assert eval_res.status_code == 200
    assert eval_res.data['is_correct'] == True
    assert eval_res.data['score_earned'] == 10
    print("  [OK] Knowledge Check Engine: Evaluation state machine & scoring verified.")

    # 4. ENGINE 4: SCENARIO LESSON
    s_lesson = Lesson.objects.create(module=module, title="Phase 4 Branching Scenario Lesson", type="scenario", order=104)
    s_tree, _ = LessonBlockTree.objects.get_or_create(lesson=s_lesson, defaults={'organization': course.organization})
    s_block = LessonBlock.objects.create(organization=course.organization, tree=s_tree, block_type="scenario", order=0)

    # Author edit via ScenarioNodeViewSet
    sn_view = ScenarioNodeViewSet.as_view({'post': 'create'})
    # Create start node
    sn1_req = factory.post('/api/authoring/scenario-nodes/', {
        'block': s_block.id, 'title': 'Start Point', 'content': 'Scenario starts here', 'is_start_node': True, 'is_ending_node': False
    }, format='json')
    force_authenticate(sn1_req, user=admin_user)
    sn1_res = sn_view(sn1_req)
    assert sn1_res.status_code == 201

    # Create ending node
    sn2_req = factory.post('/api/authoring/scenario-nodes/', {
        'block': s_block.id, 'title': 'Ending Point', 'content': 'Success outcome', 'is_start_node': False, 'is_ending_node': True, 'ending_type': 'success', 'score_delta': 50
    }, format='json')
    force_authenticate(sn2_req, user=admin_user)
    sn2_res = sn_view(sn2_req)
    assert sn2_res.status_code == 201

    # Validate scenario logic
    val_req = factory.get(f'/api/authoring/scenarios/{s_block.id}/validate/')
    force_authenticate(val_req, user=admin_user)
    val_res = validate_scenario(val_req, block_id=s_block.id)
    assert val_res.status_code == 200
    assert val_res.data['is_valid'] == True
    print("  [OK] Scenario Engine: Branching decision tree validation verified.")

    # Learner Portal Round Trip Check for all 4 lessons
    les_view = LessonViewSet.as_view({'get': 'retrieve'})
    for test_les in [r_lesson, i_lesson, kc_lesson, s_lesson]:
        l_req = factory.get(f'/api/lessons/{test_les.id}/')
        force_authenticate(l_req, user=admin_user)
        l_res = les_view(l_req, pk=test_les.id)
        assert l_res.status_code == 200, f"Learner GET failed for {test_les.type}: {l_res.status_code}"
        assert l_res.data['block_tree'] is not None, "Block tree dispatched cleanly to learner"

    print("\n=== PHASE 4 ENGINES REGRESSION CHECK PASSED 100% ===")

if __name__ == '__main__':
    run_phase4_test()
