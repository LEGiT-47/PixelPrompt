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
