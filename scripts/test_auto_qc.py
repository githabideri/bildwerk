#!/usr/bin/env python3
"""Test auto-QC metrics on sample images."""

import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from router.auto_qc import run_auto_qc, THRESHOLDS

def test_auto_qc():
    print("="*60)
    print("AUTO-QC METRICS TEST")
    print("="*60)
    print()
    
    # Print thresholds
    print("Current thresholds:")
    for key, value in THRESHOLDS.items():
        print(f"  {key}: {value}")
    print()
    
    # Test on 331.jpg output if exists
    test_images = [
        '/var/lib/clawdbot/workspace/agents/localbot-llmlab/bildwork_331_result.png',
        'test_output/result_img2img.png',
    ]
    
    for image_path in test_images:
        path = Path(image_path)
        if not path.exists():
            print(f"✗ {image_path} not found, skipping")
            continue
        
        print(f"Testing: {image_path}")
        print("-" * 40)
        
        try:
            result = run_auto_qc(str(path))
            
            print(f"  Mean saturation:      {result['metrics']['mean_saturation']:.3f} (min: {THRESHOLDS['mean_saturation_min']})")
            print(f"  Highlight clipping:   {result['metrics']['highlight_clipping']:.2%} (max: {THRESHOLDS['highlight_clipping_max']})")
            print(f"  Shadow clipping:      {result['metrics']['shadow_clipping']:.2%} (max: {THRESHOLDS['shadow_clipping_max']})")
            print(f"  Local contrast:       {result['metrics']['local_contrast']:.3f} (min: {THRESHOLDS['local_contrast_min']})")
            print()
            
            if result['passes']:
                print(f"  ✓ PASS: Route to done/")
            else:
                print(f"  ⚠ FAIL: Route to review/")
                for reason in result['reasons']:
                    print(f"    - {reason}")
            
            print()
            
        except Exception as e:
            print(f"  ✗ ERROR: {e}")
            print()
    
    print("="*60)
    print("Auto-QC test complete")

if __name__ == '__main__':
    test_auto_qc()
