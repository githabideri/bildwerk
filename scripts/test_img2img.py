#!/usr/bin/env python3
"""
Test script for img2img workflow validation
Tests:
1. Upload source image to ComfyUI
2. Submit img2img prompt
3. Poll for completion
4. Retrieve output
5. Verify output resembles source
"""

import asyncio
import aiohttp
import aiofiles
import json
import os
import base64
from pathlib import Path

WORKER_URL = "http://192.168.0.49:8188"
TEMP_DIR = Path("/var/lib/clawdbot/workspace/agents/hgg16/bildwerk/test_output")
TEMP_DIR.mkdir(exist_ok=True)

async def upload_image(session, image_path: str, filename: str) -> bool:
    """Upload image to ComfyUI"""
    url = f"{WORKER_URL}/upload/image"
    async with aiofiles.open(image_path, 'rb') as f:
        image_data = await f.read()
    
    form = aiohttp.FormData()
    form.add_field('image', image_data, filename=filename, content_type='image/png')
    
    async with session.post(url, data=form) as resp:
        success = resp.status in [200, 204]
        print(f"  Upload {'✓' if success else '✗'}: {resp.status}")
        return success

async def submit_prompt(session, workflow: dict) -> str:
    """Submit prompt to ComfyUI"""
    url = f"{WORKER_URL}/api/prompt"
    async with session.post(url, json={"prompt": workflow}) as resp:
        if resp.status == 200:
            result = await resp.json()
            prompt_id = result.get('prompt_id')
            print(f"  Prompt submitted ✓: {prompt_id}")
            return prompt_id
        else:
            error = await resp.text()
            print(f"  Prompt submission ✗: {resp.status} - {error[:200]}")
            return None

async def poll_history(session, prompt_id: str, timeout: int = 60) -> dict:
    """Poll for job completion"""
    url = f"{WORKER_URL}/api/history/{prompt_id}"
    import time
    start = time.time()
    
    while time.time() - start < timeout:
        async with session.get(url) as resp:
            if resp.status == 200:
                history = await resp.json()
                if prompt_id in history:
                    status = history[prompt_id].get('status', {})
                    if status.get('status_str') == 'success':
                        print(f"  Job completed ✓")
                        return history[prompt_id]
        await asyncio.sleep(1)
    
    print(f"  Job timeout ✗")
    return None

async def download_output(session, filename: str, local_path: str) -> bool:
    """Download output image from ComfyUI"""
    url = f"{WORKER_URL}/view?filename={filename}&type=output"
    async with session.get(url) as resp:
        if resp.status == 200:
            data = await resp.read()
            with open(local_path, 'wb') as f:
                f.write(data)
            print(f"  Output downloaded ✓: {local_path}")
            return True
        else:
            print(f"  Output download ✗: {resp.status}")
            return False

def build_img2img_workflow(image_filename: str, denoise: float = 0.45, seed: int = None) -> dict:
    """Build minimal img2img workflow
    
    Args:
        image_filename: Filename of image uploaded to ComfyUI
        denoise: Denoise value (0.0-1.0, use 0.35-0.55 for img2img)
        seed: Random seed (None or -1 for random)
    """
    if seed is None:
        import random
        seed = random.randint(0, 2**32 - 1)
    
    return {
        "1": {
            "class_type": "LoadImage",
            "inputs": {
                "image": image_filename,
                "upload": "image"
            }
        },
        "2": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": "sd_xl_base_1.0.safetensors"
            }
        },
        "3": {
            "class_type": "VAEEncode",
            "inputs": {
                "pixels": ["1", 0],
                "vae": ["2", 2]
            }
        },
        "4": {
            "class_type": "KSampler",
            "inputs": {
                "cfg": 7.5,
                "denoise": denoise,
                "latent_image": ["3", 0],
                "model": ["2", 0],
                "negative": ["7", 0],
                "positive": ["5", 0],
                "sampler_name": "euler",
                "scheduler": "normal",
                "seed": seed,
                "steps": 20
            }
        },
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["2", 1],
                "text": "photorealistic modern building facade, high quality, detailed architecture, natural lighting, 8k"
            }
        },
        "6": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["4", 0],
                "vae": ["2", 2]
            }
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["2", 1],
                "text": "drawing, painting, sketch, illustration, low quality, blurry, distorted, text, watermark"
            }
        },
        "8": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "BILDWORK_TEST",
                "images": ["6", 0]
            }
        }
    }

async def main():
    print("🧪 Testing img2img workflow...\n")
    
    # Find a test image (first PNG/JPG in output or inbox)
    test_image = None
    for ext in ['*.png', '*.jpg', '*.jpeg']:
        candidates = list(TEMP_DIR.glob(ext))
        if candidates:
            test_image = candidates[0]
            break
    
    # Try Nextcloud inbox if no local images
    if not test_image:
        inbox_path = Path("/var/lib/clawdbot/workspace/agents/hgg16/bildwerk/private/inbox")
        if inbox_path.exists():
            candidates = list(inbox_path.glob("*.png")) + list(inbox_path.glob("*.jpg"))
            if candidates:
                test_image = candidates[0]
    
    if not test_image:
        print("❌ No test image found!")
        return
    
    print(f"📁 Test image: {test_image}")
    uploaded_filename = f"test_source_{test_image.name}"
    
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)) as session:
        # Step 1: Upload image
        print("\n1️⃣  Uploading source image...")
        if not await upload_image(session, str(test_image), uploaded_filename):
            print("❌ Upload failed, aborting")
            return
        
        # Step 2: Build and submit workflow
        print("\n2️⃣  Building img2img workflow...")
        workflow = build_img2img_workflow(uploaded_filename, denoise=0.45)
        print(f"   Nodes: {len(workflow)}")
        print(f"   Denoise: {workflow['4']['inputs']['denoise']}")
        print(f"   Source: LoadImage -> '{uploaded_filename}'")
        
        print("\n3️⃣  Submitting to ComfyUI...")
        prompt_id = await submit_prompt(session, workflow)
        if not prompt_id:
            print("❌ Submission failed, aborting")
            return
        
        # Step 3: Poll for completion
        print("\n4️⃣  Waiting for completion...")
        history = await poll_history(session, prompt_id, timeout=120)
        if not history:
            print("❌ Job failed or timed out")
            return
        
        # Step 4: Extract output filename and download
        print("\n5️⃣  Retrieving output...")
        outputs = history.get('outputs', {})
        for node_id, node_outputs in outputs.items():
            if 'images' in node_outputs:
                for img_info in node_outputs['images']:
                    filename = img_info.get('filename')
                    subfolder = img_info.get('subfolder', '')
                    img_type = img_info.get('type', 'output')
                    print(f"   Found output: {filename}")
                    
                    # Download
                    output_path = TEMP_DIR / f"test_result_{filename}"
                    if await download_output(session, filename, str(output_path)):
                        print(f"\n✅ SUCCESS! Output saved to: {output_path}")
                        print(f"   Compare with source: {test_image}")
                        return
        
        print("❌ No output images found")

if __name__ == "__main__":
    asyncio.run(main())
