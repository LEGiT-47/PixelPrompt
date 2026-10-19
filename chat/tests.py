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
