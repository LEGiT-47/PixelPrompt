import logging
import os
import threading

import torch
from diffusers import StableDiffusionImg2ImgPipeline, StableDiffusionPipeline
from django.contrib.auth import login, logout
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import DatabaseError, transaction
from django.http import FileResponse, Http404
from django.views.decorators.http import require_POST
from .models import Chat, Image
from .forms import ChatTitleForm, ImageForm, RegisterForm
from io import BytesIO
from django.core.files.base import ContentFile
from PIL import Image as PILImage
from PIL import ImageOps
from django.core.files.storage import default_storage
from pathlib import Path
from uuid import uuid4

MODEL_ID = "runwayml/stable-diffusion-v1-5"
_MODEL_LOCK = threading.RLock()
_TEXT_TO_IMAGE_PIPELINE = None
_IMAGE_TO_IMAGE_PIPELINE = None
_LOGGER = logging.getLogger(__name__)


def _render_chat(request, chat, images, form, chaters, title_form=None, **extra):
    context = {
        "chat": chat,
        "images": images,
        "form": form,
        "chaters": chaters,
        "chat_title_form": title_form or ChatTitleForm(),
    }
    context.update(extra)
    return render(request, "chat_detail1.html", context)


def _chat_title_exists(user, title):
    return Chat.objects.filter(user=user, title__iexact=title).exists()


def _cleanup_saved_image(image):
    for field_file in (image.image, image.input_image):
        if field_file and field_file.name:
            try:
                default_storage.delete(field_file.name)
            except Exception:
                _LOGGER.exception("Could not clean up an image after a failed save")

def generate_image(prompt, input_image=None):
    global _TEXT_TO_IMAGE_PIPELINE, _IMAGE_TO_IMAGE_PIPELINE

    with _MODEL_LOCK:
        if _TEXT_TO_IMAGE_PIPELINE is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            dtype = torch.float16 if device == "cuda" else torch.float32
            _TEXT_TO_IMAGE_PIPELINE = StableDiffusionPipeline.from_pretrained(
                MODEL_ID,
                torch_dtype=dtype,
                token=os.environ.get("HF_TOKEN"),
            ).to(device)

        if input_image:
            if _IMAGE_TO_IMAGE_PIPELINE is None:
                _IMAGE_TO_IMAGE_PIPELINE = StableDiffusionImg2ImgPipeline.from_pipe(
                    _TEXT_TO_IMAGE_PIPELINE,
                )

            input_image.seek(0)
            with PILImage.open(input_image) as source_image:
                reference_image = ImageOps.fit(
                    source_image.convert("RGB"),
                    (512, 512),
                    method=PILImage.Resampling.LANCZOS,
                )
            generated_image = _IMAGE_TO_IMAGE_PIPELINE(
                prompt=prompt,
                image=reference_image,
                strength=0.75,
                guidance_scale=8.5,
            ).images[0]
            input_image.seek(0)
            return generated_image

        return _TEXT_TO_IMAGE_PIPELINE(
            prompt=prompt,
            guidance_scale=8.5,
        ).images[0]

@login_required
def dashboard(request):
    return redirect('chat_detail', chat_id='none')

@login_required
def chat_detail(request, chat_id):
    chaters = Chat.objects.filter(user=request.user)

    if(chat_id == 'none'):
        title_form = ChatTitleForm()
        if request.method == "POST":
            title_form = ChatTitleForm(request.POST)
            if title_form.is_valid():
                title = title_form.cleaned_data["title"]
                if _chat_title_exists(request.user, title):
                    title_form.add_error("title", "You already have a chat with this name.")
                else:
                    try:
                        chat = Chat.objects.create(title=title, user=request.user)
                    except DatabaseError:
                        _LOGGER.exception("Could not create a conversation")
                        messages.error(request, "We couldn't create that chat. Please try again.")
                    else:
                        return redirect("chat_detail", chat_id=chat.title)
        return render(request, "chat_detail1.html", {
            "chaters": chaters,
            "chat_title_form": title_form,
            "nope": "nope",
        })

    chat = get_object_or_404(Chat, title=chat_id, user=request.user)
    images = chat.images.all()
    form = ImageForm()
    title_form = ChatTitleForm()

    if request.method == 'POST':
        if "title" in request.POST:
            title_form = ChatTitleForm(request.POST)
            if title_form.is_valid():
                title = title_form.cleaned_data["title"]
                if _chat_title_exists(request.user, title):
                    title_form.add_error("title", "You already have a chat with this name.")
                else:
                    try:
                        new_chat = Chat.objects.create(title=title, user=request.user)
                    except DatabaseError:
                        _LOGGER.exception("Could not create a conversation")
                        messages.error(request, "We couldn't create that chat. Please try again.")
                    else:
                        return redirect("chat_detail", chat_id=new_chat.title)
            return _render_chat(request, chat, images, form, chaters, title_form)

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
                _LOGGER.exception("Stable Diffusion image generation failed")
                return _render_chat(
                    request,
                    chat,
                    images,
                    form,
                    chaters,
                    title_form,
                    generation_failed=True,
                )

            new_image = Image(chat=chat, prompt=prompt, input_image=input_image)
            try:
                new_image.image.save(
                    f"{uuid4().hex}.png",
                    ContentFile(image_buffer.read()),
                    save=False,
                )
                with transaction.atomic():
                    new_image.save()
            except (DatabaseError, OSError, ValueError):
                _LOGGER.exception("Could not save a generated image")
                _cleanup_saved_image(new_image)
                return _render_chat(
                    request,
                    chat,
                    images,
                    form,
                    chaters,
                    title_form,
                    save_failed=True,
                )
            return redirect('chat_detail', chat_id=chat_id)

    return _render_chat(request, chat, images, form, chaters, title_form)


@login_required
def serve_image(request, image_id):
    image = get_object_or_404(Image, pk=image_id, chat__user=request.user)
    if not image.image:
        raise Http404

    try:
        image_file = default_storage.open(image.image.name, "rb")
    except (FileNotFoundError, OSError, ValueError):
        raise Http404

    response = FileResponse(
        image_file,
        as_attachment=request.GET.get("download") == "1",
        filename=Path(image.image.name).name,
    )
    response["Cache-Control"] = "private, no-store"
    return response


@login_required
@require_POST
def delete_image(request, image_id):
    image = get_object_or_404(Image, pk=image_id, chat__user=request.user)
    chat_id = image.chat.title
    try:
        image.delete()
    except DatabaseError:
        _LOGGER.exception("Could not delete a generated image")
        messages.error(request, "We couldn't delete that image. Please try again.")
        return redirect("chat_detail", chat_id=chat_id)
    return redirect("chat_detail", chat_id=chat_id)


@login_required
@require_POST
def rename_chat(request, chat_id):
    chat = get_object_or_404(Chat, pk=chat_id, user=request.user)
    form = ChatTitleForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Enter a valid chat name.")
        return redirect("chat_detail", chat_id=chat.title)

    title = form.cleaned_data["title"]
    if Chat.objects.filter(user=request.user, title__iexact=title).exclude(pk=chat.pk).exists():
        messages.error(request, "You already have a chat with this name.")
        return redirect("chat_detail", chat_id=chat.title)

    old_title = chat.title
    chat.title = title
    try:
        chat.save(update_fields=["title"])
    except DatabaseError:
        _LOGGER.exception("Could not rename a conversation")
        messages.error(request, "We couldn't rename that chat. Please try again.")
        return redirect("chat_detail", chat_id=old_title)

    messages.success(request, "Chat renamed.")
    return redirect("chat_detail", chat_id=chat.title)


@login_required
@require_POST
def clear_chat(request, chat_id):
    chat = get_object_or_404(Chat, pk=chat_id, user=request.user)
    try:
        chat.images.all().delete()
    except DatabaseError:
        _LOGGER.exception("Could not clear a conversation")
        messages.error(request, "We couldn't clear that chat. Please try again.")
    else:
        messages.success(request, "Chat history cleared.")
    return redirect("chat_detail", chat_id=chat.title)


@login_required
@require_POST
def delete_chat(request, chat_id):
    chat = get_object_or_404(Chat, pk=chat_id, user=request.user)
    try:
        chat.delete()
    except DatabaseError:
        _LOGGER.exception("Could not delete a conversation")
        messages.error(request, "We couldn't delete that chat. Please try again.")
        return redirect("chat_detail", chat_id=chat.title)
    messages.success(request, "Chat deleted.")
    return redirect("dashboard")

from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.shortcuts import render, redirect

def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    user = form.save()
                    Chat.objects.create(title="First_Chat", user=user)
            except DatabaseError:
                _LOGGER.exception("Could not register a new account")
                messages.error(request, "We couldn't create your account. Please try again.")
            else:
                login(request, user)
                return redirect('dashboard')
    else:
        form = RegisterForm()
    return render(request, 'register.html', {'form': form})

@require_POST
def logout_view(request):
    logout(request)
    return redirect('login')
