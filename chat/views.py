import logging
from io import BytesIO
from uuid import uuid4

import torch
import mimetypes
from pathlib import Path
from torch import autocast
from diffusers import StableDiffusionPipeline
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import FileResponse
from .models import Chat, Image
from .forms import ImageForm
from io import BytesIO
from diffusers import StableDiffusionImg2ImgPipeline, StableDiffusionPipeline
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import DatabaseError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from PIL import Image as PILImage
from torch import autocast
from torchvision import transforms
from diffusers import StableDiffusionImg2ImgPipeline
from django.core.files.storage import default_storage
from django.views.decorators.http import require_GET, require_POST

from .forms import ImageForm
from .models import Chat, Image

logger = logging.getLogger(__name__)

# Initialize the Stable Diffusion pipeline
model_id = "runwayml/stable-diffusion-v1-5"
device = "cuda" if torch.cuda.is_available() else "cpu"


def delete_file(file_name):
    """Delete a stored image by its storage-relative name, logging failures."""
    if not file_name:
        return

    try:
        if default_storage.exists(file_name):
            default_storage.delete(file_name)
    except Exception:
        logger.exception("Failed to delete an image from storage")


def generate_image(prompt, input_image=None):
    """Generate an image from a prompt, optionally using an uploaded image."""
    with autocast(device):
        if input_image:
            with PILImage.open(input_image) as opened_image:
                source_image = opened_image.convert("RGB")

            preprocess = transforms.Compose([
                transforms.Resize((512, 512)),
                transforms.ToTensor(),
                transforms.Normalize([0.5], [0.5]),
            ])
            input_tensor = preprocess(source_image).unsqueeze(0).to(device)
            pipeline = StableDiffusionImg2ImgPipeline.from_pretrained(
                model_id,
                torch_dtype=torch.float16 if device == "cuda" else torch.float32,
            )
            pipeline.to(device)
            return pipeline(
                prompt=prompt,
                image=input_tensor,
                strength=0.75,
                guidance_scale=8.5,
            )["images"][0]

        pipeline = StableDiffusionPipeline.from_pretrained(
            model_id,
            torch_dtype=torch.float16 if device == "cuda" else torch.float32,
        )
        pipeline.to(device)
        return pipeline(prompt, guidance_scale=8.5)["images"][0]


def _chat_context(chat, form, chaters):
    return {
        "chat": chat,
        "images": chat.images.all(),
        "form": form,
        "chaters": chaters,
    }


def _generation_failure(request, chat, form, chaters, database_failure=False):
    messages.error(
        request,
        "Something went wrong. We couldn't generate or save the image. Please try again.",
    )
    context = {
        "chat": chat,
        "images": [],
        "form": form,
        "chaters": [],
    } if database_failure else _chat_context(chat, form, chaters)
    return render(request, "chat_detail1.html", context)


@login_required
def dashboard(request):
    return redirect("chat_detail", chat_id="none")


@login_required
def chat_detail(request, chat_id):
    if chat_id == "none":
        if request.method == "POST":
            title = request.POST.get("title")
            if title:
                try:
                    Chat.objects.create(title=title, user=request.user)
                except DatabaseError:
                    logger.exception("Failed to create a chat for user_id=%s", request.user.pk)
                    messages.error(request, "We couldn't create your chat. Please try again.")
                    return render(request, "chat_detail1.html", {"chaters": [], "nope": "nope"})
                else:
                    return redirect("chat_detail", chat_id=title)

        return render(request, "chat_detail1.html", {
            "chaters": Chat.objects.filter(user=request.user),
            "nope": "nope",
        })

    # Keep Django's standard 404 response for chats that do not exist or are not owned by this user.
    chat = get_object_or_404(Chat, title=chat_id, user=request.user)
    chaters = Chat.objects.filter(user=request.user)
    form = ImageForm()

    if request.method == "POST":
        title = request.POST.get("title")
        if title:
            try:
                Chat.objects.create(title=title, user=request.user)
            except DatabaseError:
                logger.exception("Failed to create a chat for user_id=%s", request.user.pk)
                messages.error(request, "We couldn't create your chat. Please try again.")
                return render(request, "chat_detail1.html", {
                    "chat": chat,
                    "images": [],
                    "form": form,
                    "chaters": [],
                })
            else:
                return redirect("chat_detail", chat_id=title)
        else:
            form = ImageForm(request.POST, request.FILES)
            if form.is_valid():
                prompt = form.cleaned_data["prompt"]
                input_image = form.cleaned_data.get("input_image")

                try:
                    generated_image = generate_image(prompt, input_image)
                    image_buffer = BytesIO()
                    generated_image.save(image_buffer, format="PNG")
                    image_buffer.seek(0)
                except Exception:
                    logger.exception("Image generation failed for chat_id=%s", chat.pk)
                    messages.error(
                        request,
                        "Something went wrong. We couldn't generate the image. Please try again.",
                    )
                    return render(request, "chat_detail1.html", _chat_context(chat, form, chaters))

                new_image = Image(chat=chat, prompt=prompt)
                try:
                    new_image.image.save(
                        f"{uuid4().hex}.png",
                        ContentFile(image_buffer.read()),
                        save=False,
                    )
                except Exception:
                    logger.exception("Failed to store a generated image for chat_id=%s", chat.pk)
                    return _generation_failure(request, chat, form, chaters)

                try:
                    with transaction.atomic():
                        new_image.save()
                except DatabaseError:
                    logger.exception("Failed to save generated image record for chat_id=%s", chat.pk)
                    delete_file(new_image.image.name)
                    return _generation_failure(request, chat, form, chaters, database_failure=True)

                # Remove the oldest image only after the new image and record were saved.
                try:
                    oldest_image = None
                    with transaction.atomic():
                        if chat.images.count() > 4:
                            oldest_image = chat.images.exclude(pk=new_image.pk).order_by("created_at").first()
                            if oldest_image:
                                old_file_name = oldest_image.image.name
                                oldest_image.delete()
                            else:
                                old_file_name = None
                        else:
                            old_file_name = None
                    if old_file_name:
                        delete_file(old_file_name)
                except DatabaseError:
                    logger.exception("Failed to prune old images for chat_id=%s", chat.pk)

                return redirect("chat_detail", chat_id=chat_id)

    return render(request, "chat_detail1.html", _chat_context(chat, form, chaters))


@login_required
@require_GET
def image_file(request, image_id, download=False):
    image = get_object_or_404(
        Image.objects.select_related('chat'),
        pk=image_id,
        chat__user=request.user,
    )
    content_type = mimetypes.guess_type(image.image.name)[0] or 'application/octet-stream'
    return FileResponse(
        image.image.open('rb'),
        as_attachment=download,
        filename=Path(image.image.name).name,
        content_type=content_type,
    )

from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.shortcuts import render, redirect

def register(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    user = form.save()
                    Chat.objects.create(title="First_Chat", user=user)
            except DatabaseError:
                logger.exception("Failed to create a registered user and initial chat")
                form.add_error(None, "We couldn't complete your registration. Please try again.")
            else:
                login(request, user)
                return redirect("dashboard")
    else:
        form = UserCreationForm()
    return render(request, "register.html", {"form": form})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("login")

