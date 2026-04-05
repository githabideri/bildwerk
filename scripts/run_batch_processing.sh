#!/bin/bash
# Master Orchestration Script - Bildwerk Batch Processing
# This script sets up everything and processes all 122 images

set -e

echo "=================================================="
echo "🎨 BILDWERK BATCH PROCESSOR"
echo "=================================================="
echo "Processing 122 Dias-Dichtl images"
echo "Target: wgpx15 (GPU server)"
echo "=================================================="
echo

# Configuration
WGPX15_HOST="root@192.168.0.15"
COMFYUI_PORT=8189
SCRIPTS_DIR="/var/lib/clawdbot/workspace/agents/hgg16/bildwerk/scripts"

# Step 1: Set up ComfyUI on wgpx15
echo "📦 Step 1: Setting up ComfyUI on wgpx15..."
echo "--------------------------------------------------"

ssh -o StrictHostKeyChecking=no root@wgpx15 << 'EOF'
# Create directories
mkdir -p /opt/bildwerk/models/checkpoints
mkdir -p /opt/bildwerk/models/controlnet
mkdir -p /opt/bildwerk/output

# Clone ComfyUI
if [ ! -d "/opt/bildwerk/ComfyUI" ]; then
    echo "Cloning ComfyUI..."
    cd /opt/bildwerk
    git clone https://github.com/comfyanonymous/ComfyUI.git
fi

cd /opt/bildwerk/ComfyUI

# Install dependencies
echo "Installing Python dependencies..."
pip3 install --quiet torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip3 install --quiet -r requirements.txt

echo "✅ ComfyUI setup complete"
EOF

echo "✅ wgpx15 setup complete!"
echo

# Step 2: Download models
echo "📥 Step 2: Downloading models to wgpx15..."
echo "--------------------------------------------------"

ssh -o StrictHostKeyChecking=no root@wgpx15 << 'EOF'
cd /opt/bildwerk/models

# Check if models exist
if [ ! -f "checkpoints/sd_xl_base_1.0.safetensors" ]; then
    echo "Downloading SDXL Base (~6.3GB)..."
    wget -q --show-progress --continue -O checkpoints/sd_xl_base_1.0.safetensors \
        "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors"
else
    echo "SDXL Base already exists"
fi

if [ ! -f "checkpoints/sd_xl_refiner_1.0.safetensors" ]; then
    echo "Downloading SDXL Refiner (~6.5GB)..."
    wget -q --show-progress --continue -O checkpoints/sd_xl_refiner_1.0.safetensors \
        "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_refiner_1.0.safetensors"
else
    echo "SDXL Refiner already exists"
fi

if [ ! -f "controlnet/controlnet-sdxl-softedge.safetensors" ]; then
    echo "Downloading ControlNet SoftEdge (~6.3GB)..."
    wget -q --show-progress --continue -O controlnet/controlnet-sdxl-softedge.safetensors \
        "https://huggingface.co/diffusers/controlnet-sdxl-softedge/resolve/main/diffusion_pytorch_model.safetensors"
else
    echo "ControlNet SoftEdge already exists"
fi

echo "✅ Models ready"
ls -lh checkpoints/
ls -lh controlnet/
EOF

echo "✅ Model download complete!"
echo

# Step 3: Start ComfyUI server
echo "🚀 Step 3: Starting ComfyUI server on wgpx15..."
echo "--------------------------------------------------"

ssh -o StrictHostKeyChecking=no root@wgpx15 << EOF
# Kill any existing ComfyUI on our port
pkill -f "ComfyUI.*${COMFYUI_PORT}" || true

# Start ComfyUI in background
cd /opt/bildwerk/ComfyUI
nohup python3 main.py \
    --listen 0.0.0.0 \
    --port ${COMFYUI_PORT} \
    --cuda-device 2 \
    --disable-all-custom-nodes \
    > /opt/bildwerk/comfyui.log 2>&1 &

echo "ComfyUI PID: \$!"
sleep 5
echo "ComfyUI started, checking..."
curl -s http://localhost:${COMFYUI_PORT}/system_stats || echo "Waiting for ComfyUI to start..."
EOF

echo "Waiting for ComfyUI to be ready..."
sleep 10

# Verify ComfyUI is running
if curl -s http://192.168.0.15:${COMFYUI_PORT}/system_stats > /dev/null; then
    echo "✅ ComfyUI is running on http://192.168.0.15:${COMFYUI_PORT}"
else
    echo "⚠️ ComfyUI might not be fully ready yet, continuing anyway..."
fi
echo

# Step 4: Run batch processor
echo "🔄 Step 4: Starting batch processing..."
echo "--------------------------------------------------"
echo "This will process all 122 images. Estimated time: 2-4 hours"
echo "You can safely leave this running overnight."
echo

# Run the batch processor
python3 ${SCRIPTS_DIR}/batch_processor.py

echo
echo "=================================================="
echo "✅ BATCH PROCESSING COMPLETE!"
echo "=================================================="
echo
echo "Results available at:"
echo "  - Processed images: /var/lib/clawdbot/workspace/agents/hgg16/bildwerk/output/"
echo "  - Descriptions: /var/lib/clawdbot/workspace/agents/hgg16/bildwerk/descriptions/"
echo "  - Summary: /var/lib/clawdbot/workspace/agents/hgg16/bildwerk/descriptions/processing_summary.json"
echo
echo "ComfyUI output on wgpx15:"
echo "  - /opt/bildwerk/output/"
echo "  - Check via: http://192.168.0.15:8189"
echo "=================================================="
