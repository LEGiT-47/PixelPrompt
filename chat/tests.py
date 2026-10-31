import tempfile
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.storage import default_storage
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .forms import RegisterForm
from .models import Chat, Image


class ImagePrivacyAndManagementTests(TestCase):
	def setUp(self):
		self.media_directory = tempfile.TemporaryDirectory()
		self.media_settings = override_settings(MEDIA_ROOT=self.media_directory.name)
		self.media_settings.enable()

		self.owner = User.objects.create_user(username="owner", password="test-password")
		self.other_user = User.objects.create_user(username="other", password="test-password")
		self.chat = Chat.objects.create(title="private-chat", user=self.owner)
		self.image = Image.objects.create(
			chat=self.chat,
			prompt="A private test image",
			image="chat_images/private.png",
		)
		self.client.force_login(self.owner)

	def tearDown(self):
		self.media_settings.disable()
		self.media_directory.cleanup()

	def image_url(self):
		return reverse("serve_image", kwargs={"image_id": self.image.pk})

	def delete_url(self):
		return reverse("delete_image", kwargs={"image_id": self.image.pk})

	def test_image_view_requires_login(self):
		self.client.logout()

		response = self.client.get(self.image_url())

		self.assertEqual(response.status_code, 302)

	def test_owner_can_view_image_through_authenticated_route(self):
		with patch.object(default_storage, "open", return_value=BytesIO(b"private image")):
			response = self.client.get(self.image_url())

		self.assertEqual(response.status_code, 200)
		self.assertEqual(b"".join(response.streaming_content), b"private image")
		self.assertEqual(response["Cache-Control"], "private, no-store")

	def test_other_user_cannot_view_or_download_image(self):
		self.client.force_login(self.other_user)

		view_response = self.client.get(self.image_url())
		download_response = self.client.get(f"{self.image_url()}?download=1")

		self.assertEqual(view_response.status_code, 404)
		self.assertEqual(download_response.status_code, 404)

	def test_direct_media_url_is_not_routed(self):
		response = self.client.get("/media/chat_images/private.png")

		self.assertEqual(response.status_code, 404)

	def test_private_storage_does_not_generate_public_urls(self):
		with self.assertRaises(ValueError):
			self.image.image.url

	def test_download_uses_attachment_content_disposition(self):
		with patch.object(default_storage, "open", return_value=BytesIO(b"private image")):
			response = self.client.get(f"{self.image_url()}?download=1")

		self.assertEqual(response.status_code, 200)
		self.assertIn("attachment", response["Content-Disposition"])

	def test_image_deletion_is_post_only_and_owner_checked(self):
		self.assertEqual(self.client.get(self.delete_url()).status_code, 405)

		self.client.force_login(self.other_user)
		response = self.client.post(self.delete_url())

		self.assertEqual(response.status_code, 404)
		self.assertTrue(Image.objects.filter(pk=self.image.pk).exists())

	def test_owner_can_delete_image_and_file(self):
		with patch.object(default_storage, "delete") as storage_delete:
			response = self.client.post(self.delete_url())

		self.assertEqual(response.status_code, 302)
		self.assertFalse(Image.objects.filter(pk=self.image.pk).exists())
		storage_delete.assert_called_once_with("chat_images/private.png")

	def test_generation_failure_shows_safe_retry_message(self):
		with patch("chat.views.generate_image", side_effect=RuntimeError("internal model detail")):
			response = self.client.post(
				reverse("chat_detail", kwargs={"chat_id": self.chat.title}),
				{"prompt": "A scenic view"},
			)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Image generation failed.")
		self.assertContains(response, "Please try again.")
		self.assertContains(response, "Try again")
		self.assertNotContains(response, "internal model detail")

	def test_generation_keeps_history_above_four_images(self):
		old_images = [
			Image.objects.create(
				chat=self.chat,
				prompt=f"Older image {index}",
				image=f"chat_images/old-{index}.png",
			)
			for index in range(4)
		]

		class GeneratedImage:
			def save(self, image_buffer, format):
				image_buffer.write(b"generated image data")

		with patch("chat.views.generate_image", return_value=GeneratedImage()):
			response = self.client.post(
				reverse("chat_detail", kwargs={"chat_id": self.chat.title}),
				{"prompt": "Keep my history"},
			)

		self.assertEqual(response.status_code, 302)
		self.assertEqual(self.chat.images.count(), 6)
		self.assertTrue(all(Image.objects.filter(pk=image.pk).exists() for image in old_images))

	def test_logout_requires_post_and_csrf(self):
		csrf_client = Client(enforce_csrf_checks=True)
		csrf_client.force_login(self.owner)
		logout_url = reverse("logout")

		self.assertEqual(csrf_client.get(logout_url).status_code, 405)
		self.assertEqual(csrf_client.post(logout_url).status_code, 403)

	def test_chat_shows_private_image_and_management_controls(self):
		response = self.client.get(reverse("chat_detail", kwargs={"chat_id": self.chat.title}))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, self.image_url())
		self.assertContains(response, self.delete_url())
		self.assertNotContains(response, "/media/chat_images/")

	def test_image_form_validation_is_visible(self):
		response = self.client.post(
			reverse("chat_detail", kwargs={"chat_id": self.chat.title}),
			{"prompt": ""},
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "This field is required.")

	def test_owner_can_rename_chat(self):
		response = self.client.post(
			reverse("rename_chat", kwargs={"chat_id": self.chat.pk}),
			{"title": "renamed-chat"},
		)

		self.chat.refresh_from_db()
		self.assertEqual(response.status_code, 302)
		self.assertEqual(self.chat.title, "renamed-chat")

	def test_owner_can_clear_chat_history(self):
		Image.objects.create(chat=self.chat, prompt="Second image", image="chat_images/second.png")

		response = self.client.post(reverse("clear_chat", kwargs={"chat_id": self.chat.pk}))

		self.assertEqual(response.status_code, 302)
		self.assertEqual(self.chat.images.count(), 0)

	def test_owner_can_delete_chat(self):
		response = self.client.post(reverse("delete_chat", kwargs={"chat_id": self.chat.pk}))

		self.assertEqual(response.status_code, 302)
		self.assertFalse(Chat.objects.filter(pk=self.chat.pk).exists())

	def test_other_user_cannot_manage_chat(self):
		self.client.force_login(self.other_user)
		chat_actions = ("rename_chat", "clear_chat", "delete_chat")

		for action in chat_actions:
			with self.subTest(action=action):
				response = self.client.post(reverse(action, kwargs={"chat_id": self.chat.pk}), {"title": "stolen"})
				self.assertEqual(response.status_code, 404)

		self.assertTrue(Chat.objects.filter(pk=self.chat.pk, user=self.owner).exists())

	def test_registration_form_validates_email_and_duplicate_addresses(self):
		self.owner.email = "owner@example.test"
		self.owner.save(update_fields=["email"])
		form = RegisterForm(data={
			"username": "new-user",
			"email": "OWNER@example.test",
			"password1": "B1ue!River#43",
			"password2": "B1ue!River#43",
		})

		self.assertFalse(form.is_valid())
		self.assertIn("email", form.errors)
