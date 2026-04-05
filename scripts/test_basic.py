#!/usr/bin/env python3
"""Test basic img2img without ControlNet first"""

import json
import aiohttp
import asyncio
from pathlib import Path
import sys

sys.path.insert(0, '/var/lib/clawdbot/workspace/agents/hgg16/bildwerk/scripts')

COMFYUI_URL = "http://192.168.0.49:8188"

async def upload_image(image_path: str) -> str:
    """Upload image to ComfyUI"""
    url = f"{COMFYUI_URL}/upload/image"
    
    with open(image_path, 'rb') as f:
        image_data = f.read()
    
    filename = image_path.name
    
    form = aiohttp.FormData()
    form.add_field('image', image_data, filename=filename, content_type='image/png')
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=form) as resp:
            if resp.status in [200, 204]:
                return filename
            else:
                error = await resp.text()
                print(f"Upload failed: {resp.status} - {error[:100]}")
                return None

async def submit_workflow(workflow: dict) -> str:
    """Submit workflow to ComfyUI"""
    url = f"{COMFYUI_URL}/api/prompt"
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json={"prompt": workflow}) as resp:
            if resp.status == 200:
                result = await resp.json()
                return result.get('prompt_id')
            else:
                error = await resp.text()
                print(f"Submit failed: {resp.status} - {error[:100]}")
                return None

async def poll_completion(prompt_id: str) -> dict:
    """Poll for completion"""
    url = f"{COMFYUI_URL}/api/history/{prompt_id}"
    
    async with aiohttp.ClientSession() as session:
        import time
        for _ in range(300):  # 10 minutes max
            await asyncio.sleep(2)
            async with session.get(url) as resp:
                if resp.status == 200:
                    history = await resp.json()
                    if prompt_id in history:
                        return history[prompt_id]
    
    return None

async def main():
    # Load workflow
    workflow_path = Path("/var/lib/clawdbot/workspace/agents/hgg16/bildwerk/workflows/test_no_controlnet.json")
    workflow = json.load(open(workflow_path))
    
    # Upload image
    image_path = Path("/var/lib/clawdbot/workspace/agents/hgg16/bildwerk/private/interior_passage/309.jpg")
    uploaded = await upload_image(image_path)
    print(f"Uploaded: {uploaded}")
    
    if not uploaded:
        return
    
    # Submit workflow
    prompt_id = await submit_workflow(workflow)
    print(f"Prompt ID: {prompt_id}")
    
    if not prompt_id:
        return
    
    # Poll
    result = await poll_completion(prompt_id)
    print(f"Result: {result}")

asyncio.run(main())
