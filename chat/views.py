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
from django.core.files.base import ContentFile
from PIL import Image as PILImage
from django.contrib.auth import logout
from PIL import Image as PILImage
from torchvision import transforms
from diffusers import StableDiffusionImg2ImgPipeline
from django.core.files.storage import default_storage
from django.views.decorators.http import require_GET, require_POST

# Ensure the file exists and delete it
def delete_file(file_path):
    if default_storage.exists(file_path):
        default_storage.delete(file_path)
        print(f"File {file_path} deleted.")
    else:
        print(f"File {file_path} does not exist.")


# Initialize the Stable Diffusion pipeline
model_id = "runwayml/stable-diffusion-v1-5"
device = "cuda" if torch.cuda.is_available() else "cpu"

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
            print(11)
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
            print(11)
            return redirect('chat_detail', chat_id=title)
        form = ImageForm(request.POST, request.FILES)
        if form.is_valid():
            # Generate image using Stable Diffusion
            prompt = form.cleaned_data['prompt']
            input_image = form.cleaned_data.get('input_image')
            print(input_image)
            strength = 0.75
            print(2)
            with autocast(device):
               if input_image:  # Check if an input image is provided
                  # Load the input image
                  print(1)
                  input_image = PILImage.open(input_image).convert("RGB")
                  preprocess = transforms.Compose([
                  transforms.Resize((512, 512)),  # Match the Stable Diffusion resolution
                  transforms.ToTensor(),
                  transforms.Normalize([0.5], [0.5]),  # Normalize to [-1, 1]
                  ])
                  input_tensor = preprocess(input_image).unsqueeze(0).to(device)
                  pipe1 = StableDiffusionImg2ImgPipeline.from_pretrained(
                      model_id,
                      torch_dtype=torch.float16 if device == "cuda" else torch.float32,
                     
                    )
                  pipe1.to(device)
                  generated_image = pipe1(prompt=prompt, image=input_tensor, strength=strength, guidance_scale=8.5)["images"][0]
               else:
                   pipe = StableDiffusionPipeline.from_pretrained(
                     model_id,
                     torch_dtype=torch.float16 if device == "cuda" else torch.float32,
                    
                 )
                   pipe.to(device)
                   generated_image = pipe(prompt, guidance_scale=8.5)["images"][0]

            # Convert PIL image to an in-memory file
            image_buffer = BytesIO()
            generated_image.save(image_buffer, format="PNG")
            image_buffer.seek(0)

            

            if chat.images.count() >= 4:
            # Get the oldest image based on `created_at`
                 oldest_image = chat.images.order_by('created_at').first()

                 # Ensure the file exists and delete it from the filesystem
                 if oldest_image.image:
                          delete_file(oldest_image.image.path)
    
                   # Delete the record from the database
                 oldest_image.delete()


            new_image = Image(chat=chat, prompt=prompt)
            new_image.image.save(f"{request.user}_{chat.title}_{prompt}.png", ContentFile(image_buffer.read()), save=True)
            new_image.save()
            return redirect('chat_detail', chat_id=chat_id)

    return render(request, 'chat_detail1.html', {'chat': chat, 'images': images, 'form': form, 'chaters': chaters})


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
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)  # Automatically log in the user after registration
            Chat.objects.create(title="First_Chat", user=request.user)
            return redirect('dashboard')
    else:
        form = UserCreationForm()
    return render(request, 'register.html', {'form': form})

@require_POST
def logout_view(request):
    logout(request)
    return redirect('login')

