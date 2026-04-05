#!/usr/bin/env python3
"""Download ControlNet models with correct URLs."""

import os
import subprocess
import requests

# Correct ControlNet models for SDXL
# Using HuggingFace direct download URLs
MODELS = [
    {
        "name": "SDXL OpenPose ControlNet",
        "url": "https://huggingface.co/InstantX/SDXL-ControlNet-Plus/resolve/main/SDXL-OpenPose-ControlNet-Plus/diffusion_pytorch_model.safetensors",
        "output": "sd_xl_openpose_controlnet_plus.safetensors"
    },
    {
        "name": "SDXL Canny ControlNet",
        "url": "https://huggingface.co/InstantX/SDXL-ControlNet-Plus/resolve/main/SDXL-Canny-ControlNet-Plus/diffusion_pytorch_model.safetensors",
        "output": "sd_xl_canny_controlnet_plus.safetensors"
    },
    {
        "name": "Depth ControlNet",
        "url": "https://huggingface.co/lllyasviel/ControlNet-v1-1/resolve/main/depth_midas.safetensors",
        "output": "depth_midas.safetensors"
    }
]

CONTROLNET_DIR = "/var/lib/clawdbot/workspace/agents/localbot-llmlab/ComfyUI/models/controlnet"

def download_file(url, output_path):
    """Download file with requests, handling redirects properly."""
    try:
        response = requests.get(url, stream=True, timeout=120)
        response.raise_for_status()
        
        # Check if response is HTML (error page)
        content_type = response.headers.get('Content-Type', '')
        if 'text/html' in content_type:
            print(f"  ✗ HTML response (not a model file)")
            return False
        
        # Stream download
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        size = os.path.getsize(output_path)
        print(f"  ✓ Downloaded {output_path} ({size} bytes)")
        return True
        
    except Exception as e:
        print(f"  ✗ Download failed: {e}")
        return False

def main():
    os.makedirs(CONTROLNET_DIR, exist_ok=True)
    
    # Remove old failed downloads
    for f in os.listdir(CONTROLNET_DIR):
        if f.endswith('.safetensors') and os.path.getsize(os.path.join(CONTROLNET_DIR, f)) < 10000:
            os.remove(os.path.join(CONTROLNET_DIR, f))
            print(f"Removed failed download: {f}")
    
    for model in MODELS:
        output_path = os.path.join(CONTROLNET_DIR, model["output"])
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
            print(f"✓ {model['output']} exists (skipping)")
            continue
        
        print(f"Downloading {model['name']}...")
        download_file(model["url"], output_path)

if __name__ == "__main__":
    main()
