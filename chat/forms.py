from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import Image

User = get_user_model()

class ImageForm(forms.ModelForm):
    prompt = forms.CharField(max_length=255, widget=forms.Textarea(attrs={
        'placeholder': '''Describe the image you want to generate...
Try: &quot;Fantasy landscape with dragons and waterfalls&quot;, &quot;Cyberpunk city at night&quot;''',
        
        'class': 'w-full p-4 pr-20 rounded-xl border border-neutral-300 focus:border-primary-500 focus:ring focus:ring-primary-200 resize-none h-24 transition duration-200',
    }))

    class Meta:
        model = Image
        fields = ['prompt', 'input_image']


class ChatTitleForm(forms.Form):
    title = forms.CharField(max_length=100, strip=True)

    def clean_title(self):
        title = self.cleaned_data["title"]
        if title.lower() == "none" or "/" in title:
            raise forms.ValidationError("Choose a different chat name.")
        return title


class RegisterForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        help_text="Required. Enter a valid email address.",
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs["class"] = "auth-input"
            field.widget.attrs["required"] = "required"
            if field_name == "username":
                field.widget.attrs["autocomplete"] = "username"
            elif field_name == "email":
                field.widget.attrs["autocomplete"] = "email"
            elif field_name in {"password1", "password2"}:
                field.widget.attrs["autocomplete"] = "new-password"

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email


class LoginForm(AuthenticationForm):
    error_messages = {
        "invalid_login": "Incorrect username or password. Please try again.",
        "inactive": "This account is inactive.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {
                "class": "auth-input",
                "autocomplete": "username",
                "autofocus": True,
                "placeholder": "Enter your username",
                "required": "required",
            }
        )
        self.fields["password"].widget.attrs.update(
            {
                "class": "auth-input",
                "autocomplete": "current-password",
                "placeholder": "Enter your password",
                "required": "required",
            }
        )
