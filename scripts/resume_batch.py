#!/usr/bin/env python3
"""
Resume batch processing - submit remaining images to ComfyUI
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
OUTPUT_DIR = Path("/var/lib/clawdbot/workspace/agents/hgg16/bildwerk/output")
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
            print(f"  ❌ ComfyUI error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"  ❌ Submission error: {e}")
        return None

def main():
    # Find all images
    image_files = sorted(list(INPUT_DIR.glob("*.jpg")) + 
                         list(INPUT_DIR.glob("*.jpeg")) + 
                         list(INPUT_DIR.glob("*.png")))
    
    # Check which images have already been analyzed
    analyzed = set()
    for f in DESCRIPTIONS_DIR.glob("*_analysis.json"):
        stem = f.stem.replace("_analysis", "")
        analyzed.add(stem)
    
    # Load workflow once
    workflow = load_workflow()
    
    print(f"🎯 Resuming batch processing")
    print(f"📁 Total images: {len(image_files)}")
    print(f"📝 Already analyzed: {len(analyzed)}")
    print(f"⏳ Remaining: {len(image_files) - len(analyzed)}")
    print()
    
    start_time = datetime.now()
    results = []
    
    for i, image_path in enumerate(image_files, 1):
        stem = image_path.stem
        
        # Skip if already analyzed
        if stem in analyzed:
            print(f"[{i}/{len(image_files)}] {image_path.name} - skipped (already analyzed)")
            continue
        
        print(f"[{i}/{len(image_files)}] {image_path.name}")
        
        # Analyze and determine preset
        preset = "vedute"  # Default for all
        print(f"  📝 Analyzing: {stem} → {preset}")
        
        # Save analysis
        analysis = {
            "filename": image_path.name,
            "source_path": str(image_path),
            "preset": preset,
            "timestamp": datetime.now().isoformat()
        }
        
        analysis_file = DESCRIPTIONS_DIR / f"{stem}_analysis.json"
        with open(analysis_file, 'w') as f:
            json.dump(analysis, f, indent=2)
        
        # Load image
        image_b64 = load_image_as_base64(image_path)
        
        # Submit to ComfyUI
        print(f"  🚀 Submitting to ComfyUI...")
        prompt_id = submit_to_comfyui(workflow, image_b64, stem)
        
        if prompt_id:
            analysis["prompt_id"] = prompt_id
            analysis["status"] = "submitted"
            print(f"    ✅ Submitted! Queue ID: {prompt_id}")
        else:
            analysis["status"] = "failed"
            print(f"    ❌ Submission failed")
        
        results.append(analysis)
        
        # Small delay between submissions
        time.sleep(2)
    
    # Save summary
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    summary = {
        "resume_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "duration_seconds": duration,
        "processed": len(results),
        "results": results
    }
    
    summary_file = DESCRIPTIONS_DIR / "processing_resume_summary.json"
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print("\n" + "="*60)
    print(f"✅ Resume complete! Processed {len(results)} images")
    print(f"Duration: {duration/60:.1f} minutes")
    print(f"Summary: {summary_file}")
    print("="*60)

if __name__ == "__main__":
    main()
