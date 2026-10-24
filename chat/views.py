import logging
from io import BytesIO
from uuid import uuid4

import torch
from diffusers import StableDiffusionImg2ImgPipeline, StableDiffusionPipeline
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import DatabaseError, transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST, require_safe
from PIL import Image as PILImage
from torch import autocast
from torchvision import transforms

from .forms import ImageForm
from .models import Chat, Image

logger = logging.getLogger(__name__)

model_id = "runwayml/stable-diffusion-v1-5"
device = "cuda" if torch.cuda.is_available() else "cpu"


def delete_file(file_name):
    """Remove a stored image without exposing storage errors to users."""
    if not file_name:
        return

    try:
        default_storage.delete(file_name)
    except Exception:
        logger.exception("Failed to remove an image file from private storage")


def generate_image(prompt, input_image=None):
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


def _chat_context(chat, form, chaters, image_generation_failed=False):
    return {
        "chat": chat,
        "images": chat.images.all(),
        "form": form,
        "chaters": chaters,
        "image_generation_failed": image_generation_failed,
    }


@login_required
def dashboard(request):
    return redirect("chat_detail", chat_id="none")


@login_required
def chat_detail(request, chat_id):
    if chat_id == "none":
        if request.method == "POST":
            title = request.POST.get("title")
            if title:
                Chat.objects.create(title=title, user=request.user)
                return redirect("chat_detail", chat_id=title)
        return render(request, "chat_detail1.html", {
            "chaters": Chat.objects.filter(user=request.user),
            "nope": "nope",
        })

    # Preserve the existing per-user ownership check and Django 404 behavior.
    chat = get_object_or_404(Chat, title=chat_id, user=request.user)
    chaters = Chat.objects.filter(user=request.user)
    form = ImageForm()

    if request.method == "POST":
        title = request.POST.get("title")
        if title:
            Chat.objects.create(title=title, user=request.user)
            return redirect("chat_detail", chat_id=title)

        form = ImageForm(request.POST, request.FILES)
        if form.is_valid():
            prompt = form.cleaned_data["prompt"]
            input_image = form.cleaned_data.get("input_image")
            image_buffer = BytesIO()

            try:
                generated_image = generate_image(prompt, input_image)
                generated_image.save(image_buffer, format="PNG")
                image_buffer.seek(0)
            except Exception:
                logger.exception("Image generation failed for chat_id=%s", chat.pk)
                messages.error(
                    request,
                    "Image generation failed. We couldn't generate your image. Please try again.",
                )
                return render(
                    request,
                    "chat_detail1.html",
                    _chat_context(chat, form, chaters, image_generation_failed=True),
                )

            new_image = Image(chat=chat, prompt=prompt)
            try:
                new_image.image.save(
                    f"{uuid4().hex}.png",
                    ContentFile(image_buffer.getvalue()),
                    save=False,
                )
                with transaction.atomic():
                    new_image.save()
            except (DatabaseError, OSError, ValueError):
                logger.exception("Failed to persist generated image for chat_id=%s", chat.pk)
                delete_file(new_image.image.name)
                messages.error(
                    request,
                    "We couldn't save your generated image. Please try again.",
                )
                return render(
                    request,
                    "chat_detail1.html",
                    _chat_context(chat, form, chaters, image_generation_failed=True),
                )
            except Exception:
                logger.exception("Unexpected failure while saving image for chat_id=%s", chat.pk)
                delete_file(new_image.image.name)
                messages.error(
                    request,
                    "We couldn't save your generated image. Please try again.",
                )
                return render(
                    request,
                    "chat_detail1.html",
                    _chat_context(chat, form, chaters, image_generation_failed=True),
                )

            # Preserve image history; users explicitly choose which images to remove.
            return redirect("chat_detail", chat_id=chat_id)

    return render(request, "chat_detail1.html", _chat_context(chat, form, chaters))


@login_required
@require_safe
def serve_image(request, image_id):
    """Stream image content only after verifying the requesting user's ownership."""
    image = get_object_or_404(Image, pk=image_id, chat__user=request.user)
    try:
        image_file = default_storage.open(image.image.name, "rb")
    except (FileNotFoundError, OSError, ValueError):
        logger.exception("Stored image could not be opened for image_id=%s", image.pk)
        raise Http404("Image not found")

    response = FileResponse(
        image_file,
        as_attachment=request.GET.get("download") == "1",
        filename=f"pixelprompt-image-{image.pk}.png",
        content_type="image/png",
    )
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
@require_POST
def delete_image(request, image_id):
    """Delete an image only when its parent chat belongs to the current user."""
    image = get_object_or_404(Image, pk=image_id, chat__user=request.user)
    chat_title = image.chat.title
    stored_name = image.image.name

    try:
        with transaction.atomic():
            image.delete()
    except DatabaseError:
        logger.exception("Failed to delete image record image_id=%s", image_id)
        messages.error(request, "We couldn't delete this image. Please try again.")
        return redirect("chat_detail", chat_id=chat_title)

    try:
        default_storage.delete(stored_name)
    except Exception:
        # The database record is gone, so this orphan cannot be retrieved through the
        # authenticated image route. Log for storage cleanup without leaking details.
        logger.exception("Failed to remove deleted image file image_id=%s", image_id)
        messages.warning(request, "The image was removed, but its stored file could not be cleaned up.")
    else:
        messages.success(request, "Image deleted.")

    return redirect("chat_detail", chat_id=chat_title)


def register(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            Chat.objects.create(title="First_Chat", user=user)
            return redirect("dashboard")
    else:
        form = UserCreationForm()
    return render(request, "register.html", {"form": form})


@login_required
@require_POST
def logout_view(request):
    logout(request)
    return redirect("login")

