#!/usr/bin/env python3
"""
Run basic img2img calibration (without ControlNet)
This tests the core workflow before adding ControlNet.
"""

import json
import aiohttp
import asyncio
from pathlib import Path
from datetime import datetime
import sys
import os

sys.path.insert(0, '/var/lib/clawdbot/workspace/agents/hgg16/bildwerk/scripts')

COMFYUI_URL = "http://192.168.0.49:8188"
WORKSPACE = Path("/var/lib/clawdbot/workspace/agents/hgg16/bildwerk")
CALIBRATION_DIR = WORKSPACE / "private" / "interior_passage"

TUNING_IMAGES = ["309.jpg", "317.jpg", "324.jpg"]
VARIANTS = {
    "A": {"denoise": 0.38, "cfg": 5.0, "steps": 30},
    "B": {"denoise": 0.42, "cfg": 5.2, "steps": 32},
    "C": {"denoise": 0.45, "cfg": 5.5, "steps": 34},
}

POSITIVE_PROMPT = "present-day color architectural photograph of an interior passage with vaulted ceiling, realistic stone masonry, natural daylight, authentic limestone textures, documentary photography style, warm gray tones, professional architectural photography, high resolution"
NEGATIVE_PROMPT = "black and white, monochrome, sketch, drawing, engraving, illustration, etching, CGI, 3D render, plastic surfaces, washed out, overexposed, distorted geometry, malformed arches, unrealistic textures, text, watermark, low quality"


class BasicCalibrationRunner:
    def __init__(self):
        self.session = None
        self.results = []
    
    async def connect(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=600))
    
    async def close(self):
        if self.session:
            await self.session.close()
    
    async def upload_image(self, image_path: Path) -> str:
        url = f"{COMFYUI_URL}/upload/image"
        with open(image_path, 'rb') as f:
            image_data = f.read()
        filename = image_path.name
        form = aiohttp.FormData()
        form.add_field('image', image_data, filename=filename, content_type='image/png')
        async with self.session.post(url, data=form) as resp:
            if resp.status in [200, 204]:
                return filename
            else:
                error = await resp.text()
                raise Exception(f"Upload failed: {resp.status} - {error[:100]}")
    
    def build_workflow(self, image_filename: str, variant: str, params: dict) -> dict:
        import hashlib
        seed_str = f"{image_filename}_{variant}"
        seed = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16) % (2**32)
        
        return {
            "1": {"class_type": "LoadImage", "inputs": {"image": image_filename, "upload": "image"}},
            "2": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"}},
            "3": {"class_type": "VAEEncode", "inputs": {"pixels": ["1", 0], "vae": ["2", 2]}},
            "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 1], "text": POSITIVE_PROMPT}},
            "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 1], "text": NEGATIVE_PROMPT}},
            "6": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed, "steps": params["steps"], "cfg": params["cfg"],
                    "sampler_name": "euler_ancestral", "scheduler": "normal",
                    "denoise": params["denoise"],
                    "model": ["2", 0], "positive": ["4", 0], "negative": ["5", 0],
                    "latent_image": ["3", 0]
                }
            },
            "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["2", 2]}},
            "8": {"class_type": "SaveImage", "inputs": {"filename_prefix": f"calibration_{variant}", "images": ["7", 0]}}
        }
    
    async def submit_workflow(self, workflow: dict) -> str:
        url = f"{COMFYUI_URL}/api/prompt"
        async with self.session.post(url, json={"prompt": workflow}) as resp:
            if resp.status == 200:
                result = await resp.json()
                return result.get('prompt_id')
            else:
                error = await resp.text()
                raise Exception(f"Submit failed: {resp.status} - {error[:100]}")
    
    async def poll_completion(self, prompt_id: str, timeout: int = 600) -> dict:
        url = f"{COMFYUI_URL}/api/history/{prompt_id}"
        import time
        start = time.time()
        while time.time() - start < timeout:
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    history = await resp.json()
                    if prompt_id in history:
                        return history[prompt_id]
            await asyncio.sleep(2)
        raise Exception(f"Timeout after {timeout}s")
    
    async def run_calibration(self, image: str, variant: str, variant_params: dict):
        source_dir = CALIBRATION_DIR
        source_path = source_dir / image
        
        if not source_path.exists():
            print(f"  ✗ Source not found: {source_path}")
            return
        
        print(f"\nRunning {image} variant {variant} (denoise={variant_params['denoise']})")
        
        output_dir = CALIBRATION_DIR / "outputs_basic" / f"pass1_{variant}"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            uploaded_filename = await self.upload_image(source_path)
            print(f"  ✓ Uploaded: {uploaded_filename}")
        except Exception as e:
            print(f"  ✗ Upload failed: {e}")
            return
        
        try:
            workflow = self.build_workflow(uploaded_filename, variant, variant_params)
            prompt_id = await self.submit_workflow(workflow)
            print(f"  ✓ Workflow submitted: {prompt_id}")
        except Exception as e:
            print(f"  ✗ Workflow submission failed: {e}")
            return
        
        try:
            print(f"  Waiting for completion...")
            result = await self.poll_completion(prompt_id)
            outputs = result.get('outputs', {})
            output_filename = None
            for node_id, node_outputs in outputs.items():
                if 'images' in node_outputs:
                    for img_info in node_outputs['images']:
                        output_filename = img_info.get('filename')
                        break
                if output_filename:
                    break
            
            if not output_filename:
                raise Exception("No output images found")
            
            # Download output
            output_url = f"{COMFYUI_URL}/view?filename={output_filename}&subfolder=&type=output"
            output_path = output_dir / output_filename
            async with self.session.get(output_url) as resp:
                if resp.status == 200:
                    with open(output_path, 'wb') as f:
                        f.write(await resp.read())
                    print(f"  ✓ Downloaded: {output_path}")
                    
                    # Run Auto-QC
                    try:
                        from auto_qc import analyze_image
                        metrics, routing = analyze_image(output_path)
                        print(f"  ✓ Auto-QC: {routing}")
                        print(f"    saturation={metrics['mean_saturation']:.4f}")
                        print(f"    highlight_clipping={metrics['highlight_clipping']:.4f}")
                        print(f"    laplacian={metrics['laplacian_variance']:.2f}")
                    except Exception as e:
                        print(f"  ⚠ Auto-QC failed: {e}")
                        metrics = {"routing": "error", "error": str(e)}
            
            self.results.append({
                "image": image, "variant": variant, "params": variant_params,
                "output_path": str(output_path), "prompt_id": prompt_id,
                "status": "completed", "qc_metrics": metrics.get('routing', 'unknown')
            })
        except Exception as e:
            print(f"  ✗ Output handling failed: {e}")
            self.results.append({
                "image": image, "variant": variant, "params": variant_params,
                "status": "failed", "error": str(e)
            })


async def main():
    runner = BasicCalibrationRunner()
    try:
        await runner.connect()
        
        print("=" * 60)
        print("BASIC IMG2IMG CALIBRATION (No ControlNet)")
        print("=" * 60)
        
        for image in TUNING_IMAGES:
            for variant, params in VARIANTS.items():
                await runner.run_calibration(image, variant, params)
        
        results_file = CALIBRATION_DIR / "calibration_results_basic.json"
        with open(results_file, 'w') as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "results": runner.results
            }, f, indent=2, default=str)
        
        print(f"\nResults saved to: {results_file}")
        print(f"Completed: {len([r for r in runner.results if r['status']=='completed'])}/{len(TUNING_IMAGES)*3}")
        
    finally:
        await runner.close()


if __name__ == "__main__":
    asyncio.run(main())
