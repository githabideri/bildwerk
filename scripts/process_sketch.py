#!/usr/bin/env python3
"""
Process a sketch image through bildwerk GPU worker
"""

import requests
import json
import base64
import sys
import os
from pathlib import Path

# Configuration
GPU_WORKER_URL = "http://192.168.0.49:8188"
COMFYUI_API_URL = f"{GPU_WORKER_URL}/api"

def load_image_as_base64(image_path):
    """Load image and encode as base64"""
    with open(image_path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')

def load_workflow(workflow_path):
    """Load ComfyUI workflow"""
    with open(workflow_path, 'r') as f:
        return json.load(f)

def submit_to_comfyui(workflow, image_base64):
    """Submit workflow to ComfyUI"""
    # Update workflow with image data
    workflow['5']['inputs']['image'] = image_base64
    
    # Update output path
    workflow['8']['inputs']['filename_prefix'] = 'bildwerk_output/test_sketch'
    
    response = requests.post(
        f"{COMFYUI_API_URL}/prompt",
        json={"prompt": workflow}
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Job submitted! Queue ID: {result.get('prompt_id', 'unknown')}")
        return result.get('prompt_id')
    else:
        print(f"❌ Error: {response.status_code} - {response.text}")
        return None

def get_result(comfyui_url, prompt_id):
    """Get result from ComfyUI"""
    response = requests.get(f"{comfyui_url}/history/{prompt_id}")
    if response.status_code == 200:
        return response.json()
    return None

def main():
    if len(sys.argv) < 2:
        print("Usage: python process_sketch.py <input_image.jpg>")
        sys.exit(1)
    
    input_image = sys.argv[1]
    workflow_path = Path(__file__).parent / "workflows/vedute_sketch_workflow.json"
    
    print(f"📁 Loading image: {input_image}")
    image_b64 = load_image_as_base64(input_image)
    
    print(f"📋 Loading workflow: {workflow_path}")
    workflow = load_workflow(workflow_path)
    
    print(f"🚀 Submitting to GPU worker: {GPU_WORKER_URL}")
    prompt_id = submit_to_comfyui(workflow, image_b64)
    
    if prompt_id:
        print(f"⏳ Processing... Check ComfyUI at {GPU_WORKER_URL}")
        print(f"📊 Result will be available at: {GPU_WORKER_URL}/view?filename=bildwerk_output/test_sketch_00000_.png")
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
