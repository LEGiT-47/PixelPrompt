# PixelPrompt

PixelPrompt is a Django application that generates images with Stable Diffusion.

## Requirements

- Python 3.10 or newer
- A CPU or CUDA-capable PyTorch installation
- The Stable Diffusion 1.5 model is downloaded the first time an image is generated
- Hugging Face access may be required for the configured model; accept its model terms and set `HF_TOKEN` if prompted
- CPU generation works but can be very slow; a supported CUDA GPU is recommended

`torch` and `torchvision` must remain on the matching versions listed in
`requirements.txt`. The default installation uses the packages available from
PyPI. For a CUDA-specific PyTorch build, install the matching `torch` and
`torchvision` versions from the [PyTorch installation selector](https://pytorch.org/get-started/locally/)
first, then install the remaining application dependencies without replacing
those packages:

```powershell
python -m pip install torch==2.14.1 torchvision==0.29.1 --index-url <PyTorch-wheel-index>
python -m pip install -r requirements.txt
```

Replace `<PyTorch-wheel-index>` with the index URL for the desired CUDA release
from the PyTorch selector. The CUDA release must provide the torch/torchvision
versions pinned by this project. CPU users can skip this step.

## Setup

Clone the repository and enter the project directory:

```powershell
git clone <repository-url>
cd PixelPrompt
```

Create and activate a virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

On macOS or Linux, activate it with:

```sh
source .venv/bin/activate
```

Install the dependencies:

```sh
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Configure Django. `DJANGO_SECRET_KEY` is required when debug is disabled;
`DJANGO_ALLOWED_HOSTS` is a comma-separated list of allowed host names.

```powershell
$env:DJANGO_DEBUG = "true"
$env:DJANGO_SECRET_KEY = "development-only-change-me"
$env:DJANGO_ALLOWED_HOSTS = "localhost,127.0.0.1"
# Optional: set this if Hugging Face requires authentication for the model
$env:HF_TOKEN = "hf_your_token"
```

On macOS or Linux, use:

```sh
export DJANGO_DEBUG=true
export DJANGO_SECRET_KEY=development-only-change-me
export DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
# Optional: set this if Hugging Face requires authentication for the model
export HF_TOKEN=hf_your_token
```

Apply migrations and start the development server:

```sh
python manage.py migrate
python manage.py runserver
```

Open <http://127.0.0.1:8000/>. For production, set `DJANGO_DEBUG=false`, use a
strong secret key, and configure the production host names in
`DJANGO_ALLOWED_HOSTS`.
