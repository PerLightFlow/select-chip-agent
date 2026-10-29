from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TransactionTestCase
from core.models import AuditEvent


class RegistrationTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.client = Client(enforce_csrf_checks=True)
        self.client.get('/api/session/')
        self.password = 'Cobalt-river!7296'

    def register(self, **overrides):
        body = {'username': 'new-researcher', 'password': self.password,
                'confirm_password': self.password, **overrides}
        return self.client.post('/api/register/', body, content_type='application/json',
                                HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value)

    def test_registration_logs_in_active_ordinary_user_and_allows_workspace(self):
        response = self.register(is_staff=True, is_superuser=True, is_active=False)
        self.assertEqual(response.status_code, 201)
        user = get_user_model().objects.get(username='new-researcher')
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff or user.is_superuser)
        self.assertTrue(user.check_password(self.password))
        self.assertNotEqual(user.password, self.password)
        self.assertTrue(self.client.get('/api/session/').json()['authenticated'])
        for path in ['conversations', 'projects', 'documents']:
            self.assertEqual(self.client.get(f'/api/assistant/{path}/').status_code, 200)
        self.assertEqual(self.client.get('/admin/auth/user/add/').status_code, 302)
        self.assertTrue(AuditEvent.objects.filter(actor=user, action='register_account').exists())
        self.assertNotIn(self.password, response.content.decode())

    def test_duplicate_username_does_not_change_existing_account(self):
        user = get_user_model().objects.create_user('new-researcher', password='Original-river!7296')
        response = self.register()
        self.assertEqual(response.status_code, 400)
        self.assertIn('已存在', response.json()['error'])
        user.refresh_from_db()
        self.assertTrue(user.check_password('Original-river!7296'))
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertFalse(self.client.get('/api/session/').json()['authenticated'])

    def test_invalid_password_confirmation_and_username_create_no_account(self):
        for data in [{'password': '12345678', 'confirm_password': '12345678'},
                     {'confirm_password': 'Different!8273'}, {'username': 'bad name'},
                     {'username': ''}, {'username': 'x' * 151}, {'password': ['not a string']},
                     {'password': 'x' * 1001}, {'username': None}]:
            with self.subTest(data=list(data)):
                self.assertEqual(self.register(**data).status_code, 400)
        self.assertFalse(get_user_model().objects.exists())

    def test_csrf_method_and_malformed_json_are_rejected(self):
        self.assertEqual(self.client.get('/api/register/').status_code, 405)
        self.assertEqual(self.client.post('/api/register/', {}, content_type='application/json').status_code, 403)
        for body in ['[1]', '{invalid']:
            response = self.client.post('/api/register/', body, content_type='application/json',
                                        HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value)
            self.assertEqual(response.status_code, 400)
        self.assertFalse(get_user_model().objects.exists())

    def test_logged_in_user_cannot_replace_session_by_registering(self):
        user = get_user_model().objects.create_user('existing', password=self.password)
        self.client.force_login(user)
        self.assertEqual(self.register().status_code, 409)
        self.assertEqual(self.client.get('/api/session/').json()['username'], 'existing')
        self.assertFalse(get_user_model().objects.filter(username='new-researcher').exists())

    @patch('core.views.RegistrationThrottle.rate', '1/minute', create=True)
    def test_registration_attempts_are_throttled(self):
        self.assertEqual(self.register(confirm_password='wrong').status_code, 400)
        self.assertEqual(self.register().status_code, 429)
        self.assertFalse(get_user_model().objects.exists())
