import tempfile

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import Chat, Image


class ImageAccessTests(TestCase):
	def setUp(self):
		self.media_dir = tempfile.TemporaryDirectory()
		self.addCleanup(self.media_dir.cleanup)
		media_settings = override_settings(MEDIA_ROOT=self.media_dir.name)
		media_settings.enable()
		self.addCleanup(media_settings.disable)

		self.owner = User.objects.create_user(username='owner', password='test-password')
		self.other_user = User.objects.create_user(username='other', password='test-password')
		self.chat = Chat.objects.create(title='private-chat', user=self.owner)
		self.image = Image.objects.create(
			chat=self.chat,
			prompt='private image',
			image=SimpleUploadedFile('private.png', b'image-data', content_type='image/png'),
		)

	def test_owner_can_view_and_download_image(self):
		self.client.force_login(self.owner)

		view_response = self.client.get(reverse('image_file', args=[self.image.pk]))
		self.assertEqual(view_response.status_code, 200)
		self.assertEqual(b''.join(view_response.streaming_content), b'image-data')

		download_response = self.client.get(reverse('image_download', args=[self.image.pk]))
		self.assertEqual(download_response.status_code, 200)
		self.assertIn('attachment', download_response['Content-Disposition'])

	def test_other_user_cannot_view_or_download_image(self):
		self.client.force_login(self.other_user)

		self.assertEqual(
			self.client.get(reverse('image_file', args=[self.image.pk])).status_code,
			404,
		)
		self.assertEqual(
			self.client.get(reverse('image_download', args=[self.image.pk])).status_code,
			404,
		)

	def test_media_url_is_not_served_directly(self):
		self.client.force_login(self.owner)
		response = self.client.get(f'{settings.MEDIA_URL}{self.image.image.name}')
		self.assertEqual(response.status_code, 404)


class LogoutSecurityTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(username='logout-user', password='test-password')
		self.client = Client(enforce_csrf_checks=True)
		self.client.force_login(self.user)

	def test_logout_requires_csrf_protected_post(self):
		logout_url = reverse('logout')

		self.assertEqual(self.client.get(logout_url).status_code, 405)
		self.assertEqual(self.client.post(logout_url).status_code, 403)

		self.client.get(reverse('login'))
		csrf_token = self.client.cookies['csrftoken'].value
		response = self.client.post(logout_url, HTTP_X_CSRFTOKEN=csrf_token)

		self.assertEqual(response.status_code, 302)
		self.assertNotIn('_auth_user_id', self.client.session)
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import DatabaseError
from django.test import TestCase
from django.urls import reverse

from .models import Chat


class ChatErrorHandlingTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(username="pixel-user", password="test-password")
		self.chat = Chat.objects.create(title="test-chat", user=self.user)
		self.client.force_login(self.user)
		self.url = reverse("chat_detail", kwargs={"chat_id": self.chat.title})

	def test_invalid_generation_form_renders_field_errors(self):
		response = self.client.post(self.url, {"prompt": ""})

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Please correct the following")
		self.assertContains(response, "This field is required.")

	def test_generation_failure_shows_safe_feedback_and_logs_exception(self):
		with patch("chat.views.generate_image", side_effect=RuntimeError("private model details")):
			with self.assertLogs("chat", level="ERROR"):
				response = self.client.post(self.url, {"prompt": "A peaceful mountain lake"})

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "We couldn't generate the image.")
		self.assertNotContains(response, "private model details")

	def test_missing_chat_keeps_django_404_response(self):
		response = self.client.get(reverse("chat_detail", kwargs={"chat_id": "missing-chat"}))

		self.assertEqual(response.status_code, 404)

	def test_chat_creation_database_failure_shows_friendly_message(self):
		with patch("chat.views.Chat.objects.create", side_effect=DatabaseError("database internals")):
			with self.assertLogs("chat", level="ERROR"):
				response = self.client.post(reverse("chat_detail", kwargs={"chat_id": "none"}), {
					"title": "another-chat",
				})

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "We couldn't create your chat.")
		self.assertNotContains(response, "database internals")
