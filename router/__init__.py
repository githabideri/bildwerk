#!/usr/bin/env python3
"""
bildwerk Router - Job orchestration and Nextcloud integration
Full implementation with XML parsing, file processing, and ComfyUI integration
"""

import asyncio
import aiohttp
import aiofiles
import yaml
import json
import os
import sys
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from prometheus_client import start_http_server, Counter, Gauge, Histogram
from typing import Dict, List, Optional
import re

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('bildwerk-router')

# Prometheus metrics
JOBS_RECEIVED = Counter('bildwerk_jobs_received', 'Total jobs received')
JOBS_COMPLETED = Counter('bildwerk_jobs_completed', 'Total jobs completed')
JOBS_FAILED = Counter('bildwerk_jobs_failed', 'Total jobs failed')
JOBS_IN_PROGRESS = Gauge('bildwerk_jobs_in_progress', 'Number of jobs in progress')
JOB_DURATION = Histogram('bildwerk_job_duration_seconds', 'Job duration in seconds')

class RouterConfig:
    def __init__(self, config_path: str):
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        self.nextcloud = self.config['nextcloud']
        self.workers = self.config['workers']
        self.router_config = self.config['router']
        self.presets_path = self.config.get('presets', {}).get('path', '/opt/bildwerk/bildwerk/presets')
        self.backends = self.config.get('backends', {})
        self.prompt_presets = self.config.get('presets', {}).get('prompt_templates', {})
        
        # Load secrets if specified
        secrets_path = config_path.replace('config.yaml', 'secrets/nextcloud.yaml')
        if os.path.exists(secrets_path):
            with open(secrets_path, 'r') as f:
                secrets = yaml.safe_load(f)
            if 'nextcloud' in secrets and 'password' in secrets['nextcloud']:
                self.nextcloud['password'] = secrets['nextcloud']['password']
        
    def get_worker(self, worker_type: str = 'gpu'):
        """Get first available worker of specified type"""
        for worker in self.workers:
            if worker['type'] == worker_type and not worker.get('experimental', False):
                return worker
        # Fallback to any available worker
        return self.workers[0] if self.workers else None
    
    def load_preset(self, preset_name: str) -> dict:
        """Load a preset configuration"""
        preset_file = Path(self.presets_path) / f"{preset_name}.json"
        if preset_file.exists():
            with open(preset_file, 'r') as f:
                return json.load(f)
        logger.warning(f"Preset {preset_name} not found, using default")
        return {}
    
    def get_backend(self, backend_name: str) -> Optional[dict]:
        """Get backend configuration by name"""
        return self.backends.get(backend_name)
    
    def get_prompt_preset(self, preset_name: str) -> str:
        """Get prompt template text by preset name"""
        return self.prompt_presets.get(preset_name, "")
    
    def get_backend_for_preset(self, preset_name: str) -> str:
        """Determine which backend to use for a given preset
        
        Returns backend name from config backends section.
        Default fallback is 'sd_xl' for known SDXL presets, 'flux_klein_local' for others.
        """
        # Known SDXL presets use the SDXL backend
        sd_xl_presets = ['vedute', 'facade', 'portrait', 'interior']
        if any(p in preset_name.lower() for p in sd_xl_presets):
            return 'sd_xl'
        # Default to flux_klein_local for new presets
        return 'flux_klein_local'

class NextcloudClient:
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.session = None
        
    async def connect(self):
        """Initialize connection with increased timeout for large file transfers"""
        self.session = aiohttp.ClientSession(
            auth=aiohttp.BasicAuth(self.username, self.password),
            timeout=aiohttp.ClientTimeout(total=600, connect=30, sock_read=60)
        )
        logger.info(f"Connected to Nextcloud: {self.base_url}")
        
    async def list_folder(self, path: str) -> List[str]:
        """List files in a folder, returns list of filenames"""
        url = f"{self.base_url}/remote.php/dav/files/{self.username}/{path}"
        try:
            async with self.session.request('PROPFIND', url, headers={'Depth': '1'}) as resp:
                xml_content = await resp.text()
                return self._parse_dav_response(xml_content)
        except Exception as e:
            logger.error(f"Error listing folder {path}: {e}")
            return []
    
    def _parse_dav_response(self, xml_content: str) -> List[str]:
        """Parse WebDAV PROPFIND XML response and extract filenames"""
        files = []
        try:
            root = ET.fromstring(xml_content)
            ns = {'d': 'DAV:'}
            
            # Find all response elements
            for response in root.findall('.//d:response', ns):
                href_elem = response.find('d:href', ns)
                if href_elem is None:
                    continue
                
                href = href_elem.text
                # Extract just the filename from the full path
                if href and href.endswith('/'):
                    continue  # Skip directories
                
                filename = href.split('/')[-1]
                if filename:
                    files.append(filename)
        except ET.ParseError as e:
            logger.error(f"XML parse error: {e}")
            # Fallback: try regex
            files = self._parse_dav_response_regex(xml_content)
        
        return files
    
    def _parse_dav_response_regex(self, xml_content: str) -> List[str]:
        """Fallback regex-based parsing for WebDAV responses"""
        # Match filenames in href tags
        pattern = r'<d:href>.*?/files/[^/]+/[^/]+/(.*?)</d:href>'
        matches = re.findall(pattern, xml_content)
        return [m for m in matches if m and not m.endswith('/')]
            
    async def upload_file(self, local_path: str, remote_path: str, max_retries: int = 3) -> bool:
        """Upload a file to Nextcloud with retry logic for transient errors"""
        url = f"{self.base_url}/remote.php/dav/files/{self.username}/{remote_path}"
        
        for attempt in range(max_retries):
            try:
                async with aiofiles.open(local_path, 'rb') as f:
                    data = await f.read()
                logger.debug(f"Uploading {len(data)} bytes to {remote_path} (attempt {attempt+1}/{max_retries})")
                async with self.session.put(url, data=data) as resp:
                    # Nextcloud can return 200 or 204 on success
                    if resp.status in [200, 204]:
                        logger.debug(f"Upload successful on attempt {attempt+1}")
                        return True
                    else:
                        error_text = await resp.text()
                        logger.error(f"Upload failed (attempt {attempt+1}): {resp.status} - {error_text[:200]}")
                        # Non-retryable error (e.g., 403, 404)
                        if resp.status >= 400 and resp.status < 500:
                            return False
            except Exception as e:
                logger.error(f"Upload failed (attempt {attempt+1}/{max_retries}) for {local_path}: {type(e).__name__}: {e}")
                
            # Retry on transient errors
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2  # Exponential backoff: 2s, 4s, 6s
                logger.info(f"Retrying upload in {wait_time}s...")
                await asyncio.sleep(wait_time)
        
        logger.error(f"Upload failed after {max_retries} attempts for {remote_path}")
        return False
            
    async def download_file(self, remote_path: str, local_path: str, max_retries: int = 3) -> bool:
        """Download a file from Nextcloud with retry logic"""
        url = f"{self.base_url}/remote.php/dav/files/{self.username}/{remote_path}"
        
        for attempt in range(max_retries):
            try:
                async with self.session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        os.makedirs(os.path.dirname(local_path), exist_ok=True)
                        async with aiofiles.open(local_path, 'wb') as f:
                            await f.write(data)
                        logger.debug(f"Download successful (attempt {attempt+1}/{max_retries})")
                        return True
                    else:
                        logger.error(f"Download failed (attempt {attempt+1}): {resp.status}")
                        if resp.status >= 400 and resp.status < 500:
                            return False
            except Exception as e:
                logger.error(f"Download failed (attempt {attempt+1}/{max_retries}) for {remote_path}: {type(e).__name__}: {e}")
            
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                logger.info(f"Retrying download in {wait_time}s...")
                await asyncio.sleep(wait_time)
        
        logger.error(f"Download failed after {max_retries} attempts for {remote_path}")
        return False
        
    async def move_file(self, from_path: str, to_path: str) -> bool:
        """Move a file in Nextcloud"""
        from_url = f"{self.base_url}/remote.php/dav/files/{self.username}/{from_path}"
        to_url = f"{self.base_url}/remote.php/dav/files/{self.username}/{to_path}"
        try:
            async with self.session.request('MOVE', from_url, headers={'Destination': to_url}) as resp:
                return resp.status in [201, 204]
        except Exception as e:
            logger.error(f"Move failed {from_path} -> {to_path}: {e}")
            return False
            
    async def close(self):
        """Close connection"""
        if self.session:
            await self.session.close()

class WorkerClient:
    def __init__(self, url: str):
        self.url = url.rstrip('/')
        self.session = None
        
    async def load_workflow_file(self, workflow_path: str) -> dict:
        """Load a workflow JSON file from disk"""
        try:
            with open(workflow_path, 'r') as f:
                workflow = json.load(f)
            logger.debug(f"Loaded workflow from {workflow_path} ({len(workflow)} nodes)")
            return workflow
        except Exception as e:
            logger.error(f"Failed to load workflow file {workflow_path}: {e}")
            raise
    
    def substitute_workflow_params(self, workflow: dict, params: dict) -> dict:
        """Substitute parameters into a workflow JSON
        
        Replaces placeholders like 'INPUT_IMAGE', 'PROMPT_TEXT', 'SEED' with actual values.
        Supports nested dictionary values and list values.
        """
        import copy
        workflow = copy.deepcopy(workflow)
        
        def substitute_value(val):
            if isinstance(val, str):
                # Replace placeholders
                for key, replacement in params.items():
                    placeholder = f"${{{key}}}"
                    if placeholder in val:
                        val = val.replace(placeholder, str(replacement))
                # Also handle simple string replacement for known keys
                if val == "INPUT_IMAGE" and 'input_image' in params:
                    val = params['input_image']
                elif val == "PROMPT_TEXT" and 'prompt' in params:
                    val = params['prompt']
                elif val == "SEED" and 'seed' in params:
                    val = params['seed']
            elif isinstance(val, dict):
                val = {k: substitute_value(v) for k, v in val.items()}
            elif isinstance(val, list):
                val = [substitute_value(item) for item in val]
            return val
        
        return substitute_value(workflow)
        
    async def connect(self):
        """Initialize connection"""
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300))
        
    async def upload_image(self, image_path: str, filename: str) -> Optional[str]:
        """Upload an image to ComfyUI via /upload/image endpoint"""
        try:
            url = f"{self.url}/upload/image"
            async with aiofiles.open(image_path, 'rb') as f:
                image_data = await f.read()
            
            # Create multipart form data
            form = aiohttp.FormData()
            form.add_field('image', image_data, filename=filename, content_type='image/png')
            
            async with self.session.post(url, data=form) as resp:
                if resp.status in [200, 204]:
                    logger.info(f"Uploaded image to ComfyUI: {filename}")
                    return filename
                else:
                    error_text = await resp.text()
                    logger.error(f"Image upload failed: {resp.status} - {error_text}")
                    return None
        except Exception as e:
            logger.error(f"Error uploading image: {e}")
            return None
    
    async def submit_to_comfyui(self, image_path: str, preset: dict) -> Optional[str]:
        """Submit an image to ComfyUI for processing via img2img workflow
        
        Steps:
        1. Upload source image to ComfyUI via /upload/image
        2. Build workflow with LoadImage referencing uploaded filename
        3. Submit prompt via /prompt
        4. Return prompt_id for tracking
        """
        try:
            # Extract filename and upload to ComfyUI
            import os
            original_filename = os.path.basename(image_path)
            uploaded_filename = f"source_{original_filename}"
            
            logger.info(f"Uploading {original_filename} to ComfyUI...")
            uploaded_name = await self.upload_image(image_path, uploaded_filename)
            
            if not uploaded_name:
                logger.error("Failed to upload image to ComfyUI")
                return None
            
            # Build ComfyUI workflow with uploaded image filename
            workflow = self._build_comfyui_workflow(uploaded_name, preset)
            
            # Submit to ComfyUI
            url = f"{self.url}/api/prompt"
            async with self.session.post(url, json={"prompt": workflow}) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    prompt_id = result.get('prompt_id')
                    logger.info(f"Submitted img2img to ComfyUI, prompt_id: {prompt_id}")
                    return prompt_id
                else:
                    error_text = await resp.text()
                    logger.error(f"ComfyUI submission failed: {resp.status} - {error_text}")
                    return None
        except Exception as e:
            logger.error(f"Error submitting to ComfyUI: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def submit_two_stage_workflow(self, input_image_path: str, backend_name: str, 
                                        workflow_file: str, upscale_workflow_file: str,
                                        prompt_text: str, seed: int, 
                                        output_prefix: str = "FLUX_KLEIN") -> dict:
        """Submit a two-stage workflow: generation -> upscale
        
        Args:
            input_image_path: Path to input image (already uploaded to ComfyUI)
            backend_name: Backend name for logging
            workflow_file: Path to generation workflow JSON
            upscale_workflow_file: Path to upscale workflow JSON
            prompt_text: Prompt text for generation
            seed: Random seed for generation
            output_prefix: Filename prefix for output images
        
        Returns:
            dict with stage results:
            {
                'stage_a': {'success': bool, 'prompt_id': str, 'output_filename': str},
                'stage_b': {'success': bool, 'prompt_id': str, 'output_filename': str},
                'final_output': str,
                'intermediate_output': str
            }
        """
        import random
        
        result = {
            'stage_a': {'success': False, 'prompt_id': None, 'output_filename': None},
            'stage_b': {'success': False, 'prompt_id': None, 'output_filename': None},
            'final_output': None,
            'intermediate_output': None
        }
        
        # Stage A: Generation
        logger.info(f"Stage A: Generating with {backend_name}...")
        try:
            # Load generation workflow
            generation_workflow = await self.load_workflow_file(workflow_file)
            
            # Substitute parameters
            params = {
                'input_image': input_image_path,
                'prompt': prompt_text,
                'seed': seed if seed != -1 else random.randint(0, 2**32 - 1)
            }
            workflow = self.substitute_workflow_params(generation_workflow, params)
            
            # Submit generation
            url = f"{self.url}/api/prompt"
            async with self.session.post(url, json={"prompt": workflow}) as resp:
                if resp.status == 200:
                    gen_result = await resp.json()
                    gen_prompt_id = gen_result.get('prompt_id')
                    logger.info(f"Stage A submitted: prompt_id={gen_prompt_id}")
                    
                    # Poll for completion
                    gen_job_data = await self.poll_history(gen_prompt_id, timeout=600)
                    if not gen_job_data:
                        raise Exception("Stage A: Generation timed out")
                    
                    # Extract output filename from history
                    outputs = gen_job_data.get('outputs', {})
                    gen_output_filename = None
                    gen_subfolder = None
                    for node_id, node_outputs in outputs.items():
                        if 'images' in node_outputs:
                            for img_info in node_outputs['images']:
                                gen_output_filename = img_info.get('filename')
                                gen_subfolder = img_info.get('subfolder', '')
                                logger.info(f"Stage A output: {gen_output_filename} (subfolder={gen_subfolder})")
                                break
                        if gen_output_filename:
                            break
                    
                    if not gen_output_filename:
                        raise Exception("Stage A: No output images found")
                    
                    result['stage_a'] = {
                        'success': True,
                        'prompt_id': gen_prompt_id,
                        'output_filename': gen_output_filename,
                        'subfolder': gen_subfolder
                    }
                    result['intermediate_output'] = gen_output_filename
                    
                    # Stage B: Upscale
                    logger.info(f"Stage B: Upscaling intermediate image...")
                    
                    # Load upscale workflow
                    upscale_workflow = await self.load_workflow_file(upscale_workflow_file)
                    
                    # Substitute parameters - upscale uses the generation output
                    upscale_params = {
                        'input_image': gen_output_filename,
                    }
                    upscale_workflow = self.substitute_workflow_params(upscale_workflow, upscale_params)
                    
                    # Submit upscale
                    async with self.session.post(url, json={"prompt": upscale_workflow}) as resp:
                        if resp.status == 200:
                            ups_result = await resp.json()
                            ups_prompt_id = ups_result.get('prompt_id')
                            logger.info(f"Stage B submitted: prompt_id={ups_prompt_id}")
                            
                            # Poll for completion
                            ups_job_data = await self.poll_history(ups_prompt_id, timeout=300)
                            if not ups_job_data:
                                raise Exception("Stage B: Upscale timed out")
                            
                            # Extract output filename
                            outputs = ups_job_data.get('outputs', {})
                            ups_output_filename = None
                            ups_subfolder = None
                            for node_id, node_outputs in outputs.items():
                                if 'images' in node_outputs:
                                    for img_info in node_outputs['images']:
                                        ups_output_filename = img_info.get('filename')
                                        ups_subfolder = img_info.get('subfolder', '')
                                        logger.info(f"Stage B output: {ups_output_filename}")
                                        break
                                if ups_output_filename:
                                    break
                            
                            if not ups_output_filename:
                                raise Exception("Stage B: No output images found")
                            
                            result['stage_b'] = {
                                'success': True,
                                'prompt_id': ups_prompt_id,
                                'output_filename': ups_output_filename,
                                'subfolder': ups_subfolder
                            }
                            result['final_output'] = ups_output_filename
                        else:
                            error_text = await resp.text()
                            logger.error(f"Stage B submission failed: {resp.status} - {error_text[:200]}")
                else:
                    error_text = await resp.text()
                    logger.error(f"Stage A submission failed: {resp.status} - {error_text[:200]}")
            return result
        except Exception as e:
            logger.error(f"Two-stage workflow failed: {e}")
            import traceback
            traceback.print_exc()
            result['stage_a']['success'] = False
            result['stage_a']['error'] = str(e)
            return result
    
    def _build_comfyui_workflow(self, image_filename: str, preset: dict) -> dict:
        """Build a ComfyUI img2img workflow based on preset configuration
        
        This is a minimal img2img workflow that:
        - Loads the source image from uploaded filename
        - Encodes it to latent space using VAE from checkpoint
        - Applies denoising with KSampler (denoise < 1.0 for img2img)
        - Decodes back to image space
        - Saves with explicit filename_prefix
        
        Node graph:
        LoadImage(1) -> VAEEncode(3) -> KSampler(4) -> VAEDecode(6) -> SaveImage(8)
        CheckpointLoader(2) -> provides model, clip, vae to above nodes
        CLIPTextEncode(5,7) -> positive/negative prompts to KSampler
        
        Args:
            image_filename: Filename of image uploaded to ComfyUI via /upload/image
            preset: Preset configuration dict
        """
        import random
        
        # Use VAE from checkpoint loader, not separate VAELoader
        # Denoise between 0.35-0.55 for "preserve composition but modernize"
        denoise = preset.get('generation_params', {}).get('denoise', 0.45)
        
        # Seed: -1 means random, but ComfyUI needs 0-2^32-1, so generate random
        seed_config = preset.get('generation_params', {}).get('seed', -1)
        if seed_config == -1:
            seed = random.randint(0, 2**32 - 1)
        else:
            seed = seed_config
        
        workflow = {
            # Load the source image from uploaded filename
            "1": {
                "class_type": "LoadImage",
                "inputs": {
                    "image": image_filename,
                    "upload": "image"
                }
            },
            # Load checkpoint (provides model, clip, and vae)
            "2": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": preset.get('model_config', {}).get('base', 'sd_xl_base_1.0.safetensors')
                }
            },
            # Encode source image to latent space using VAE from checkpoint
            "3": {
                "class_type": "VAEEncode",
                "inputs": {
                    "pixels": ["1", 0],
                    "vae": ["2", 2]  # vae output from CheckpointLoaderSimple
                }
            },
            # KSampler for img2img (denoise < 1.0)
            "4": {
                "class_type": "KSampler",
                "inputs": {
                    "cfg": preset.get('generation_params', {}).get('cfg_scale', 7.5),
                    "denoise": denoise,
                    "latent_image": ["3", 0],  # encoded source image, NOT EmptyLatentImage
                    "model": ["2", 0],  # model from CheckpointLoaderSimple
                    "negative": ["7", 0],
                    "positive": ["5", 0],
                    "sampler_name": preset.get('generation_params', {}).get('sampler', 'euler'),
                    "scheduler": preset.get('generation_params', {}).get('scheduler', 'normal'),
                    "seed": seed,
                    "steps": preset.get('generation_params', {}).get('steps', 20)
                }
            },
            # Positive prompt
            "5": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "clip": ["2", 1],  # clip from CheckpointLoaderSimple
                    "text": preset.get('prompt_templates', {}).get('positive', 'photorealistic modern building facade, high quality, detailed architecture, natural lighting, 8k')
                }
            },
            # Decode latent to image using VAE from checkpoint
            "6": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["4", 0],
                    "vae": ["2", 2]  # vae output from CheckpointLoaderSimple
                }
            },
            # Negative prompt
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "clip": ["2", 1],  # clip from CheckpointLoaderSimple
                    "text": preset.get('prompt_templates', {}).get('negative', 'drawing, painting, sketch, illustration, low quality, blurry, distorted, text, watermark')
                }
            },
            # Save with explicit filename_prefix
            "8": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": "BILDWORK_IMG2IMG",
                    "images": ["6", 0]
                }
            }
        }
        
        return workflow
    
    async def poll_history(self, prompt_id: str, timeout: int = 300) -> Optional[dict]:
        """Poll ComfyUI history until job completes or timeout
        
        Returns the full history entry for the prompt_id, or None on timeout
        """
        url = f"{self.url}/api/history/{prompt_id}"
        import time
        start = time.time()
        
        logger.info(f"Polling for job completion: {prompt_id}")
        
        while time.time() - start < timeout:
            try:
                async with self.session.get(url) as resp:
                    if resp.status == 200:
                        history = await resp.json()
                        if prompt_id in history:
                            job_data = history[prompt_id]
                            status = job_data.get('status', {})
                            status_str = status.get('status_str', 'unknown')
                            
                            if status_str == 'success':
                                logger.info(f"Job {prompt_id} completed successfully")
                                return job_data
                            elif status_str == 'error':
                                logger.error(f"Job {prompt_id} failed: {job_data}")
                                return None
                            else:
                                # running, pending, etc.
                                await asyncio.sleep(2)
                                continue
                        else:
                            # Job not yet in history
                            await asyncio.sleep(2)
                    else:
                        logger.warning(f"History check failed: {resp.status}")
                        await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Error polling history: {e}")
                await asyncio.sleep(2)
        
        logger.error(f"Job {prompt_id} timed out after {timeout}s")
        return None
    
    async def download_output(self, filename: str, subfolder: str, img_type: str, local_path: str) -> bool:
        """Download generated image via /view endpoint
        
        Args:
            filename: Exact filename from history output
            subfolder: Subfolder from history output (usually empty)
            img_type: Type from history output (usually 'output')
            local_path: Where to save locally
        """
        url = f"{self.url}/view?filename={filename}&subfolder={subfolder}&type={img_type}"
        try:
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    # Ensure parent directory exists
                    Path(local_path).parent.mkdir(parents=True, exist_ok=True)
                    with open(local_path, 'wb') as f:
                        f.write(data)
                    logger.info(f"Downloaded output to {local_path} ({len(data)} bytes)")
                    return True
                else:
                    logger.error(f"Output download failed: {resp.status}")
                    return False
        except Exception as e:
            logger.error(f"Error downloading output: {e}")
            return False
    
    async def close(self):
        """Close connection"""
        if self.session:
            await self.session.close()

class Router:
    def __init__(self, config_path: str):
        self.config = RouterConfig(config_path)
        self.nextcloud = None
        self.worker = None
        self.running = False
        self.temp_dir = Path(config_path).parent / "temp"
        self.temp_dir.mkdir(exist_ok=True)
        # Track completed jobs to prevent reprocessing
        self.completed_jobs = set()
        # Load completed jobs from marker file if exists
        self.completed_marker = self.temp_dir / "completed_jobs.txt"
        if self.completed_marker.exists():
            with open(self.completed_marker, 'r') as f:
                self.completed_jobs = set(line.strip() for line in f if line.strip())
            logger.info(f"Loaded {len(self.completed_jobs)} completed job markers")
        
        # Load classification manifest (optional)
        self.classification_manifest = None
        self._load_classification_manifest()
    
    def _load_classification_manifest(self):
        """Load classification manifest and overrides from workspace.
        
        Resolution order:
        1. overrides.json (manual corrections)
        2. manifest.corrected.json (corrected classification)
        """
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from router.manifest_router import (
            load_classification_manifest, 
            load_overrides,
            get_bucket_stats,
            DEFAULT_MANIFEST_PATH
        )
        
        # Load corrected manifest (mandatory)
        manifest_path = Path(DEFAULT_MANIFEST_PATH)
        
        if manifest_path.exists():
            try:
                self.classification_manifest = load_classification_manifest(str(manifest_path))
                logger.info(f"Loaded corrected manifest: {len(self.classification_manifest)} files")
            except Exception as e:
                logger.warning(f"Failed to load corrected manifest: {e}")
                self.classification_manifest = None
        else:
            logger.warning(f"Corrected manifest NOT FOUND at {manifest_path}")
            self.classification_manifest = None
        
        # Load overrides (optional)
        self.classification_overrides = {}
        from router.manifest_router import get_overrides_path
        overrides_path = get_overrides_path()
        if overrides_path.exists():
            try:
                self.classification_overrides = load_overrides(str(overrides_path))
                logger.info(f"Loaded {len(self.classification_overrides)} manual overrides")
            except Exception as e:
                logger.warning(f"Failed to load overrides: {e}")
        else:
            logger.info("No overrides.json found (optional)")
        
    async def start(self):
        """Start the router with startup diagnostics"""
        logger.info("Starting bildwerk router...")
        
        # Startup diagnostics
        logger.info("="*60)
        logger.info("STARTUP DIAGNOSTICS")
        logger.info("="*60)
        logger.info(f"Nextcloud base URL: {self.config.nextcloud['base_url']}")
        logger.info(f"Nextcloud username: {self.config.nextcloud['username']}")
        logger.info(f"Nextcloud folders.base: {self.config.nextcloud['folders']['base']}")
        
        # Report classification manifest status
        if self.classification_manifest:
            from router.manifest_router import get_bucket_stats
            stats = get_bucket_stats(self.classification_manifest)
            logger.info(f"Classification manifest: ✅ Loaded ({len(self.classification_manifest)} files)")
            for bucket, count in sorted(stats.items()):
                logger.info(f"  - {bucket}: {count} files")
        else:
            logger.info("Classification manifest: ⚠️  Not loaded (will use default preset)")
        
        # Test WebDAV connectivity
        base_path = self.config.nextcloud['folders']['base']
        webdav_root = f"{self.config.nextcloud['base_url']}/remote.php/dav/files/{self.config.nextcloud['username']}/{base_path}/"
        logger.info(f"WebDAV root: {webdav_root}")
        
        # Connect to Nextcloud
        self.nextcloud = NextcloudClient(
            self.config.nextcloud['base_url'],
            self.config.nextcloud['username'],
            self.config.nextcloud.get('password', '')
        )
        
        try:
            await self.nextcloud.connect()
            logger.info("Nextcloud connection: ✅ OK")
            
            # Test PROPFIND
            test_result = await self.nextcloud.list_folder(base_path)
            logger.info(f"Nextcloud PROPFIND test: ✅ OK (found {len(test_result)} items)")
            if test_result:
                logger.info(f"Sample items: {test_result[:3]}")
        except Exception as e:
            logger.error(f"Nextcloud PROPFIND test: ❌ FAILED - {type(e).__name__}: {e}")
            raise
        
        logger.info("="*60)
        
        # Connect to GPU worker
        gpu_worker = self.config.get_worker('gpu')
        if gpu_worker:
            self.worker = WorkerClient(gpu_worker['url'])
            await self.worker.connect()
            logger.info(f"Connected to GPU worker: {gpu_worker['name']} at {gpu_worker['url']}")
        else:
            logger.warning("No GPU worker configured!")
        
        # Start metrics server
        try:
            start_http_server(8081)
            logger.info("Prometheus metrics server started on port 8081")
        except OSError as e:
            logger.warning(f"Could not start metrics server: {e}")
        
        self.running = True
        logger.info("Router started successfully")
        
    async def process_file(self, filename: str):
        """Process a single file from inbox - FULL LIFECYCLE
        
        Steps:
        1. Move from inbox to processing
        2. Download source locally
        3. Submit to worker (upload + prompt)
        4. Poll for completion
        5. Extract output metadata from history
        6. Download generated output
        7. Create sidecar.json
        8. Upload output + sidecar to done/
        9. Mark job completed
        """
        import hashlib
        
        base_path = self.config.nextcloud['folders']['base']
        inbox_folder = self.config.nextcloud['folders']['inbox']
        processing_folder = self.config.nextcloud['folders']['processing']
        done_folder = self.config.nextcloud['folders']['done']
        error_folder = self.config.nextcloud['folders']['error']
        
        inbox_path = f"{base_path}/{inbox_folder}/{filename}"
        processing_path = f"{base_path}/{processing_folder}/{filename}"
        
        # Skip if already completed
        if filename in self.completed_jobs:
            logger.info(f"Skipping {filename} - already completed")
            return True
        
        logger.info(f"Processing file: {filename}")
        JOBS_RECEIVED.inc()
        JOBS_IN_PROGRESS.inc()
        
        local_path = None
        prompt_id = None
        started_at = datetime.now().isoformat()
        
        try:
            # Step 1: Move to processing
            logger.info(f"Moving {filename} to processing...")
            if not await self.nextcloud.move_file(inbox_path, processing_path):
                logger.error(f"Failed to move {filename} to processing")
                return False
            
            # Step 2: Download source locally
            local_path = self.temp_dir / filename
            logger.info(f"Downloading {filename}...")
            if not await self.nextcloud.download_file(processing_path, str(local_path)):
                logger.error(f"Failed to download {filename}")
                await self.nextcloud.move_file(processing_path, f"{base_path}/{error_folder}/{filename}")
                return False
            
            # Calculate source hash
            with open(local_path, 'rb') as f:
                source_sha256 = hashlib.sha256(f.read()).hexdigest()
            
            # Step 3: Load preset and submit to worker
            # Route file to preset based on classification (if manifest available)
            # Resolution order: overrides.json → manifest.corrected.json → fallback
            preset_name = 'vedute'  # Default fallback
            requires_review = False
            
            if self.classification_manifest:
                from router.manifest_router import route_file
                preset_name, requires_review = route_file(
                    filename, 
                    self.classification_manifest,
                    self.classification_overrides
                )
                if preset_name is None:
                    logger.warning(f"{filename}: No preset from classification, flagging for review")
                    preset_name = 'vedute'  # Fallback to default
                else:
                    logger.info(f"{filename}: Routed to preset {preset_name} (review: {requires_review})")
            else:
                logger.warning(f"{filename}: Using default preset (no corrected manifest loaded)")
            
            preset = self.config.load_preset(preset_name)
            
            # Determine backend for this preset
            backend_name = self.config.get_backend_for_preset(preset_name)
            backend_config = self.config.get_backend(backend_name)
            
            if self.worker:
                logger.info(f"Submitting {filename} to worker using backend: {backend_name}")
                
                # Check if this backend requires two-stage workflow
                if backend_config and backend_config.get('two_stage', False):
                    # Two-stage: generation + upscale
                    workflow_file = Path(__file__).parent.parent / 'workflows' / backend_config.get('workflow_file')
                    upscale_workflow_file = Path(__file__).parent.parent / 'workflows' / backend_config.get('upscale_workflow_file')
                    
                    # Get prompt text from preset or prompt_templates
                    prompt_text = preset.get('prompt_templates', {}).get('positive', '')
                    if not prompt_text:
                        prompt_text = self.config.get_prompt_preset(preset_name)
                    
                    # Get seed from preset or generation_params
                    seed = preset.get('generation_params', {}).get('seed', -1)
                    
                    # Upload input image to ComfyUI first
                    uploaded_filename = await self.worker.upload_image(str(local_path), f"input_{filename}")
                    if not uploaded_filename:
                        raise Exception("Failed to upload input image")
                    
                    # Submit two-stage workflow
                    stage_result = await self.worker.submit_two_stage_workflow(
                        input_image_path=uploaded_filename,
                        backend_name=backend_name,
                        workflow_file=str(workflow_file),
                        upscale_workflow_file=str(upscale_workflow_file),
                        prompt_text=prompt_text,
                        seed=seed,
                        output_prefix=f"{preset_name.upper()}_{filename.replace('.png', '').replace('.jpg', '')}"
                    )
                    
                    if not stage_result['stage_a']['success']:
                        raise Exception(f"Stage A (generation) failed: {stage_result['stage_a'].get('error', 'unknown')}")
                    
                    if not stage_result['stage_b']['success']:
                        raise Exception(f"Stage B (upscale) failed: {stage_result['stage_b'].get('error', 'unknown')}")
                    
                    # Use final output
                    output_filename = stage_result['final_output']
                    output_subfolder = stage_result['stage_b'].get('subfolder', '')
                    prompt_id = stage_result['stage_b']['prompt_id']
                    finished_at = datetime.now().isoformat()
                else:
                    # Single-stage: use existing method
                    prompt_id = await self.worker.submit_to_comfyui(str(local_path), preset)
                    
                    if not prompt_id:
                        raise Exception("Failed to submit to worker")
                    
                    logger.info(f"Job submitted: prompt_id={prompt_id}")
                    
                    # Poll for completion
                    logger.info(f"Polling for job completion...")
                    job_data = await self.worker.poll_history(prompt_id, timeout=300)
                    
                    if not job_data:
                        raise Exception("Job failed or timed out")
                    
                    finished_at = datetime.now().isoformat()
            else:
                raise Exception("No worker available")
            
            # Step 4 continued: Extract output metadata from history
            # (For two-stage, output is already known from stage_result)
            if backend_config and backend_config.get('two_stage', False):
                outputs = None  # Already have output from stage_result
            else:
                logger.info(f"Polling for job completion...")
                job_data = await self.worker.poll_history(prompt_id, timeout=300)
                
                if not job_data:
                    raise Exception("Job failed or timed out")
                
                outputs = job_data.get('outputs', {})
            
            # Step 5: Extract output metadata from history
            outputs = job_data.get('outputs', {})
            output_filename = None
            output_subfolder = None
            output_type = None
            
            for node_id, node_outputs in outputs.items():
                if 'images' in node_outputs:
                    for img_info in node_outputs['images']:
                        output_filename = img_info.get('filename')
                        output_subfolder = img_info.get('subfolder', '')
                        output_type = img_info.get('type', 'output')
                        logger.info(f"Found output: {output_filename} (subfolder={output_subfolder}, type={output_type})")
                        break
                if output_filename:
                    break
            
            if not output_filename:
                raise Exception("No output images found in history")
            
            # Step 6: Download generated output
            output_local = self.temp_dir / "out" / output_filename
            logger.info(f"Downloading output {output_filename}...")
            if not await self.worker.download_output(output_filename, output_subfolder, output_type, str(output_local)):
                raise Exception("Failed to download output")
            
            # Calculate output hash
            with open(output_local, 'rb') as f:
                output_sha256 = hashlib.sha256(f.read()).hexdigest()
            
            # Step 7: Create sidecar.json
            # Determine backend name (for two-stage, backend_name is already determined)
            backend_used = backend_name if 'backend_name' in locals() else "comfyui"
            
            # Two-stage specific fields
            intermediate_image = None
            final_image = output_filename
            
            if 'stage_result' in locals() and stage_result['stage_a']['success']:
                intermediate_image = stage_result['intermediate_output']
            
            sidecar = {
                "job_id": prompt_id,
                "source_filename": filename,
                "source_remote_path": f"{base_path}/{done_folder}/{filename}",
                "output_filename": output_filename,
                "intermediate_image": intermediate_image,
                "final_image": final_image,
                "preset": preset_name,
                "requires_review": requires_review,
                "review_reason": "classification_low_confidence" if requires_review else None,
                "backend": backend_used,
                "worker": self.config.get_worker('gpu')['name'] if self.config.get_worker('gpu') else "unknown",
                "model": preset.get('model_config', {}).get('base', 'sd_xl_base_1.0.safetensors'),
                "prompt_id": prompt_id,
                "started_at": started_at,
                "finished_at": finished_at,
                "status": "completed",
                "source_sha256": source_sha256,
                "output_sha256": output_sha256,
                # Two-stage metadata
                "backend_config": backend_name if 'backend_name' in locals() else None,
                "stages": {
                    "generation": {
                        "success": True,  # Will be updated if two-stage
                        "prompt_id": prompt_id,
                        "workflow": backend_config.get('workflow_file', 'N/A') if backend_config else 'N/A'
                    },
                    "upscale": {
                        "success": True,  # Will be updated if two-stage
                        "prompt_id": prompt_id,
                        "workflow": backend_config.get('upscale_workflow_file', 'N/A') if backend_config else 'N/A'
                    }
                }
            }
            
            # Update stage results for two-stage workflows
            if 'stage_result' in locals():
                sidecar['stages']['generation']['success'] = stage_result['stage_a']['success']
                sidecar['stages']['upscale']['success'] = stage_result['stage_b']['success']
                if not stage_result['stage_a']['success']:
                    sidecar['stages']['generation']['error'] = stage_result['stage_a'].get('error', 'unknown')
                if not stage_result['stage_b']['success']:
                    sidecar['stages']['upscale']['error'] = stage_result['stage_b'].get('error', 'unknown')
            
            sidecar_path = self.temp_dir / "out" / f"{Path(output_filename).stem}_sidecar.json"
            with open(sidecar_path, 'w') as f:
                json.dump(sidecar, f, indent=2)
            logger.info(f"Created sidecar: {sidecar_path}")
            
            # Step 7.5: Run auto-QC and determine routing
            try:
                from router.auto_qc import run_auto_qc, should_route_to_review
                qc_result = run_auto_qc(str(output_local))
                sidecar['qc_metrics'] = qc_result['metrics']
                sidecar['qc_passes'] = qc_result['passes']
                
                if qc_result['passes']:
                    logger.info(f"Auto-QC: ✅ PASS")
                    target_folder = done_folder
                else:
                    logger.warning(f"Auto-QC: ⚠️ FAIL - {'; '.join(qc_result['reasons'])}")
                    sidecar['review_reasons'] = qc_result['reasons']
                    sidecar['requires_review'] = True
                    target_folder = 'review'
                
                # Save updated sidecar
                with open(sidecar_path, 'w') as f:
                    json.dump(sidecar, f, indent=2)
            except Exception as e:
                logger.warning(f"Auto-QC failed: {e}, routing to done/ by default")
                target_folder = done_folder
            
            # Step 8: Upload output and sidecar to Nextcloud
            logger.info(f"Uploading output to Nextcloud ({target_folder}/)...")
            output_remote = f"{base_path}/{target_folder}/{output_filename}"
            if not await self.nextcloud.upload_file(str(output_local), output_remote):
                logger.error(f"Failed to upload output to {output_remote}")
                raise Exception("Failed to upload output")
            
            sidecar_remote = f"{base_path}/{target_folder}/{Path(output_filename).stem}_sidecar.json"
            logger.info(f"Uploading sidecar to Nextcloud...")
            if not await self.nextcloud.upload_file(str(sidecar_path), sidecar_remote):
                logger.error(f"Failed to upload sidecar to {sidecar_remote}")
                raise Exception("Failed to upload sidecar")
            
            # Step 9: Mark job as completed
            self.completed_jobs.add(filename)
            with open(self.completed_marker, 'a') as f:
                f.write(filename + '\n')
            logger.info(f"Marked {filename} as completed")
            
            # Move source to target folder (keep for reference)
            target_source_path = f"{base_path}/{target_folder}/{filename}"
            await self.nextcloud.move_file(processing_path, target_source_path)
            
            JOBS_COMPLETED.inc()
            logger.info(f"✅ File {filename} processed successfully!")
            logger.info(f"   Output: {output_remote}")
            logger.info(f"   Sidecar: {sidecar_remote}")
            logger.info(f"   Target folder: {target_folder}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error processing {filename}: {e}")
            import traceback
            traceback.print_exc()
            JOBS_FAILED.inc()
            try:
                # Move back to error if in processing
                error_path = f"{base_path}/{error_folder}/{filename}"
                if local_path and local_path.exists():
                    # Check if still in processing
                    await self.nextcloud.move_file(processing_path, error_path)
            except:
                pass
            return False
        finally:
            JOBS_IN_PROGRESS.dec()
            # Clean up local temp files
            try:
                if local_path and local_path.exists():
                    local_path.unlink()
                output_dir = self.temp_dir / "out"
                if output_dir.exists():
                    import shutil
                    shutil.rmtree(output_dir)
            except:
                pass
            
    async def poll_inbox(self):
        """Poll Nextcloud inbox for new files, skipping completed jobs"""
        base_path = self.config.nextcloud['folders']['base']
        inbox_folder = self.config.nextcloud['folders']['inbox']
        inbox_full_path = f"{base_path}/{inbox_folder}"
        poll_interval = self.config.router_config.get('poll_interval_seconds', 30)
        
        logger.info(f"Starting inbox polling: {inbox_full_path} (every {poll_interval}s)")
        
        while self.running:
            try:
                files = await self.nextcloud.list_folder(inbox_full_path)
                
                if files:
                    # Filter out completed jobs
                    pending_files = [f for f in files if f not in self.completed_jobs]
                    
                    if pending_files:
                        logger.info(f"Found {len(pending_files)} pending file(s): {pending_files}")
                        if len(files) != len(pending_files):
                            skipped = len(files) - len(pending_files)
                            logger.info(f"Skipped {skipped} completed job(s)")
                        
                        # Process files one by one
                        for filename in pending_files:
                            if self.running:
                                await self.process_file(filename)
                            else:
                                break
                    else:
                        logger.debug("No pending files in inbox")
                else:
                    logger.debug("No files in inbox")
                    
            except Exception as e:
                logger.error(f"Error polling inbox: {e}")
                
            await asyncio.sleep(poll_interval)
            
    async def stop(self):
        """Stop the router and save completed jobs marker"""
        logger.info("Stopping router...")
        self.running = False
        
        # Save completed jobs to marker file
        with open(self.completed_marker, 'w') as f:
            for filename in sorted(self.completed_jobs):
                f.write(filename + '\n')
        logger.info(f"Saved {len(self.completed_jobs)} completed job markers")
        
        if self.nextcloud:
            await self.nextcloud.close()
            
        if self.worker:
            await self.worker.close()
            
        logger.info("Router stopped")

async def main():
    config_path = os.environ.get('BILDWORK_CONFIG', '/opt/bildwerk/router/config.yaml')
    
    if not os.path.exists(config_path):
        logger.error(f"Config file not found: {config_path}")
        sys.exit(1)
        
    router = Router(config_path)
    
    try:
        await router.start()
        await router.poll_inbox()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await router.stop()

if __name__ == '__main__':
    asyncio.run(main())
