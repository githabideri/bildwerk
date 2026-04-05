#!/usr/bin/env python3
"""Download ControlNet models for interior_passage calibration."""

import os
import subprocess

# ControlNet models needed for interior_passage
MODELS = [
    {
        "name": "sd_xl_openpose_controlnetplus",
        "url": "https://huggingface.co/InstantX/SDXL-ControlNet-Plus/resolve/main/SDXL-OpenPose-ControlNet-Plus/diffusion_pytorch_model.safetensors",
        "output": "sd_xl_openpose_controlnetplus.safetensors"
    },
    {
        "name": "sd_xl_softedge_2",
        "url": "https://huggingface.co/InstantX/SDXL-ControlNet-Plus/resolve/main/SDXL-SoftEdge-ControlNet-Plus/diffusion_pytorch_model.safetensors",
        "output": "sd_xl_softedge_controlnetplus.safetensors"
    },
    {
        "name": "depth_v2",
        "url": "https://huggingface.co/lllyasviel/ControlNet-v1-1/resolve/main/depth_v2.safetensors",
        "output": "depth_v2.safetensors"
    }
]

CONTROLNET_DIR = "/var/lib/clawdbot/workspace/agents/localbot-llmlab/ComfyUI/models/controlnet"

def main():
    os.makedirs(CONTROLNET_DIR, exist_ok=True)
    
    for model in MODELS:
        output_path = os.path.join(CONTROLNET_DIR, model["output"])
        
        if os.path.exists(output_path):
            print(f"✓ {model['output']} already exists")
            continue
        
        print(f"Downloading {model['name']}...")
        subprocess.run([
            "curl", "-L", "-o", output_path, model["url"]
        ], check=True)
        
        # Remove placeholder file if exists
        placeholder = os.path.join(CONTROLNET_DIR, "put_controlnets_and_t2i_here")
        if os.path.exists(placeholder):
            os.remove(placeholder)
        
        print(f"✓ Downloaded {model['output']}")

if __name__ == "__main__":
    main()
