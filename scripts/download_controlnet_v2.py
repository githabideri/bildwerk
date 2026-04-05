#!/usr/bin/env python3
"""Download ControlNet models - alternative approach using direct URLs."""

import os
import subprocess

# Alternative ControlNet models for SDXL
# These are more reliable sources
MODELS = [
    {
        "url": "https://github.com/comfyanonymous/ComfyUI_controlnet_diffs/raw/main/sd_xl_openpose_controlnet_plus.safetensors",
        "output": "sd_xl_openpose_controlnet_plus.safetensors"
    },
    {
        "url": "https://github.com/comfyanonymous/ComfyUI_controlnet_diffs/raw/main/sd_xl_canny_controlnet_plus.safetensors",
        "output": "sd_xl_canny_controlnet_plus.safetensors"
    },
    {
        "url": "https://huggingface.co/lllyasviel/ControlNet-v1-1/resolve/main/depth_midas.safetensors",
        "output": "depth_midas.safetensors"
    }
]

CONTROLNET_DIR = "/var/lib/clawdbot/workspace/agents/localbot-llmlab/ComfyUI/models/controlnet"

def main():
    os.makedirs(CONTROLNET_DIR, exist_ok=True)
    
    for model in MODELS:
        output_path = os.path.join(CONTROLNET_DIR, model["output"])
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            print(f"✓ {model['output']} already exists (skipping)")
            continue
        
        print(f"Downloading {model['output']}...")
        try:
            subprocess.run([
                "curl", "-L", "-o", output_path, model["url"]
            ], check=True, timeout=60)
            
            size = os.path.getsize(output_path)
            if size > 1000:
                print(f"✓ Downloaded {model['output']} ({size} bytes)")
            else:
                print(f"✗ Download failed for {model['output']} (only {size} bytes)")
                os.remove(output_path)
        except Exception as e:
            print(f"✗ Error downloading {model['output']}: {e}")

if __name__ == "__main__":
    main()
