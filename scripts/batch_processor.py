#!/usr/bin/env python3
"""
Bildwerk Batch Processor - Process all 122 Dias-Dichtl images
This script orchestrates the entire workflow:
1. Analyze each image with vision model
2. Set appropriate preset based on analysis
3. Submit to ComfyUI for processing
4. Collect and organize results
"""

import os
import sys
import json
import base64
import requests
import time
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess

# Configuration
INPUT_DIR = Path("/var/lib/clawdbot/workspace/agents/hgg16/Dias-Dichtl")
OUTPUT_DIR = Path("/var/lib/clawdbot/workspace/agents/hgg16/bildwerk/output")
DESCRIPTIONS_DIR = Path("/var/lib/clawdbot/workspace/agents/hgg16/bildwerk/descriptions")
WORKFLOWS_DIR = Path("/var/lib/clawdbot/workspace/agents/hgg16/bildwerk/workflows")

COMFYUI_URL = "http://192.168.0.15:8189"  # wgpx15, port 8189
COMFYUI_API = f"{COMFYUI_URL}/api"

# Preset configurations
PRESETS = {
    "vedute": {
        "workflow": "vedute_sketch_workflow.json",
        "positive_prompt": "photorealistic modern city view, high quality, detailed architecture, natural lighting, 8k, professional photography",
        "negative_prompt": "sketch, drawing, pencil, lines, unfinished, low quality, blurry, distorted, text, watermark",
        "controlnet_strength": 0.85
    },
    "facades": {
        "workflow": "facades_workflow.json",
        "positive_prompt": "photorealistic modern building facade, architectural photography, detailed, professional, 8k",
        "negative_prompt": "sketch, drawing, lines, unfinished, low quality, blurry",
        "controlnet_strength": 0.8
    },
    "portraits": {
        "workflow": "portraits_workflow.json",
        "positive_prompt": "photorealistic portrait, professional photography, detailed, natural lighting, 8k",
        "negative_prompt": "sketch, drawing, engraving, lines, unfinished, low quality",
        "controlnet_strength": 0.75
    }
}

class BildwerkProcessor:
    def __init__(self):
        self.results = []
        self.failed = []
        self.stats = {
            "total": 0,
            "analyzed": 0,
            "processed": 0,
            "failed": 0
        }
        
    def load_image_as_base64(self, image_path):
        """Load image and encode as base64"""
        with open(image_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')
    
    def analyze_image(self, image_path):
        """
        Analyze image using local vision model
        Returns preset recommendation
        """
        # For now, use file metadata and naming to infer type
        # Later: integrate with qwen35l vision API
        
        filename = image_path.stem.lower()
        
        # Simple heuristic-based classification
        if any(kw in filename for kw in ['portrait', 'person', 'face', 'head']):
            return "portraits"
        elif any(kw in filename for kw in ['facade', 'building', 'house', 'architecture']):
            return "facades"
        else:
            # Default to vedute for city views and sketches
            return "vedute"
    
    def get_workflow(self, preset):
        """Load workflow JSON for preset"""
        workflow_file = WORKFLOWS_DIR / PRESETS[preset]["workflow"]
        if workflow_file.exists():
            with open(workflow_file, 'r') as f:
                return json.load(f)
        else:
            # Use default vedute workflow
            default_file = WORKFLOWS_DIR / "vedute_sketch_workflow.json"
            with open(default_file, 'r') as f:
                return json.load(f)
    
    def submit_to_comfyui(self, workflow, image_b64, output_prefix):
        """Submit workflow to ComfyUI"""
        # Update workflow with image data
        workflow['5']['inputs']['image'] = image_b64
        workflow['8']['inputs']['filename_prefix'] = f"bildwerk_output/{output_prefix}"
        
        # Update prompts based on preset
        preset = self.current_preset
        if '6' in workflow:  # Positive prompt node
            workflow['6']['inputs']['text'] = PRESETS[preset]["positive_prompt"]
        if '7' in workflow:  # Negative prompt node
            workflow['7']['inputs']['text'] = PRESETS[preset]["negative_prompt"]
        
        try:
            response = requests.post(
                f"{COMFYUI_API}/prompt",
                json={"prompt": workflow},
                timeout=30
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
    
    def process_image(self, image_path):
        """Process single image"""
        filename = image_path.name
        stem = image_path.stem
        
        print(f"  📝 Analyzing: {filename}")
        
        # Analyze and determine preset
        self.current_preset = self.analyze_image(image_path)
        print(f"    → Preset: {self.current_preset}")
        
        # Store analysis
        analysis = {
            "filename": filename,
            "source_path": str(image_path),
            "preset": self.current_preset,
            "timestamp": datetime.now().isoformat()
        }
        
        # Save analysis
        analysis_file = DESCRIPTIONS_DIR / f"{stem}_analysis.json"
        with open(analysis_file, 'w') as f:
            json.dump(analysis, f, indent=2)
        
        self.stats["analyzed"] += 1
        
        # Load and prepare workflow
        workflow = self.get_workflow(self.current_preset)
        
        # Load image
        image_b64 = self.load_image_as_base64(image_path)
        
        # Submit to ComfyUI
        print(f"  🚀 Submitting to ComfyUI...")
        prompt_id = self.submit_to_comfyui(workflow, image_b64, stem)
        
        if prompt_id:
            analysis["prompt_id"] = prompt_id
            analysis["status"] = "submitted"
            self.stats["processed"] += 1
            print(f"    ✅ Submitted! Queue ID: {prompt_id}")
        else:
            analysis["status"] = "failed"
            self.stats["failed"] += 1
            print(f"    ❌ Submission failed")
        
        return analysis
    
    def process_all(self):
        """Process all images in input directory"""
        # Ensure output directories exist
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        DESCRIPTIONS_DIR.mkdir(parents=True, exist_ok=True)
        
        # Find all images
        image_files = list(INPUT_DIR.glob("*.jpg")) + \
                      list(INPUT_DIR.glob("*.jpeg")) + \
                      list(INPUT_DIR.glob("*.png"))
        
        self.stats["total"] = len(image_files)
        
        print(f"🎯 Starting batch processing of {len(image_files)} images")
        print(f"📂 Input: {INPUT_DIR}")
        print(f"📤 Output: {OUTPUT_DIR}")
        print(f"📝 Descriptions: {DESCRIPTIONS_DIR}")
        print(f"🖥️  ComfyUI: {COMFYUI_URL}")
        print()
        
        start_time = datetime.now()
        
        # Process images (sequentially to avoid overwhelming ComfyUI)
        for i, image_path in enumerate(sorted(image_files), 1):
            print(f"\n[{i}/{len(image_files)}] {image_path.name}")
            try:
                result = self.process_image(image_path)
                self.results.append(result)
                
                # Small delay between submissions
                time.sleep(1)
                
            except Exception as e:
                print(f"  ❌ Error processing {image_path.name}: {e}")
                self.failed.append({
                    "filename": image_path.name,
                    "error": str(e)
                })
                self.stats["failed"] += 1
        
        # Generate summary
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        summary = {
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": duration,
            "stats": self.stats,
            "results": self.results,
            "failures": self.failed
        }
        
        # Save summary
        summary_file = DESCRIPTIONS_DIR / "processing_summary.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        # Print summary
        print("\n" + "="*60)
        print("📊 BATCH PROCESSING SUMMARY")
        print("="*60)
        print(f"Total images:    {self.stats['total']}")
        print(f"Analyzed:        {self.stats['analyzed']}")
        print(f"Processed:       {self.stats['processed']}")
        print(f"Failed:          {self.stats['failed']}")
        print(f"Duration:        {duration/60:.1f} minutes")
        print(f"Results saved:   {summary_file}")
        print("="*60)
        
        return summary

def main():
    processor = BildwerkProcessor()
    processor.process_all()

if __name__ == "__main__":
    main()
