#!/bin/bash
# Setup ComfyUI on wgpx15 for bildwerk image processing

set -e

echo "🚀 Setting up ComfyUI on wgpx15..."

# Create directories
mkdir -p /opt/bildwerk/models/checkpoints
mkdir -p /opt/bildwerk/models/controlnet
mkdir -p /opt/bildwerk/output
mkdir -p /opt/bildwerk/descriptions

# Clone ComfyUI if not exists
if [ ! -d "/opt/bildwerk/ComfyUI" ]; then
    echo "Cloning ComfyUI..."
    cd /opt/bildwerk
    git clone https://github.com/comfyanonymous/ComfyUI.git
fi

# Install Python dependencies
echo "Installing Python dependencies..."
cd /opt/bildwerk/ComfyUI
pip3 install --upgrade pip
pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip3 install -r requirements.txt

# Download models (using wget or curl)
echo "Downloading models..."

# SDXL Base
if [ ! -f "/opt/bildwerk/models/checkpoints/sd_xl_base_1.0.safetensors" ]; then
    echo "Downloading SDXL Base (~6GB)..."
    wget -q --show-progress -O /opt/bildwerk/models/checkpoints/sd_xl_base_1.0.safetensors \
        https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors
fi

# SDXL Refiner
if [ ! -f "/opt/bildwerk/models/checkpoints/sd_xl_refiner_1.0.safetensors" ]; then
    echo "Downloading SDXL Refiner (~6GB)..."
    wget -q --show-progress -O /opt/bildwerk/models/checkpoints/sd_xl_refiner_1.0.safetensors \
        https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_refiner_1.0.safetensors
fi

# ControlNet SoftEdge
if [ ! -f "/opt/bildwerk/models/controlnet/controlnet-sdxl-softedge.safetensors" ]; then
    echo "Downloading ControlNet SoftEdge (~6GB)..."
    wget -q --show-progress -O /opt/bildwerk/models/controlnet/controlnet-sdxl-softedge.safetensors \
        https://huggingface.co/diffusers/controlnet-sdxl-softedge/resolve/main/diffusion_pytorch_model.safetensors
fi

# ControlNet Depth
if [ ! -f "/opt/bildwerk/models/controlnet/controlnet-sdxl-depth.safetensors" ]; then
    echo "Downloading ControlNet Depth (~6GB)..."
    wget -q --show-progress -O /opt/bildwerk/models/controlnet/controlnet-sdxl-depth.safetensors \
        https://huggingface.co/diffusers/controlnet-sdxl-depth/resolve/main/diffusion_pytorch_model.safetensors
fi

echo "✅ Setup complete!"
echo "Models available:"
ls -lh /opt/bildwerk/models/checkpoints/
ls -lh /opt/bildwerk/models/controlnet/
