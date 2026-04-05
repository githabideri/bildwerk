#!/usr/bin/env python3
"""
Analyze images using local Qwen vision model and store descriptions
"""

import os
import sys
import json
import base64
from pathlib import Path
from datetime import datetime

# Add localbot workspace to path
sys.path.insert(0, '/var/lib/clawdbot/workspace/agents/localbot-llmlab')

def encode_image_to_base64(image_path):
    """Encode image file to base64"""
    with open(image_path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')

def analyze_image_with_qwen(image_path, image_b64):
    """
    Use qwen35l vision model to analyze image
    Returns description JSON
    """
    import requests
    
    # Local qwen35l vision endpoint
    vision_url = "http://192.168.0.27:8000/v1/chat/completions"  # llama-cpp server
    
    prompt = """Analyze this image and provide a detailed description including:
1. Image type (sketch, engraving, photograph, painting, drawing, etc.)
2. Subject matter (city view, building facade, portrait, landscape, etc.)
3. Style and technique
4. Notable features and details
5. Condition/quality
6. Recommended processing preset (vedute/facades/portraits/other)

Provide your analysis in JSON format with these fields:
{
  "image_type": "...",
  "subject": "...",
  "style": "...",
  "features": ["...", "..."],
  "condition": "...",
  "recommended_preset": "vedute|facades|portraits|other",
  "full_description": "..."
}
"""
    
    # For now, return placeholder - actual implementation needs proper vision API
    return {
        "image_type": "unknown",
        "subject": "unknown",
        "style": "unknown",
        "features": [],
        "condition": "unknown",
        "recommended_preset": "vedute",
        "full_description": "Vision analysis pending - using default vedute preset",
        "analysis_timestamp": datetime.now().isoformat()
    }

def process_image_directory(image_dir, output_dir):
    """Process all images in directory"""
    image_dir = Path(image_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Find all images
    image_files = list(image_dir.glob("*.jpg")) + \
                  list(image_dir.glob("*.jpeg")) + \
                  list(image_dir.glob("*.png"))
    
    print(f"📁 Found {len(image_files)} images to analyze")
    
    results = []
    for i, image_path in enumerate(sorted(image_files), 1):
        print(f"[{i}/{len(image_files)}] Analyzing: {image_path.name}")
        
        try:
            # Encode image
            image_b64 = encode_image_to_base64(image_path)
            
            # Analyze with vision model
            analysis = analyze_image_with_qwen(str(image_path), image_b64)
            analysis["filename"] = image_path.name
            analysis["source_path"] = str(image_path)
            
            # Store analysis
            results.append(analysis)
            
            # Save individual analysis
            analysis_file = output_dir / f"{image_path.stem}_analysis.json"
            with open(analysis_file, 'w') as f:
                json.dump(analysis, f, indent=2)
                
        except Exception as e:
            print(f"  ❌ Error analyzing {image_path.name}: {e}")
            results.append({
                "filename": image_path.name,
                "source_path": str(image_path),
                "error": str(e),
                "analysis_timestamp": datetime.now().isoformat()
            })
    
    # Save all analyses
    manifest_file = output_dir / "image_analyses_manifest.json"
    with open(manifest_file, 'w') as f:
        json.dump({
            "total_images": len(results),
            "successful": len([r for r in results if "error" not in r]),
            "failed": len([r for r in results if "error" in r]),
            "timestamp": datetime.now().isoformat(),
            "analyses": results
        }, f, indent=2)
    
    print(f"✅ Analysis complete! Results saved to {output_dir}")
    print(f"   Successful: {len([r for r in results if 'error' not in r])}")
    print(f"   Failed: {len([r for r in results if 'error' in r])}")
    
    return results

if __name__ == "__main__":
    image_dir = sys.argv[1] if len(sys.argv) > 1 else "/var/lib/clawdbot/workspace/agents/hgg16/Dias-Dichtl"
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "/var/lib/clawdbot/workspace/agents/hgg16/bildwerk/descriptions"
    
    process_image_directory(image_dir, output_dir)
