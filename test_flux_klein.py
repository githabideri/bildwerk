#!/usr/bin/env python3
import requests
import json
import time
import sys

COMFYUI_URL = "http://192.168.0.49:8188"

workflow = {
  "1": {"class_type": "LoadImage", "inputs": {"image": "test.png", "upload": "input"}},
  "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux-2-klein-4b-fp8.safetensors", "weight_dtype": "default"}},
  "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_4b.safetensors", "type": "flux2", "weight_dtype": "default"}},
  "4": {"class_type": "VAELoader", "inputs": {"vae_name": "flux2-vae.safetensors"}},
  "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": "test"}},
  "6": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["5", 0]}},
  "7": {"class_type": "GetImageSize", "inputs": {"image": ["1", 0]}},
  "8": {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": ["7", 0], "height": ["7", 1], "batch_size": 1}},
  "9": {"class_type": "Flux2Scheduler", "inputs": {"width": ["7", 0], "height": ["7", 1], "steps": 4}},
  "10": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
  "11": {"class_type": "RandomNoise", "inputs": {"noise_seed": 12345, "control_after_generate": "randomize"}},
  "12": {"class_type": "VAEEncode", "inputs": {"pixels": ["1", 0], "vae": ["4", 0]}},
  "13": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["5", 0], "latent": ["12", 0]}},
  "14": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["6", 0], "latent": ["12", 0]}},
  "15": {"class_type": "CFGGuider", "inputs": {"model": ["2", 0], "positive": ["13", 0], "negative": ["14", 0], "cfg": 1}},
  "16": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["11", 0], "guider": ["15", 0], "sampler": ["10", 0], "sigmas": ["9", 0], "latent_image": ["8", 0]}},
  "17": {"class_type": "VAEDecode", "inputs": {"samples": ["16", 0], "vae": ["4", 0]}},
  "18": {"class_type": "SaveImage", "inputs": {"filename_prefix": "TEST_FLUX", "images": ["17", 0]}}
}

print("Submitting...")
resp = requests.post(f"{COMFYUI_URL}/api/prompt", json={"prompt": workflow})
if resp.status_code != 200:
    print(f"ERROR: {resp.status_code} - {resp.text}")
    sys.exit(1)

prompt_id = resp.json().get('prompt_id')
print(f"prompt_id: {prompt_id}")

for i in range(60):
    time.sleep(5)
    hist = requests.get(f"{COMFYUI_URL}/api/history/{prompt_id}").json()
    if prompt_id in hist:
        status_str = hist[prompt_id].get('status', {}).get('status_str', 'unknown')
        print(f"Status: {status_str}")
        if status_str == 'success':
            print("SUCCESS!")
            sys.exit(0)
        elif status_str == 'error':
            print(f"FAILED: {hist[prompt_id]}")
            sys.exit(1)
    print(f"Waiting... ({i+1}/60)")

print("TIMEOUT")
sys.exit(1)
