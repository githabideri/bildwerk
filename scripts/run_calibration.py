#!/usr/bin/env python3
"""
Calibration Runner - Execute ControlNet workflow on specific images

This is a direct calibration script that doesn't rely on the full router pipeline.
It submits workflows directly to ComfyUI API.
"""

import os
import sys
import json
import asyncio
import aiohttp
from pathlib import Path
from datetime import datetime
import hashlib

# Configuration
WORKSPACE = Path("/var/lib/clawdbot/workspace/agents/hgg16/bildwerk")
CALIBRATION_DIR = WORKSPACE / "private" / "interior_passage"
COMFYUI_URL = "http://192.168.0.49:8188"

# Calibration images
TUNING_IMAGES = ["309.jpg", "317.jpg", "324.jpg"]
HOLDOUT_IMAGES = ["330.jpg", "331.jpg"]

# Variant parameters
VARIANTS = {
    "A": {"denoise": 0.38, "cfg": 5.0, "steps": 30},
    "B": {"denoise": 0.42, "cfg": 5.2, "steps": 32},
    "C": {"denoise": 0.45, "cfg": 5.5, "steps": 34},
}

# Prompts
POSITIVE_PROMPT = "present-day color architectural photograph of an interior passage with vaulted ceiling, realistic stone masonry, natural daylight, authentic limestone textures, documentary photography style, warm gray tones, professional architectural photography, high resolution"
NEGATIVE_PROMPT = "black and white, monochrome, sketch, drawing, engraving, illustration, etching, CGI, 3D render, plastic surfaces, washed out, overexposed, distorted geometry, malformed arches, unrealistic textures, text, watermark, low quality"


class CalibrationRunner:
    def __init__(self):
        self.session = None
        self.results = []
        self.running = False
    
    async def connect(self):
        """Initialize ComfyUI connection"""
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=600))
        self.running = True
    
    async def close(self):
        """Close connection"""
        if self.session:
            await self.session.close()
    
    async def upload_image(self, image_path: str) -> str:
        """Upload image to ComfyUI /upload/image endpoint"""
        url = f"{COMFYUI_URL}/upload/image"
        
        with open(image_path, 'rb') as f:
            image_data = f.read()
        
        filename = os.path.basename(image_path)
        
        form = aiohttp.FormData()
        form.add_field('image', image_data, filename=filename, content_type='image/png')
        
        async with self.session.post(url, data=form) as resp:
            if resp.status in [200, 204]:
                return filename
            else:
                error = await resp.text()
                raise Exception(f"Upload failed: {resp.status} - {error[:100]}")
    
    async def submit_workflow(self, workflow: dict) -> str:
        """Submit workflow to ComfyUI /api/prompt"""
        url = f"{COMFYUI_URL}/api/prompt"
        
        async with self.session.post(url, json={"prompt": workflow}) as resp:
            if resp.status == 200:
                result = await resp.json()
                return result.get('prompt_id')
            else:
                error = await resp.text()
                raise Exception(f"Workflow submission failed: {resp.status} - {error[:100]}")
    
    async def poll_completion(self, prompt_id: str, timeout: int = 600) -> dict:
        """Poll for job completion"""
        url = f"{COMFYUI_URL}/api/history/{prompt_id}"
        
        start = datetime.now()
        while datetime.now() - start < timedelta(seconds=timeout):
            try:
                async with self.session.get(url) as resp:
                    if resp.status == 200:
                        history = await resp.json()
                        if prompt_id in history:
                            return history[prompt_id]
                await asyncio.sleep(2)
            except Exception as e:
                print(f"  Poll error: {e}")
                await asyncio.sleep(2)
        
        raise Exception(f"Timeout after {timeout}s")
    
    async def download_output(self, filename: str, subfolder: str, output_dir: str) -> str:
        """Download generated image"""
        url = f"{COMFYUI_URL}/view?filename={filename}&subfolder={subfolder}&type=output"
        
        local_path = Path(output_dir) / filename
        
        async with self.session.get(url) as resp:
            if resp.status == 200:
                with open(local_path, 'wb') as f:
                    f.write(await resp.read())
                return str(local_path)
            else:
                raise Exception(f"Download failed: {resp.status}")
    
    def build_controlnet_workflow(self, image_filename: str, variant: str, params: dict) -> dict:
        """Build ControlNet workflow for Pass 1"""
        
        # Calculate seed from filename and variant for reproducibility
        seed_str = f"{image_filename}_{variant}"
        seed = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16) % (2**32)
        
        workflow = {
            # Load source image
            "1": {
                "class_type": "LoadImage",
                "inputs": {"image": image_filename, "upload": "image"}
            },
            # Load checkpoint
            "2": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"}
            },
            # Encode source image
            "3": {
                "class_type": "VAEEncode",
                "inputs": {
                    "pixels": ["1", 0],
                    "vae": ["2", 2]
                }
            },
            # Load ControlNet
            "4": {
                "class_type": "ControlNetLoader",
                "inputs": {
                    "control_net_name": "controlnet_union_sdxl.safetensors",
                    "model": ["2", 0]
                }
            },
            # Apply ControlNet
            "5": {
                "class_type": "ControlNetApplyAdvanced",
                "inputs": {
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "control_net": ["4", 0],
                    "image": ["1", 0],
                    "strength": 0.75,
                    "start_percent": 0.0,
                    "end_percent": 1.0
                }
            },
            # Positive prompt
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "clip": ["2", 1],
                    "text": POSITIVE_PROMPT
                }
            },
            # Negative prompt
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "clip": ["2", 1],
                    "text": NEGATIVE_PROMPT
                }
            },
            # KSampler with ControlNet guidance
            "8": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed,
                    "steps": params["steps"],
                    "cfg": params["cfg"],
                    "sampler_name": "euler_ancestral",
                    "scheduler": "normal",
                    "denoise": params["denoise"],
                    "model": ["2", 0],
                    "positive": ["5", 0],
                    "negative": ["5", 1],
                    "latent_image": ["3", 0]
                }
            },
            # Decode latent to image
            "9": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["8", 0],
                    "vae": ["2", 2]
                }
            },
            # Save output
            "10": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": f"calibration_{variant}",
                    "images": ["9", 0]
                }
            }
        }
        
        return workflow
    
    async def run_calibration(self, image: str, variant: str, variant_params: dict):
        """Run calibration on a single image/variant combination"""
        
        # Get source image
        source_dir = WORKSPACE / "private" / "interior_passage"
        source_path = source_dir / image
        
        if not source_path.exists():
            print(f"  ✗ Source not found: {source_path}")
            return
        
        print(f"\nRunning {image} variant {variant} (denoise={variant_params['denoise']})")
        
        # Create calibration output directory
        output_dir = CALIBRATION_DIR / "outputs" / f"pass1_{variant}"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Upload source to ComfyUI
        try:
            uploaded_filename = await self.upload_image(source_path)
            print(f"  ✓ Uploaded: {uploaded_filename}")
        except Exception as e:
            print(f"  ✗ Upload failed: {e}")
            return
        
        # Build and submit workflow
        try:
            workflow = self.build_controlnet_workflow(uploaded_filename, variant, variant_params)
            prompt_id = await self.submit_workflow(workflow)
            print(f"  ✓ Workflow submitted: {prompt_id}")
        except Exception as e:
            print(f"  ✗ Workflow submission failed: {e}")
            return
        
        # Poll for completion
        try:
            print(f"  Waiting for completion...")
            result = await self.poll_completion(prompt_id)
            print(f"  ✓ Job completed: {result['status']}")
        except Exception as e:
            print(f"  ✗ Polling failed: {e}")
            return
        
        # Extract output filename from history
        try:
            outputs = result.get('outputs', {})
            output_filename = None
            output_subfolder = None
            
            for node_id, node_outputs in outputs.items():
                if 'images' in node_outputs:
                    for img_info in node_outputs['images']:
                        output_filename = img_info.get('filename')
                        output_subfolder = img_info.get('subfolder', '')
                        break
                if output_filename:
                    break
            
            if not output_filename:
                raise Exception("No output images found")
            
            print(f"  ✓ Output found: {output_filename}")
            
            # Download output
            output_path = await self.download_output(output_filename, output_subfolder, str(output_dir))
            print(f"  ✓ Downloaded: {output_path}")
            
            # Run Auto-QC
            try:
                sys.path.insert(0, str(WORKSPACE / "scripts"))
                from auto_qc import analyze_image
                
                metrics, routing = analyze_image(Path(output_path))
                print(f"  ✓ Auto-QC: {routing}")
                print(f"    saturation={metrics['mean_saturation']:.4f}")
                print(f"    highlight_clipping={metrics['highlight_clipping']:.4f}")
                print(f"    laplacian={metrics['laplacian_variance']:.2f}")
            except Exception as e:
                print(f"  ⚠ Auto-QC failed: {e}")
                metrics = {"routing": "error", "error": str(e)}
            
            # Record result
            result_entry = {
                "image": image,
                "variant": variant,
                "params": variant_params,
                "output_path": output_path,
                "prompt_id": prompt_id,
                "qc_metrics": metrics,
                "status": "completed"
            }
            self.results.append(result_entry)
            
        except Exception as e:
            print(f"  ✗ Output handling failed: {e}")
            self.results.append({
                "image": image,
                "variant": variant,
                "params": variant_params,
                "status": "failed",
                "error": str(e)
            })


async def main():
    """Main calibration runner"""
    
    runner = CalibrationRunner()
    
    try:
        await runner.connect()
        
        print("=" * 60)
        print("INTERIOR PASS CALIBRATION")
        print("=" * 60)
        
        # Test run on 309.jpg first
        print("\n" + "=" * 60)
        print("TEST RUN: 309.jpg variant B")
        print("=" * 60)
        
        await runner.run_calibration("309.jpg", "B", VARIANTS["B"])
        
        if runner.results:
            last_result = runner.results[-1]
            if last_result.get("status") == "completed":
                print("\n✓ Test run SUCCESSFUL")
                print(f"  Output: {last_result.get('output_path')}")
                print(f"  QC: {last_result.get('qc_metrics', {}).get('routing', 'unknown')}")
            else:
                print("\n✗ Test run FAILED")
                print(f"  Error: {last_result.get('error')}")
                print("\nStopping calibration due to failure.")
                return
        else:
            print("\n✗ No results recorded")
            return
        
        # If test succeeded, proceed with full calibration
        print("\n" + "=" * 60)
        print("FULL CALIBRATION LOOP")
        print("=" * 60)
        
        for image in TUNING_IMAGES:
            for variant, params in VARIANTS.items():
                await runner.run_calibration(image, variant, params)
        
        # Save results
        results_file = CALIBRATION_DIR / "calibration_results.json"
        with open(results_file, 'w') as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "results": runner.results
            }, f, indent=2, default=str)
        
        print(f"\nResults saved to: {results_file}")
        
    finally:
        await runner.close()


if __name__ == "__main__":
    asyncio.run(main())
