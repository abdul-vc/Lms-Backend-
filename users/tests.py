from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory, force_authenticate
from users.auth_views import MeView, ChangePasswordView
from organizations.models import Organization

User = get_user_model()

class OrgAdminProfileApiTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.org = Organization.objects.create(name='Test Org')
        self.user = User.objects.create_user(
            username='org_admin_user',
            email='orgadmin@test.com',
            password='InitialPassword123',
            organization=self.org,
            is_platform_super_admin=False
        )

    def test_me_get_profile_requires_only_authenticated_user(self):
        request = self.factory.get('/api/users/auth/me/')
        force_authenticate(request, user=self.user)
        view = MeView.as_view()
        response = view(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['email'], 'orgadmin@test.com')

    def test_me_patch_updates_own_profile(self):
        request = self.factory.patch('/api/users/auth/me/', {'first_name': 'Updated', 'last_name': 'Admin'})
        force_authenticate(request, user=self.user)
        view = MeView.as_view()
        response = view(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['first_name'], 'Updated')
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Updated')

    def test_change_password_success(self):
        data = {'current_password': 'InitialPassword123', 'new_password': 'NewSecurePassword123'}
        request = self.factory.post('/api/users/auth/change-password/', data=data)
        force_authenticate(request, user=self.user)
        view = ChangePasswordView.as_view()
        response = view(request)
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewSecurePassword123'))

    def test_change_password_incorrect_current_password(self):
        data = {'current_password': 'WrongPassword', 'new_password': 'NewSecurePassword123'}
        request = self.factory.post('/api/users/auth/change-password/', data=data)
        force_authenticate(request, user=self.user)
        view = ChangePasswordView.as_view()
        response = view(request)
        self.assertEqual(response.status_code, 400)
        self.assertIn('incorrect', response.data['detail'].lower())
