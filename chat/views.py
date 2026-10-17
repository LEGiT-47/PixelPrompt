# import torch
# from torch import autocast
# from diffusers import StableDiffusionPipeline
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Chat, Image
from .forms import ImageForm
from io import BytesIO
from django.core.files.base import ContentFile
from PIL import Image as PILImage
from django.contrib.auth import logout
# from torchvision import transforms
# from diffusers import StableDiffusionImg2ImgPipeline
from django.core.files.storage import default_storage

def delete_file(file_path):
    if default_storage.exists(file_path):
        default_storage.delete(file_path)
        print(f"File {file_path} deleted.")
    else:
        print(f"File {file_path} does not exist.")

# model_id = "runwayml/stable-diffusion-v1-5"
# device = "cuda" if torch.cuda.is_available() else "cpu"

@login_required
def dashboard(request):
    return redirect('chat_detail', chat_id='none')

@login_required
def chat_detail(request, chat_id):
    if(chat_id == 'none'):
        if request.method == 'POST':
          title = request.POST.get('title')
          if title:
            Chat.objects.create(title=title, user=request.user)
            return redirect('chat_detail', chat_id=title)
        return render(request, 'chat_detail1.html', {'chaters': Chat.objects.filter(user=request.user), 'nope': "nope"})

    chat = get_object_or_404(Chat, title=chat_id, user=request.user)
    images = chat.images.all()
    form = ImageForm()
    chaters = Chat.objects.filter(user=request.user)

    if request.method == 'POST':
        title = request.POST.get('title')
        if title:
            Chat.objects.create(title=title, user=request.user)
            return redirect('chat_detail', chat_id=title)
        form = ImageForm(request.POST, request.FILES)
        if form.is_valid():
            prompt = form.cleaned_data['prompt']
            strength = 0.75

            # --- ML stub: image generation disabled for UI development ---
            # Creates a solid purple placeholder image instead of running Stable Diffusion
            placeholder = PILImage.new("RGB", (512, 512), color=(99, 27, 255))
            image_buffer = BytesIO()
            placeholder.save(image_buffer, format="PNG")
            image_buffer.seek(0)
            # --------------------------------------------------------------

            if chat.images.count() >= 4:
                oldest_image = chat.images.order_by('created_at').first()
                if oldest_image.image:
                    delete_file(oldest_image.image.path)
                oldest_image.delete()

            new_image = Image(chat=chat, prompt=prompt)
            new_image.image.save(f"{request.user}_{chat.title}_{prompt}.png", ContentFile(image_buffer.read()), save=True)
            new_image.save()
            return redirect('chat_detail', chat_id=chat_id)

    return render(request, 'chat_detail1.html', {'chat': chat, 'images': images, 'form': form, 'chaters': chaters})

from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.shortcuts import render, redirect

def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            Chat.objects.create(title="First_Chat", user=request.user)
            return redirect('dashboard')
    else:
        form = UserCreationForm()
    return render(request, 'register.html', {'form': form})

def logout_view(request):
    logout(request)
    return redirect('login')
