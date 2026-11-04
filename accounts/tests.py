from axes.models import AccessAttempt
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import IntegrityError, transaction
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

	def test_registration_rejects_reserved_usernames_with_variations(self):
		for reserved in ('SAMUKAMESTRE', 'samu ka mestre', 'a.d.m.i.n', 'ROOT'):
			with self.subTest(username=reserved):
				response = self.client.post(
					reverse('register'),
					self.registration_data(username=reserved),
				)
				self.assertContains(response, 'Este nome de usuário não está disponível.')
		self.assertEqual(User.objects.count(), 0)

	def test_registration_normalizes_case_insensitive_username(self):
		User.objects.create_user(username='jogador', password=get_random_string(32))
		response = self.client.post(
			reverse('register'),
			self.registration_data(username='JOGADOR'),
		)
		self.assertContains(response, 'Este nome de usuário já está em uso.')
		self.assertEqual(User.objects.count(), 1)

	def test_database_enforces_case_insensitive_username_uniqueness(self):
		User.objects.create_user(username='NomeUnico', password=get_random_string(32))
		with self.assertRaises(IntegrityError):
			with transaction.atomic():
				User.objects.create_user(username='nomeunico', password=get_random_string(32))

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


class AccountProfileTests(TestCase):
	def setUp(self):
		cache.clear()
		self.password = get_random_string(32)
		self.user = User.objects.create_user(
			username='profile-user',
			email='profile@example.com',
			password=self.password,
		)
		self.client.force_login(self.user)

	def test_profile_updates_name_username_and_email_without_granting_role(self):
		response = self.client.post(reverse('account_profile'), {
			'acao': 'perfil',
			'nome': 'Samara',
			'username': 'profile-user-new',
			'email': 'new@example.com',
			'tipo_conta': 'mestre',
		})

		self.assertRedirects(response, reverse('account_profile'))
		self.user.refresh_from_db()
		self.assertEqual(
			(self.user.first_name, self.user.username, self.user.email),
			('Samara', 'profile-user-new', 'new@example.com'),
		)
		self.assertFalse(self.user.is_superuser)
		self.assertFalse(self.user.is_staff)

	def test_profile_can_change_password_without_ending_session(self):
		new_password = get_random_string(32)
		response = self.client.post(reverse('account_profile'), {
			'acao': 'senha',
			'old_password': self.password,
			'new_password1': new_password,
			'new_password2': new_password,
		})

		self.assertRedirects(response, reverse('account_profile'))
		self.user.refresh_from_db()
		self.assertTrue(self.user.check_password(new_password))
		self.assertEqual(self.client.get(reverse('account_profile')).status_code, 200)

	def test_last_superuser_cannot_demote_and_player_cannot_promote(self):
		master = User.objects.create_superuser(
			username='last-master', email='last-master@example.com',
			password=get_random_string(32),
		)
		self.client.force_login(master)
		response = self.client.post(reverse('account_profile'), {
			'acao': 'perfil',
			'nome': '',
			'username': master.username,
			'email': master.email,
			'tipo_conta': 'jogador',
		})
		self.assertEqual(response.status_code, 400)
		master.refresh_from_db()
		self.assertTrue(master.is_superuser)

		self.client.force_login(self.user)
		response = self.client.post(reverse('account_profile'), {
			'acao': 'perfil',
			'nome': '',
			'username': self.user.username,
			'email': self.user.email,
			'tipo_conta': 'mestre',
		})
		self.assertEqual(response.status_code, 302)
		self.user.refresh_from_db()
		self.assertFalse(self.user.is_superuser)

	def test_master_can_demote_self_only_when_another_master_remains(self):
		master = User.objects.create_superuser(
			username='first-master', email='first-master@example.com',
			password=get_random_string(32),
		)
		User.objects.create_superuser(
			username='second-master', email='second-master@example.com',
			password=get_random_string(32),
		)
		self.client.force_login(master)
		response = self.client.post(reverse('account_profile'), {
			'acao': 'perfil',
			'nome': '',
			'username': master.username,
			'email': master.email,
			'tipo_conta': 'jogador',
		})

		self.assertRedirects(response, reverse('account_profile'))
		master.refresh_from_db()
		self.assertFalse(master.is_superuser)
		self.assertEqual(User.objects.filter(is_superuser=True).count(), 1)


class AxesLockoutTests(TestCase):
	def setUp(self):
		AccessAttempt.objects.all().delete()

	def test_login_is_locked_after_five_failures(self):
		credentials = {'username': 'blocked-user', 'password': get_random_string(32)}
		for failure_attempt in range(5):
			response = self.client.post(reverse('login'), credentials)

		self.assertEqual(response.status_code, 429)
		self.assertContains(response, 'Acesso temporariamente bloqueado', status_code=429)
