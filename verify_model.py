#!/usr/bin/env python3
import safetensors.torch as st
try:
    with open('/opt/bildwerk/worker/ComfyUI/models/diffusion_models/flux-2-klein-4b-fp8.safetensors', 'rb') as f:
        data = st.load_file(f)
    print("File valid, keys:", len(data))
except Exception as e:
    print(f"Error: {e}")
