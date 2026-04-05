#!/usr/bin/env python3
"""Download correct SDXL ControlNet models."""

import os
import requests

# Correct working SDXL ControlNet models
MODELS = [
    {
        "name": "SDXL OpenPose",
        "url": "https://huggingface.co/thibaud/controlnet-openpose-sdxl-1.0/resolve/main/pytorch_model.safetensors",
        "output": "controlnet_openpose_sdxl.safetensors"
    },
    {
        "name": "SDXL Union (Canny/Depth/Lineart)",
        "url": "https://huggingface.co/xinsir/controlnet-union-sdxl-1.0/resolve/main/diffusion_pytorch_model.safetensors",
        "output": "controlnet_union_sdxl.safetensors"
    },
    {
        "name": "Mistoline (LineArt)",
        "url": "https://huggingface.co/TheMistoAI/MistoLine_SDXL_1.0/resolve/main/MistoLine_SDXL_1.0.safetensors",
        "output": "mistoline_sdxl.safetensors"
    }
]

CONTROLNET_DIR = "/var/lib/clawdbot/workspace/agents/localbot-llmlab/ComfyUI/models/controlnet"

def download_file(url, output_path):
    """Download file with proper error handling."""
    try:
        response = requests.get(url, stream=True, timeout=180)
        response.raise_for_status()
        
        # Check if response is HTML (error page)
        content_type = response.headers.get('Content-Type', '')
        if 'text/html' in content_type:
            print(f"  ✗ Got HTML response (not a model file)")
            content = response.text[:200]
            print(f"     First 200 chars: {content}")
            return False
        
        # Stream download
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        size = os.path.getsize(output_path)
        if size > 10000:
            print(f"  ✓ Downloaded {output_path} ({size} bytes)")
            return True
        else:
            print(f"  ✗ Downloaded but file is only {size} bytes")
            os.remove(output_path)
            return False
        
    except Exception as e:
        print(f"  ✗ Download failed: {e}")
        return False

def main():
    os.makedirs(CONTROLNET_DIR, exist_ok=True)
    
    # Clean up failed downloads
    for f in os.listdir(CONTROLNET_DIR):
        path = os.path.join(CONTROLNET_DIR, f)
        if os.path.isfile(path) and os.path.getsize(path) < 10000:
            os.remove(path)
            print(f"Removed failed: {f}")
    
    for model in MODELS:
        output_path = os.path.join(CONTROLNET_DIR, model["output"])
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
            print(f"✓ {model['output']} exists (skipping)")
            continue
        
        print(f"Downloading {model['name']}...")
        download_file(model["url"], output_path)

if __name__ == "__main__":
    main()
