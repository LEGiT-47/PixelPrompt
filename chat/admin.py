from django.contrib import admin
from django import forms
from django.db import models
from .models import Chat, Image

admin.site.register(Chat)


@admin.register(Image)
class ImageAdmin(admin.ModelAdmin):
	# The default file widget renders ImageField.url, which private storage forbids.
	formfield_overrides = {
		models.ImageField: {"widget": forms.FileInput},
	}

