import secrets

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

# Generated per test run, so no password literal lives in the repository.
PASSWORD = secrets.token_urlsafe(16)


class RegisterTests(TestCase):
    def payload(self, **overrides):
        data = {
            "username": "alice",
            "email": "alice@example.com",
            "password1": PASSWORD,
            "password2": PASSWORD,
        }
        data.update(overrides)
        return data

    def test_valid_registration_saves_email(self):
        resp = self.client.post(reverse("register"), self.payload())
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(User.objects.get(username="alice").email, "alice@example.com")

    def test_invalid_email_rejected(self):
        resp = self.client.post(reverse("register"), self.payload(email="not-an-email"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("email", resp.context["form"].errors)
        self.assertFalse(User.objects.filter(username="alice").exists())

    def test_missing_email_rejected(self):
        resp = self.client.post(reverse("register"), self.payload(email=""))
        self.assertIn("email", resp.context["form"].errors)

    def test_duplicate_email_rejected_case_insensitive(self):
        User.objects.create_user("bob", "alice@example.com", PASSWORD)
        resp = self.client.post(reverse("register"), self.payload(email="ALICE@Example.com"))
        self.assertIn("email", resp.context["form"].errors)

    def test_duplicate_username_rejected(self):
        User.objects.create_user("alice", "other@example.com", PASSWORD)
        resp = self.client.post(reverse("register"), self.payload())
        self.assertIn("username", resp.context["form"].errors)

    def test_password_mismatch_rejected(self):
        resp = self.client.post(reverse("register"), self.payload(password2="different"))
        self.assertIn("password2", resp.context["form"].errors)

    def test_weak_password_rejected(self):
        resp = self.client.post(
            reverse("register"), self.payload(password1="12345678", password2="12345678")
        )
        self.assertIn("password2", resp.context["form"].errors)

    def test_errors_are_rendered_next_to_fields(self):
        resp = self.client.post(reverse("register"), self.payload(email="bad"))
        self.assertContains(resp, 'class="field-error"')


class LoginTests(TestCase):
    def setUp(self):
        User.objects.create_user("alice", "alice@example.com", PASSWORD)

    def test_wrong_password_shows_generic_message(self):
        resp = self.client.post(reverse("login"), {"username": "alice", "password": "wrong"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Incorrect username or password")

    def test_unknown_user_gets_same_message(self):
        resp = self.client.post(reverse("login"), {"username": "nobody", "password": "wrong"})
        self.assertContains(resp, "Incorrect username or password")

    def test_empty_fields_show_required_errors(self):
        resp = self.client.post(reverse("login"), {"username": "", "password": ""})
        self.assertIn("username", resp.context["form"].errors)
        self.assertIn("password", resp.context["form"].errors)

    def test_valid_login_redirects(self):
        resp = self.client.post(reverse("login"), {"username": "alice", "password": PASSWORD})
        self.assertEqual(resp.status_code, 302)
import os
import secrets
import tempfile

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Chat, Image

# Generated per test run, so no password literal lives in the repository.
PASSWORD = secrets.token_urlsafe(16)


class ChatManagementTests(TestCase):
    def setUp(self):
        self.a = User.objects.create_user("a", password=PASSWORD)
        self.b = User.objects.create_user("b", password=PASSWORD)
        self.chat = Chat.objects.create(title="Mine", user=self.a)

    def login(self, name):
        self.client.login(username=name, password=PASSWORD)

    def test_owner_can_rename(self):
        self.login("a")
        resp = self.client.post(reverse("rename_chat", args=[self.chat.id]), {"title": "  New name "})
        self.assertEqual(resp.status_code, 302)
        self.chat.refresh_from_db()
        self.assertEqual(self.chat.title, "New name")

    def test_blank_rename_is_ignored(self):
        self.login("a")
        self.client.post(reverse("rename_chat", args=[self.chat.id]), {"title": "   "})
        self.chat.refresh_from_db()
        self.assertEqual(self.chat.title, "Mine")

    def test_owner_can_delete(self):
        self.login("a")
        self.client.post(reverse("delete_chat", args=[self.chat.id]))
        self.assertFalse(Chat.objects.filter(id=self.chat.id).exists())

    def test_owner_can_clear_but_chat_stays(self):
        Image.objects.create(chat=self.chat, prompt="p", image="chat_images/x.png")
        self.login("a")
        self.client.post(reverse("clear_chat", args=[self.chat.id]))
        self.assertTrue(Chat.objects.filter(id=self.chat.id).exists())
        self.assertEqual(self.chat.images.count(), 0)

    def test_other_user_gets_404_and_nothing_changes(self):
        Image.objects.create(chat=self.chat, prompt="p", image="chat_images/x.png")
        self.login("b")
        for name in ("rename_chat", "delete_chat", "clear_chat"):
            resp = self.client.post(reverse(name, args=[self.chat.id]), {"title": "hacked"})
            self.assertEqual(resp.status_code, 404, name)
        self.chat.refresh_from_db()
        self.assertEqual(self.chat.title, "Mine")
        self.assertEqual(self.chat.images.count(), 1)
        self.assertEqual(self.client.get(reverse("chat_detail", args=[self.chat.id])).status_code, 404)

    def test_get_requests_not_allowed(self):
        self.login("a")
        for name in ("rename_chat", "delete_chat", "clear_chat"):
            self.assertEqual(self.client.get(reverse(name, args=[self.chat.id])).status_code, 405)

    def test_anonymous_is_redirected_to_login(self):
        resp = self.client.post(reverse("delete_chat", args=[self.chat.id]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp["Location"])
        self.assertTrue(Chat.objects.filter(id=self.chat.id).exists())

    def test_pages_render_and_duplicate_titles_work(self):
        twin = Chat.objects.create(title="Mine", user=self.a)  # same title used to crash
        self.login("a")
        self.assertEqual(self.client.get(reverse("chat_home")).status_code, 200)
        for c in (self.chat, twin):
            self.assertEqual(self.client.get(reverse("chat_detail", args=[c.id])).status_code, 200)

    def test_new_chat_creation_redirects_to_it(self):
        self.login("a")
        resp = self.client.post(reverse("chat_home"), {"title": "Fresh"})
        new = Chat.objects.get(title="Fresh", user=self.a)
        self.assertRedirects(resp, reverse("chat_detail", args=[new.id]), fetch_redirect_response=False)

    def test_clearing_removes_files_from_disk(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(MEDIA_ROOT=tmp):
            img = Image(chat=self.chat, prompt="p")
            img.image.save("x.png", ContentFile(b"data"), save=True)
            path = img.image.path
            self.assertTrue(os.path.exists(path))
            self.chat.images.all().delete()
            self.assertFalse(os.path.exists(path))
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
