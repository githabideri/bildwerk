#!/usr/bin/env python3
"""
Auto-QC for Interior Pass Calibration

Minimum viable QC metrics:
- mean saturation: should be > 0.15 (not monochrome)
- highlight clipping ratio: should be < 0.10 (not overexposed)
- shadow clipping ratio: should be < 0.05 (not underexposed)
- local contrast (Laplacian variance): should be > 50 (not flat)

Routing logic:
- obvious monochrome/near-monochrome (saturation < 0.08) -> review
- washed-out (mean saturation < 0.10 AND highlight clipping > 0.15) -> review
- flat low-contrast (Laplacian variance < 30) -> review
- technical failure (file corrupt, etc.) -> error
- acceptable output -> done
"""

import os
import sys
import json
from pathlib import Path
from PIL import Image
import numpy as np

# QC thresholds (tune as needed)
THRESHOLDS = {
    "min_saturation": 0.08,      # Below this = near-monochrome -> review
    "min_mean_saturation": 0.12,  # Below this + highlight clipping > 0.15 -> review
    "max_highlight_clipping": 0.15,  # Above this + low saturation -> review
    "min_laplacian_variance": 30,  # Below this = flat -> review
}

def calculate_mean_saturation(image: Image.Image) -> float:
    """Calculate mean saturation in HSV color space."""
    hsv = image.convert('HSV')
    r, g, b = hsv.split()
    # Saturation is in G channel for HSV
    s_array = np.array(g) / 255.0
    return float(np.mean(s_array))

def calculate_clipping_ratio(image: Image.Image, channel='r', threshold=250):
    """Calculate ratio of clipped pixels (overexposed)."""
    if channel == 'r':
        arr = np.array(image.split()[0])
    elif channel == 'g':
        arr = np.array(image.split()[1])
    elif channel == 'b':
        arr = np.array(image.split()[2])
    elif channel == 'all':
        arr = np.array(image).reshape(-1, 3).mean(axis=1)
    else:
        arr = np.array(image)
    
    clipped = np.sum(arr > threshold)
    total = arr.size
    return clipped / total

def calculate_laplacian_variance(image: Image.Image) -> float:
    """Calculate local contrast using Laplacian variance."""
    gray = image.convert('L')
    arr = np.array(gray, dtype=np.float64)
    
    # Compute Laplacian
    laplacian = np.zeros_like(arr, dtype=np.float64)
    for i in range(1, len(arr) - 1):
        for j in range(1, len(arr[0]) - 1):
            laplacian[i, j] = (
                4 * arr[i, j] - arr[i-1, j] - arr[i+1, j] - arr[i, j-1] - arr[i, j+1]
            )
    
    variance = np.var(laplacian)
    return float(variance)

def analyze_image(image_path: Path) -> dict:
    """Run all QC metrics on an image."""
    try:
        image = Image.open(image_path)
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        metrics = {
            "path": str(image_path),
            "mean_saturation": calculate_mean_saturation(image),
            "highlight_clipping": calculate_clipping_ratio(image, threshold=250),
            "shadow_clipping": calculate_clipping_ratio(image, threshold=10),
            "laplacian_variance": calculate_laplacian_variance(image),
        }
        
        # Determine routing
        routing = determine_routing(metrics)
        metrics["routing"] = routing
        
        return metrics, routing
        
    except Exception as e:
        return {"path": str(image_path), "error": str(e)}, "error"

def determine_routing(metrics: dict) -> str:
    """
    Determine routing based on QC metrics.
    
    Returns: 'done', 'review', or 'error'
    """
    if "error" in metrics:
        return "error"
    
    # Check for monochrome
    if metrics["mean_saturation"] < THRESHOLDS["min_saturation"]:
        return "review"
    
    # Check for washed out
    if (metrics["mean_saturation"] < THRESHOLDS["min_mean_saturation"] and 
        metrics["highlight_clipping"] > THRESHOLDS["max_highlight_clipping"]):
        return "review"
    
    # Check for flat/low contrast
    if metrics["laplacian_variance"] < THRESHOLDS["min_laplacian_variance"]:
        return "review"
    
    return "done"

def main():
    if len(sys.argv) < 2:
        print("Usage: python auto_qc.py <image_path>")
        sys.exit(1)
    
    image_path = Path(sys.argv[1])
    metrics, routing = analyze_image(image_path)
    
    print(json.dumps(metrics, indent=2))
    
    # Return routing as exit code for shell integration
    if routing == "done":
        sys.exit(0)
    elif routing == "review":
        sys.exit(1)
    else:  # error
        sys.exit(2)

if __name__ == "__main__":
    main()
