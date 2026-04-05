#!/usr/bin/env python3
"""
Submit all analyzed images to ComfyUI for processing
"""

import os
import sys
import json
import base64
import requests
import time
from pathlib import Path
from datetime import datetime

# Configuration
INPUT_DIR = Path("/var/lib/clawdbot/workspace/agents/hgg16/Dias-Dichtl")
DESCRIPTIONS_DIR = Path("/var/lib/clawdbot/workspace/agents/hgg16/bildwerk/descriptions")
WORKFLOWS_DIR = Path("/var/lib/clawdbot/workspace/agents/hgg16/bildwerk/workflows")

COMFYUI_URL = "http://192.168.0.15:8189"
COMFYUI_API = f"{COMFYUI_URL}/api"

def load_workflow():
    """Load vedute workflow"""
    workflow_file = WORKFLOWS_DIR / "vedute_sketch_workflow.json"
    with open(workflow_file, 'r') as f:
        return json.load(f)

def load_image_as_base64(image_path):
    """Load image and encode as base64"""
    with open(image_path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')

def submit_to_comfyui(workflow, image_b64, output_prefix):
    """Submit workflow to ComfyUI"""
    # Update workflow with image data
    workflow['5']['inputs']['image'] = image_b64
    workflow['8']['inputs']['filename_prefix'] = f"bildwerk_output/{output_prefix}"
    
    # Update prompts
    workflow['6']['inputs']['text'] = "photorealistic modern city view, high quality, detailed architecture, natural lighting, 8k, professional photography, vibrant colors, realistic textures"
    workflow['7']['inputs']['text'] = "sketch, drawing, pencil, pen, lines, outline, unfinished, low quality, blurry, distorted, text, watermark, signature, annotation, handwriting"
    
    try:
        response = requests.post(
            f"{COMFYUI_API}/prompt",
            json={"prompt": workflow},
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            return result.get('prompt_id')
        else:
            print(f"  ❌ ComfyUI error: {response.status_code}")
            return None
    except Exception as e:
        print(f"  ❌ Submission error: {e}")
        return None

def main():
    # Find all analyzed images
    analysis_files = sorted(DESCRIPTIONS_DIR.glob("*_analysis.json"))
    
    print(f"🎯 Submitting {len(analysis_files)} analyzed images to ComfyUI")
    print(f"🖥️  Target: {COMFYUI_URL}")
    print()
    
    # Load workflow once
    workflow = load_workflow()
    
    start_time = datetime.now()
    submitted = 0
    failed = 0
    
    for i, analysis_file in enumerate(analysis_files, 1):
        # Load analysis
        with open(analysis_file, 'r') as f:
            analysis = json.load(f)
        
        stem = analysis_file.stem.replace("_analysis", "")
        image_path = INPUT_DIR / f"{stem}.jpg"
        
        if not image_path.exists():
            print(f"[{i}/{len(analysis_files)}] {stem}.jpg - skipped (file not found)")
            continue
        
        print(f"[{i}/{len(analysis_files)}] {stem}.jpg")
        print(f"  🚀 Submitting to ComfyUI...")
        
        # Load image
        image_b64 = load_image_as_base64(image_path)
        
        # Submit to ComfyUI
        prompt_id = submit_to_comfyui(workflow, image_b64, stem)
        
        if prompt_id:
            analysis["prompt_id"] = prompt_id
            analysis["status"] = "submitted"
            analysis["submitted_at"] = datetime.now().isoformat()
            
            # Save updated analysis
            with open(analysis_file, 'w') as f:
                json.dump(analysis, f, indent=2)
            
            submitted += 1
            print(f"    ✅ Submitted! Queue ID: {prompt_id}")
        else:
            failed += 1
            print(f"    ❌ Submission failed")
        
        # Small delay between submissions
        time.sleep(1)
    
    # Save summary
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    summary = {
        "submit_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "duration_seconds": duration,
        "total": len(analysis_files),
        "submitted": submitted,
        "failed": failed
    }
    
    summary_file = DESCRIPTIONS_DIR / "comfyui_submission_summary.json"
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print("\n" + "="*60)
    print("✅ Submission complete!")
    print(f"Total: {len(analysis_files)}")
    print(f"Submitted: {submitted}")
    print(f"Failed: {failed}")
    print(f"Duration: {duration/60:.1f} minutes")
    print(f"Results will appear in: /opt/bildwerk/output/ on wgpx15")
    print("="*60)

if __name__ == "__main__":
    main()
