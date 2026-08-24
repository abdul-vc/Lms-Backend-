from django.test import TestCase
from rest_framework.test import APIClient
from django.utils import timezone
from users.models import User
from organizations.models import Organization, Department, Role
from courses.models import Course, Module, Lesson, AssessmentQuestion, AssessmentAttempt

class OrgAdminAssessmentActivityTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org1 = Organization.objects.create(name="Tenant One", sub_domain="tenant1")
        self.org2 = Organization.objects.create(name="Tenant Two", sub_domain="tenant2")

        self.dept1 = Department.objects.create(name="Engineering", organization=self.org1)
        self.role1 = Role.objects.create(name="Developer", organization=self.org1, is_admin_role=False)
        self.admin_role1 = Role.objects.create(name="Org Admin", organization=self.org1, is_admin_role=True, can_view_reports=True)

        self.admin1 = User.objects.create_user(
            username="admin1", email="admin1@t1.com", password="pass",
            organization=self.org1, role=self.admin_role1
        )
        self.user1 = User.objects.create_user(
            username="learner1", email="learner1@t1.com", password="pass",
            first_name="Alice", last_name="Smith",
            organization=self.org1, department=self.dept1, role=self.role1
        )

        self.course1 = Course.objects.create(title="Python 101", organization=self.org1)
        self.module1 = Module.objects.create(course=self.course1, title="Module 1", order=1)
        self.lesson1 = Lesson.objects.create(module=self.module1, title="Variables", type="assessment", order=1)

        self.q1 = AssessmentQuestion.objects.create(
            course=self.course1,
            lesson=self.lesson1,
            question_text="What is a variable?",
            option_a="Container", option_b="Fruit", option_c="Car", option_d="Animal",
            correct_option="A"
        )
        self.q2 = AssessmentQuestion.objects.create(
            course=self.course1,
            lesson=self.lesson1,
            question_text="2 + 2 = ?",
            option_a="3", option_b="4", option_c="5", option_d="6",
            correct_option="B"
        )

        # Attempt 1: Failed
        self.attempt1 = AssessmentAttempt.objects.create(
            course=self.course1, lesson=self.lesson1, user=self.user1,
            started_at=timezone.now(), submitted_at=timezone.now(),
            score_percent=50, passed=False,
            question_ids=[self.q1.id, self.q2.id],
            answers={str(self.q1.id): "A", str(self.q2.id): "A"}
        )

        # Attempt 2: Passed
        self.attempt2 = AssessmentAttempt.objects.create(
            course=self.course1, lesson=self.lesson1, user=self.user1,
            started_at=timezone.now(), submitted_at=timezone.now(),
            score_percent=100, passed=True,
            question_ids=[self.q1.id, self.q2.id],
            answers={str(self.q1.id): "A", str(self.q2.id): "B"}
        )

        # Org 2 User & Attempt (Tenant Isolation Check)
        self.user2 = User.objects.create_user(
            username="learner2", email="learner2@t2.com", password="pass",
            organization=self.org2
        )
        self.course2 = Course.objects.create(title="Java 101", organization=self.org2)
        self.module2 = Module.objects.create(course=self.course2, title="Java Mod 1", order=1)
        self.lesson2 = Lesson.objects.create(module=self.module2, title="Syntax", type="assessment", order=1)
        self.attempt_org2 = AssessmentAttempt.objects.create(
            course=self.course2, lesson=self.lesson2, user=self.user2,
            started_at=timezone.now(), submitted_at=timezone.now(),
            score_percent=100, passed=True
        )

    def test_assessment_activity_tenant_scoping(self):
        self.client.force_authenticate(user=self.admin1)
        res = self.client.get('/api/org-admin/assessment-activity/')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        results = data['results']
        
        # Org1 should only see its 2 attempts, NOT Org2's attempt
        self.assertEqual(len(results), 2)
        attempt_ids = [r['id'] for r in results]
        self.assertIn(self.attempt1.id, attempt_ids)
        self.assertIn(self.attempt2.id, attempt_ids)
        self.assertNotIn(self.attempt_org2.id, attempt_ids)

        # Verify attempt numbering
        # Results are ordered by -started_at so attempt2 is first, attempt1 second
        row_att2 = next(r for r in results if r['id'] == self.attempt2.id)
        row_att1 = next(r for r in results if r['id'] == self.attempt1.id)
        self.assertEqual(row_att1['attempt_number'], 1)
        self.assertEqual(row_att2['attempt_number'], 2)
        self.assertEqual(row_att1['total_attempts'], 2)
        self.assertEqual(row_att2['total_attempts'], 2)

        # Verify department & role mapping
        self.assertEqual(row_att1['department_name'], "Engineering")
        self.assertEqual(row_att1['role_name'], "Developer")

        # Verify question counts
        self.assertEqual(row_att1['correct_answers'], 1)
        self.assertEqual(row_att1['wrong_answers'], 1)
        self.assertEqual(row_att2['correct_answers'], 2)
        self.assertEqual(row_att2['wrong_answers'], 0)

    def test_attempt_detail_endpoint(self):
        self.client.force_authenticate(user=self.admin1)
        res = self.client.get(f'/api/org-admin/assessment-activity/{self.attempt2.id}/')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data['id'], self.attempt2.id)
        self.assertEqual(data['user_name'], "Alice Smith")
        self.assertEqual(data['score_percent'], 100)
        self.assertEqual(data['result'], "Passed")
        self.assertEqual(len(data['questions']), 2)

        # Detail on Cross-tenant attempt must 404
        cross_res = self.client.get(f'/api/org-admin/assessment-activity/{self.attempt_org2.id}/')
        self.assertEqual(cross_res.status_code, 404)

    def test_access_control_toggle_hides_and_blocks_assessment_activity(self):
        from master_setup.models import Feature, OrganizationFeatureAccess, Workspace, NavItem
        
        # Ensure feature and navitem exist
        feat, _ = Feature.objects.get_or_create(key='assessment_activity', defaults={'name': 'Assessment Activity', 'category': 'reporting'})
        admin_ws, _ = Workspace.objects.get_or_create(key='admin', defaults={'label': 'Administration'})
        NavItem.objects.get_or_create(workspace=admin_ws, key='assessment_activity', defaults={'label': 'Assessment Activity', 'icon': 'CheckSquare', 'route': '/org-admin/assessment-activity', 'feature': feat, 'required_permission': 'can_view_reports'})

        # 1. When enabled: Sidebar includes item, endpoint returns 200
        org_access, _ = OrganizationFeatureAccess.objects.get_or_create(organization=self.org1, feature=feat)
        org_access.enabled = True
        org_access.save()

        self.client.force_authenticate(user=self.admin1)
        ws_res = self.client.get('/api/me/workspaces/')
        self.assertEqual(ws_res.status_code, 200)
        nav_keys = [item['key'] for item in ws_res.json()['workspaces'][0]['nav_items']]
        self.assertIn('assessment_activity', nav_keys)

        api_res = self.client.get('/api/org-admin/assessment-activity/')
        self.assertEqual(api_res.status_code, 200)

        # 2. When disabled for Org1: Sidebar omits item, endpoint returns 403
        org_access.enabled = False
        org_access.save()

        ws_res2 = self.client.get('/api/me/workspaces/')
        self.assertEqual(ws_res2.status_code, 200)
        nav_keys2 = [item['key'] for item in ws_res2.json()['workspaces'][0]['nav_items']]
        self.assertNotIn('assessment_activity', nav_keys2)

        api_res2 = self.client.get('/api/org-admin/assessment-activity/')
        self.assertEqual(api_res2.status_code, 403)

        # 3. Org2 toggle does NOT affect Org1
        org2_access, _ = OrganizationFeatureAccess.objects.get_or_create(organization=self.org2, feature=feat)
        org2_access.enabled = True
        org2_access.save()

        # Org1 is still disabled
        ws_res3 = self.client.get('/api/me/workspaces/')
        nav_keys3 = [item['key'] for item in ws_res3.json()['workspaces'][0]['nav_items']]
        self.assertNotIn('assessment_activity', nav_keys3)
