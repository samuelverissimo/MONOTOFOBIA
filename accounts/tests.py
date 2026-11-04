from axes.models import AccessAttempt
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils.crypto import get_random_string

User = get_user_model()


class RegistrationTests(TestCase):
	def setUp(self):
		cache.clear()
		self.registration_password = get_random_string(32)

	def registration_data(self, **overrides):
		data = {
			'username': 'Alice',
			'email': 'Alice@example.com',
			'password1': self.registration_password,
			'password2': self.registration_password,
		}
		data.update(overrides)
		return data

	def test_registration_creates_normalized_argon2_user(self):
		response = self.client.post(reverse('register'), self.registration_data())

		self.assertRedirects(response, reverse('login'))
		user = User.objects.get(username='alice')
		self.assertEqual(user.email, 'alice@example.com')
		self.assertTrue(user.check_password(self.registration_password))
		self.assertNotEqual(user.password, self.registration_password)
		self.assertTrue(user.password.startswith('argon2$'))

	def test_registration_rejects_weak_password(self):
		response = self.client.post(
			reverse('register'),
			self.registration_data(
				password1='123456789012',
				password2='123456789012',
			),
		)

		self.assertEqual(response.status_code, 200)
		self.assertFalse(User.objects.filter(username='alice').exists())

	def test_registration_rejects_duplicate_email_case_insensitively(self):
		User.objects.create_user(
			username='existing',
			email='existing@example.com',
			password=get_random_string(32),
		)

		response = self.client.post(
			reverse('register'),
			self.registration_data(email='EXISTING@example.com'),
		)

		self.assertContains(response, 'Já existe uma conta com este e-mail.')
		self.assertEqual(User.objects.count(), 1)

	def test_registration_rejects_password_mismatch(self):
		response = self.client.post(
			reverse('register'),
			self.registration_data(password2='Different-Password-42!'),
		)

		self.assertEqual(response.status_code, 200)
		self.assertFalse(User.objects.filter(username='alice').exists())

	def test_authenticated_user_is_redirected_from_registration(self):
		user = User.objects.create_user(username='member', password=get_random_string(32))
		self.client.force_login(user)

		response = self.client.get(reverse('register'))

		self.assertRedirects(response, reverse('home'))

	def test_invalid_login_uses_generic_message(self):
		response = self.client.post(
			reverse('login'),
			{'username': 'unknown-user', 'password': get_random_string(32)},
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Usuário ou senha inválidos.')
		self.assertNotContains(response, 'nome de usuário incorreto')


class AxesLockoutTests(TestCase):
	def setUp(self):
		AccessAttempt.objects.all().delete()

	def test_login_is_locked_after_five_failures(self):
		credentials = {'username': 'blocked-user', 'password': get_random_string(32)}
		for failure_attempt in range(5):
			response = self.client.post(reverse('login'), credentials)

		self.assertEqual(response.status_code, 429)
		self.assertContains(response, 'Acesso temporariamente bloqueado', status_code=429)
