#!/usr/bin/env python3
"""Test single ControlNet workflow on 309.jpg"""

import json
import aiohttp
import asyncio
from pathlib import Path

COMFYUI_URL = "http://192.168.0.49:8188"

async def upload_image(image_path: str) -> str:
    """Upload image to ComfyUI"""
    url = f"{COMFYUI_URL}/upload/image"
    with open(image_path, 'rb') as f:
        image_data = f.read()
    
    filename = Path(image_path).name
    form = aiohttp.FormData()
    form.add_field('image', image_data, filename=filename, content_type='image/png')
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=form) as resp:
            if resp.status in [200, 204]:
                return filename
            else:
                error = await resp.text()
                raise Exception(f"Upload failed: {resp.status} - {error[:100]}")

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
                raise Exception(f"Submit failed: {resp.status} - {error[:100]}")

async def poll_completion(prompt_id: str, timeout: int = 600) -> dict:
    """Poll for completion"""
    url = f"{COMFYUI_URL}/api/history/{prompt_id}"
    start = __import__('time').time()
    async with aiohttp.ClientSession() as session:
        while __import__('time').time() - start < timeout:
            async with session.get(url) as resp:
                if resp.status == 200:
                    history = await resp.json()
                    if prompt_id in history:
                        return history[prompt_id]
            await asyncio.sleep(2)
    raise Exception(f"Timeout after {timeout}s")

async def main():
    # Load workflow
    workflow = json.load(open("/var/lib/clawdbot/workspace/agents/hgg16/bildwerk/workflows/309_controlnet_minimal.json"))
    
    # Upload image
    image_path = Path("/var/lib/clawdbot/workspace/agents/hgg16/bildwerk/private/interior_passage/309.jpg")
    uploaded = await upload_image(str(image_path))
    print(f"✓ Uploaded: {uploaded}")
    
    # Submit workflow
    prompt_id = await submit_workflow(workflow)
    print(f"✓ Prompt ID: {prompt_id}")
    
    # Poll for completion
    print("⏳ Waiting for completion...")
    result = await poll_completion(prompt_id)
    
    # Extract output
    outputs = result.get('outputs', {})
    output_filename = None
    for node_id, node_outputs in outputs.items():
        if 'images' in node_outputs:
            for img_info in node_outputs['images']:
                output_filename = img_info.get('filename')
                break
        if output_filename:
            break
    
    if output_filename:
        print(f"✓ Output: {output_filename}")
        
        # Download output
        output_url = f"{COMFYUI_URL}/view?filename={output_filename}&subfolder=&type=output"
        output_dir = Path("/var/lib/clawdbot/workspace/agents/hgg16/bildwerk/private/interior_passage/outputs_controlnet")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / output_filename
        
        async with aiohttp.ClientSession() as session:
            async with session.get(output_url) as resp:
                if resp.status == 200:
                    with open(output_path, 'wb') as f:
                        f.write(await resp.read())
                    print(f"✓ Downloaded: {output_path}")
                    
                    # Run Auto-QC
                    import sys
                    sys.path.insert(0, '/var/lib/clawdbot/workspace/agents/hgg16/bildwerk/scripts')
                    from auto_qc import analyze_image
                    metrics, routing = analyze_image(output_path)
                    print(f"✓ Auto-QC: {routing}")
                    print(f"  saturation={metrics['mean_saturation']:.4f}")
                    print(f"  highlight_clipping={metrics['highlight_clipping']:.4f}")
                    print(f"  laplacian={metrics['laplacian_variance']:.2f}")
                else:
                    print(f"✗ Download failed: {resp.status}")
    else:
        print("✗ No output filename found")

if __name__ == "__main__":
    asyncio.run(main())
