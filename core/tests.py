from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.crypto import get_random_string

User = get_user_model()


class AuthenticationSecurityTests(TestCase):
	def test_home_requires_login(self):
		response = self.client.get(reverse('home'))

		self.assertRedirects(response, '/accounts/login/?next=/')

	def test_logout_requires_post(self):
		password = get_random_string(32)
		user = User.objects.create_user(
			username='member',
			password=password,
		)
		self.client.force_login(user)

		response = self.client.get(reverse('logout'))

		self.assertEqual(response.status_code, 405)
		self.assertEqual(self.client.get(reverse('home')).status_code, 200)

		response = self.client.post(reverse('logout'))

		self.assertRedirects(response, reverse('login'))
		self.assertRedirects(self.client.get(reverse('home')), '/accounts/login/?next=/')

	def test_external_next_is_not_followed(self):
		password = get_random_string(32)
		user = User.objects.create_user(
			username='member',
			password=password,
		)

		response = self.client.post(
			reverse('login'),
			{
				'username': user.username,
				'password': password,
				'next': '//evil.com',
			},
		)

		self.assertRedirects(response, reverse('home'))
		self.assertNotIn('evil.com', response.url)

	def test_security_headers_are_present(self):
		response = self.client.get(reverse('login'))

		self.assertEqual(response.headers['X-Frame-Options'], 'DENY')
		self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
		policy = response.headers['Content-Security-Policy']
		self.assertIn("default-src 'self'", policy)
		self.assertNotIn('unsafe-inline', policy)

	def test_password_change_requires_current_password(self):
		current_password = get_random_string(32)
		new_password = get_random_string(32)
		user = User.objects.create_user(
			username='member',
			password=current_password,
		)
		self.client.force_login(user)
		change_url = reverse('password_change')

		response = self.client.post(
			change_url,
			{
				'old_password': get_random_string(32),
				'new_password1': new_password,
				'new_password2': new_password,
			},
		)
		self.assertEqual(response.status_code, 200)
		user.refresh_from_db()
		self.assertTrue(user.check_password(current_password))

		response = self.client.post(
			change_url,
			{
				'old_password': current_password,
				'new_password1': new_password,
				'new_password2': new_password,
			},
		)
		self.assertRedirects(response, reverse('password_change_done'))
		user.refresh_from_db()
		self.assertTrue(user.check_password(new_password))
