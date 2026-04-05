"""Auto-QC metrics for generated outputs.

Minimal viable version for routing decisions:
- mean saturation (detect monochrome)
- highlight clipping ratio
- shadow clipping ratio
- local contrast

Routing behavior:
- monochrome/low saturation -> review
- excessive clipping -> review
- low contrast -> review
- acceptable -> done
"""

import cv2
import numpy as np
from pathlib import Path
from typing import Dict, Any


def check_mean_saturation(image_path: str) -> float:
    """Calculate mean saturation (0-1).
    
    Returns value between 0 (grayscale) and 1 (fully saturated).
    """
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Could not load image: {image_path}")
    
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    hsv = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2HSV)
    
    # Extract saturation channel
    saturation = hsv[:,:,1]
    mean_sat = np.mean(saturation) / 255.0
    
    return mean_sat


def check_highlight_clipping(image_path: str) -> float:
    """Calculate fraction of pixels that are overexposed (>240/255).
    
    Returns value between 0 and 1.
    """
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Could not load image: {image_path}")
    
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    
    # Flatten and count highlights
    flat = image_rgb.flatten()
    highlight_mask = flat > 240
    highlight_ratio = np.mean(highlight_mask)
    
    return highlight_ratio


def check_shadow_clipping(image_path: str) -> float:
    """Calculate fraction of pixels that are crushed blacks (<15/255).
    
    Returns value between 0 and 1.
    """
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Could not load image: {image_path}")
    
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    
    flat = image_rgb.flatten()
    shadow_mask = flat < 15
    shadow_ratio = np.mean(shadow_mask)
    
    return shadow_ratio


def check_local_contrast(image_path: str) -> float:
    """Calculate local contrast using Laplacian variance.
    
    Returns normalized value (higher = more contrast).
    """
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Could not load image: {image_path}")
    
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # Laplacian variance
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    
    # Normalize (empirical: typical range 100-1000 for good images)
    normalized = min(laplacian_var / 1000.0, 1.0)
    
    return normalized


def run_auto_qc(image_path: str) -> Dict[str, Any]:
    """Run all auto-QC metrics on an image.
    
    Returns dict with:
    - metrics: all computed values
    - passes: bool (all thresholds met)
    - reasons: list of failure reasons (if any)
    """
    metrics = {
        'mean_saturation': check_mean_saturation(image_path),
        'highlight_clipping': check_highlight_clipping(image_path),
        'shadow_clipping': check_shadow_clipping(image_path),
        'local_contrast': check_local_contrast(image_path),
    }
    
    reasons = []
    
    # Check thresholds
    if metrics['mean_saturation'] < 0.15:
        reasons.append(f"Low saturation: {metrics['mean_saturation']:.3f} (< 0.15)")
    
    if metrics['highlight_clipping'] > 0.10:
        reasons.append(f"Highlight clipping: {metrics['highlight_clipping']:.2%} (> 10%)")
    
    if metrics['shadow_clipping'] > 0.15:
        reasons.append(f"Shadow clipping: {metrics['shadow_clipping']:.2%} (> 15%)")
    
    if metrics['local_contrast'] < 0.30:
        reasons.append(f"Low local contrast: {metrics['local_contrast']:.3f} (< 0.30)")
    
    return {
        'metrics': metrics,
        'passes': len(reasons) == 0,
        'reasons': reasons,
    }


def should_route_to_review(qc_result: Dict[str, Any]) -> bool:
    """Determine if output should go to review folder.
    
    Args:
        qc_result: Output from run_auto_qc()
    
    Returns:
        True if should route to review, False if acceptable for done/
    """
    return not qc_result['passes']


# Thresholds (documented for easy adjustment)
THRESHOLDS = {
    'mean_saturation_min': 0.15,      # Below this = monochrome/sketch
    'highlight_clipping_max': 0.10,   # Above this = overexposed
    'shadow_clipping_max': 0.15,      # Above this = crushed blacks
    'local_contrast_min': 0.30,       # Below this = flat/washed out
}
