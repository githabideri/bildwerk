#!/bin/bash
# Download required models for ComfyUI on wgpx15

set -e

echo "=================================================="
echo "DOWNLOADING COMFYUI MODELS FOR BILDWERK"
echo "=================================================="
echo ""

# Create directories
mkdir -p /root/ComfyUI/models/checkpoints
mkdir -p /root/ComfyUI/models/controlnet

echo "Downloading SDXL Base model (this will take a while)..."
cd /root/ComfyUI/models/checkpoints
wget --no-check-certificate \
  https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors \
  -O sd_xl_base_1.0.safetensors || \
wget https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors \
  -O sd_xl_base_1.0.safetensors

echo ""
echo "Downloading SDXL Refiner model..."
wget --no-check-certificate \
  https://huggingface.co/stabilityai/stable-diffusion-xl-refiner-1.0/resolve/main/sd_xl_refiner_1.0.safetensors \
  -O sd_xl_refiner_1.0.safetensors || \
wget https://huggingface.co/stabilityai/stable-diffusion-xl-refiner-1.0/resolve/main/sd_xl_refiner_1.0.safetensors \
  -O sd_xl_refiner_1.0.safetensors

echo ""
echo "Downloading ControlNet SoftEdge..."
cd /root/ComfyUI/models/controlnet
wget --no-check-certificate \
  https://huggingface.co/lllyasviel/sd_control_collection/resolve/main/sd15/softedges_sdxl_fp16.safetensors \
  -O controlnet-sdxl-softedge.safetensors || \
wget https://huggingface.co/diffusers/controlnet-sdxl-softedge-detailed/resolve/main/diffusion_pytorch_model.safetensors \
  -O controlnet-sdxl-softedge.safetensors

echo ""
echo "Models downloaded!"
echo ""
ls -lh /root/ComfyUI/models/checkpoints/
ls -lh /root/ComfyUI/models/controlnet/
