#!/usr/bin/env python3
from huggingface_hub import hf_hub_download
import os
import shutil

models = [
    ('Comfy-Org/z_image_turbo', 'split_files/text_encoders/qwen_3_4b.safetensors', 'text_encoders'),
    ('black-forest-labs/FLUX.2-klein-4b-fp8', 'flux-2-klein-4b-fp8.safetensors', 'diffusion_models'),
    ('Comfy-Org/flux2-dev', 'split_files/vae/flux2-vae.safetensors', 'vae'),
]

for repo, path, subdir in models:
    dest_dir = os.path.join('/opt/bildwerk/worker/ComfyUI/models', subdir)
    os.makedirs(dest_dir, exist_ok=True)
    print(f"Downloading {path} from {repo}...")
    filename = hf_hub_download(repo_id=repo, filename=path, cache_dir='/opt/bildwerk/worker/ComfyUI/.cache')
    dest = os.path.join(dest_dir, os.path.basename(path))
    if not os.path.exists(dest):
        shutil.copy(filename, dest)
        print(f"Copied to: {dest}")
    else:
        print(f"Already exists: {dest}")
    print(f"Size: {os.path.getsize(dest) / (1024*1024*1024):.2f} GB")
