#!/usr/bin/env python3
"""Try alternative depth controlnet models."""

import os
import requests

# Alternative depth models
MODELS = [
    {
        "name": "Depth Anything v2",
        "url": "https://huggingface.co/lllyasviel/ControlPlus/resolve/main/controlnet_depth_v2.safetensors",
        "output": "depth_v2.safetensors"
    },
    {
        "name": "MiDaS Depth",
        "url": "https://huggingface.co/lllyasviel/ControlNet-v1-1/resolve/main/control_v11_f1p_midas_pruned.safetensors",
        "output": "depth_midas_pruned.safetensors"
    },
    {
        "name": "Leres Depth",
        "url": "https://huggingface.co/lllyasviel/ControlNet-v1-1/resolve/main/leres.safetensors",
        "output": "leres.safetensors"
    }
]

CONTROLNET_DIR = "/var/lib/clawdbot/workspace/agents/localbot-llmlab/ComfyUI/models/controlnet"

def main():
    for model in MODELS:
        output_path = os.path.join(CONTROLNET_DIR, model["output"])
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
            print(f"✓ {model['output']} exists")
            continue
        
        print(f"Trying {model['name']}...")
        try:
            response = requests.get(model["url"], stream=True, timeout=120)
            if response.status_code == 200:
                content_type = response.headers.get('Content-Type', '')
                if 'text/html' not in content_type:
                    with open(output_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    size = os.path.getsize(output_path)
                    print(f"  ✓ Downloaded {model['output']} ({size} bytes)")
                else:
                    print(f"  ✗ HTML response")
            else:
                print(f"  ✗ HTTP {response.status_code}")
        except Exception as e:
            print(f"  ✗ Error: {e}")

if __name__ == "__main__":
    main()
