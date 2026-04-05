# Auto-QC and Review Routing

## Overview

Automatic quality control metrics determine if outputs go to `done/` (acceptable) or `review/` (needs human review).

## Current Implementation Status

**Status:** Scaffolding defined, not yet implemented in router

## Auto-QC Metrics

### 1. Mean Saturation

**Purpose:** Detect outputs that are still monochrome or too desaturated

**Threshold:** `< 0.15` → Route to review

**Implementation:**
```python
import cv2
import numpy as np

def check_mean_saturation(image_path: str) -> float:
    """
    Calculate mean saturation (0-1).
    Returns value between 0 (grayscale) and 1 (fully saturated).
    """
    image = cv2.imread(image_path)
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    hsv = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2HSV)
    
    # Extract saturation channel
    saturation = hsv[:,:,1]
    mean_sat = np.mean(saturation) / 255.0
    
    return mean_sat

# Usage
saturation = check_mean_saturation('output.png')
if saturation < 0.15:
    route_to_review("Low saturation - output still monochrome")
```

**Expected Values:**
- `< 0.10`: Essentially monochrome → Review
- `0.10-0.15`: Very desaturated → Review
- `0.15-0.30`: Low color → Accept but flag
- `> 0.30`: Good color → Accept

### 2. Highlight Clipping

**Purpose:** Detect overexposed areas where detail is lost

**Threshold:** `> 0.10` (10% of pixels) → Route to review

**Implementation:**
```python
def check_highlight_clipping(image_path: str) -> float:
    """
    Calculate fraction of pixels that are overexposed (>240/255).
    Returns value between 0 and 1.
    """
    image = cv2.imread(image_path)
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    
    # Flatten and count highlights
    flat = image_rgb.flatten()
    highlight_mask = flat > 240
    highlight_ratio = np.mean(highlight_mask)
    
    return highlight_ratio

# Usage
highlights = check_highlight_clipping('output.png')
if highlights > 0.10:
    route_to_review(f"Highlight clipping: {highlights:.2%}")
```

**Expected Values:**
- `< 0.02`: Excellent → Accept
- `0.02-0.05`: Good → Accept
- `0.05-0.10`: Acceptable → Accept
- `> 0.10`: Too much clipping → Review

### 3. Shadow Clipping

**Purpose:** Detect crushed blacks where detail is lost

**Threshold:** `> 0.15` (15% of pixels) → Route to review

**Implementation:**
```python
def check_shadow_clipping(image_path: str) -> float:
    """
    Calculate fraction of pixels that are crushed blacks (<15/255).
    Returns value between 0 and 1.
    """
    image = cv2.imread(image_path)
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    
    flat = image_rgb.flatten()
    shadow_mask = flat < 15
    shadow_ratio = np.mean(shadow_mask)
    
    return shadow_ratio

# Usage
shadows = check_shadow_clipping('output.png')
if shadows > 0.15:
    route_to_review(f"Shadow clipping: {shadows:.2%}")
```

**Expected Values:**
- `< 0.05`: Excellent → Accept
- `0.05-0.10`: Good → Accept
- `0.10-0.15`: Acceptable → Accept
- `> 0.15`: Too much crushing → Review

### 4. Local Contrast

**Purpose:** Detect flat, washed-out images

**Threshold:** `< 0.30` (normalized) → Route to review

**Implementation:**
```python
def check_local_contrast(image_path: str) -> float:
    """
    Calculate local contrast using Laplacian variance.
    Returns normalized value (higher = more contrast).
    """
    image = cv2.imread(image_path)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # Laplacian variance
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    
    # Normalize (empirical: typical range 100-1000 for good images)
    normalized = min(laplacian_var / 1000.0, 1.0)
    
    return normalized

# Usage
contrast = check_local_contrast('output.png')
if contrast < 0.30:
    route_to_review(f"Low local contrast: {contrast:.3f}")
```

**Expected Values:**
- `< 0.20`: Very flat → Review
- `0.20-0.30`: Low contrast → Review
- `0.30-0.50`: Acceptable → Accept
- `> 0.50`: Good contrast → Accept

### 5. Geometry Drift (Future)

**Purpose:** Detect if output composition differs too much from source

**Status:** Not yet implemented

**Planned Approach:**
```python
def check_geometry_drift(source_path: str, output_path: str) -> float:
    """
    Compare edge maps of source and output.
    Returns similarity score (1 = identical, 0 = completely different).
    """
    # 1. Extract edges from both images (Canny)
    # 2. Resize to same dimensions
    # 3. Calculate structural similarity (SSIM)
    # 4. Return similarity score
    
    # Threshold: < 0.60 → Review
    pass
```

## Routing Logic

### Decision Tree

```
┌─────────────────────────────────────┐
│ Start: Output generated             │
└──────────────┬──────────────────────┘
               │
               ▼
    ┌──────────────────────┐
    │ Check saturation     │
    │ < 0.15?              │
    └──────────┬───────────┘
               │
    ┌──────────┴──────────┐
    │ YES                 │ NO
    ▼                     ▼
┌──────────────┐    ┌──────────────────────┐
│ Route to     │    │ Check highlight      │
│ review/      │    │ clipping > 0.10?     │
│ (monochrome) │    └──────────┬───────────┘
└──────────────┘               │
    ▲              ┌───────────┴───────────┐
    │              │ YES                    │ NO
    │              ▼                        ▼
    │       ┌──────────────┐         ┌──────────────────────┐
    │       │ Route to     │         │ Check shadow         │
    │       │ review/      │         │ clipping > 0.15?     │
    │       │ (highlights) │         └──────────┬───────────┘
    │              ▲                 │ YES       │ NO
    │              │                 ▼            ▼
    │       ┌──────┴──────┐    ┌──────────────┐ ┌──────────────────────┐
    │       │ Route to    │    │ Route to     │ │ Check local          │
    │       │ review/     │    │ review/      │ │ contrast < 0.30?     │
    │       │ (shadows)   │    │ (shadows)    │ └──────────┬───────────┘
    │              ▲       │    │              │            │
    │              │       │    │              │   ┌────────┴────────┐
    │       ┌──────┴──────┐│    │              │   │ YES            │ NO
    │       │              ││    │              │   ▼                ▼
    └───────│ Route to     ││    │              └──│ Route to     │ ┌──────────────┐
            │ review/      ││    │                 │ review/      │ │ Route to     │
            │ (contrast)   ││    │                 │ (contrast)   │ │ done/        │
            └──────────────┘│    │                 └──────────────┘ └──────────────┘
                            │    │
                            └────┴─────────────────────────────────────┘
                                 All checks passed
```

### Implementation in Router

```python
async def run_auto_qc(self, output_path: str) -> tuple[bool, list[str]]:
    """
    Run auto-QC metrics on output.
    
    Returns: (passes, [reasons_for_review])
    """
    reasons = []
    
    # Check saturation
    saturation = check_mean_saturation(output_path)
    if saturation < 0.15:
        reasons.append(f"Low saturation: {saturation:.3f} (< 0.15)")
    
    # Check highlights
    highlights = check_highlight_clipping(output_path)
    if highlights > 0.10:
        reasons.append(f"Highlight clipping: {highlights:.2%} (> 10%)")
    
    # Check shadows
    shadows = check_shadow_clipping(output_path)
    if shadows > 0.15:
        reasons.append(f"Shadow clipping: {shadows:.2%} (> 15%)")
    
    # Check contrast
    contrast = check_local_contrast(output_path)
    if contrast < 0.30:
        reasons.append(f"Low local contrast: {contrast:.3f} (< 0.30)")
    
    passes = len(reasons) == 0
    return passes, reasons

# Usage in process_file
passes, reasons = await self.run_auto_qc(output_local)

if passes:
    # Upload to done/
    await self.nextcloud.upload_file(str(output_local), output_remote)
else:
    # Upload to review/
    review_remote = f"{base_path}/review/{output_filename}"
    await self.nextcloud.upload_file(str(output_local), review_remote)
    
    # Update sidecar with review flag
    sidecar['review_required'] = True
    sidecar['review_reasons'] = reasons
```

## Review Folder Workflow

### Files in Review/

| File | Purpose |
|------|---------|
| `OUTPUT_XXXXX_.png` | Generated output |
| `OUTPUT_XXXXX__sidecar.json` | Metadata with review flags |
| `SOURCE_XXXXX.jpg` | Original source (for comparison) |

### Sidecar Review Fields

```json
{
  "review_required": true,
  "review_reasons": [
    "Low saturation: 0.087 (< 0.15)",
    "Low local contrast: 0.245 (< 0.30)"
  ],
  "qc_metrics": {
    "mean_saturation": 0.087,
    "highlight_clipping": 0.03,
    "shadow_clipping": 0.08,
    "local_contrast": 0.245
  },
  "review_status": "pending",  // pending, approved, rejected
  "reviewed_by": null,
  "reviewed_at": null,
  "review_notes": null
}
```

### Human Review Actions

1. **Approve** → Move to `done/`
   - Update sidecar: `review_status: "approved"`
   - Optional: Add `review_notes`

2. **Reject** → Move to `error/`
   - Update sidecar: `review_status: "rejected"`
   - Required: Add `review_notes` with reason

3. **Reprocess** → Move back to `inbox/`
   - Update sidecar: `review_status: "reprocessing"`
   - Optional: Specify new preset parameters
   - Remove from `completed_jobs` marker

## Future Enhancements

- [ ] Geometry drift metric (edge map comparison)
- [ ] Perceptual hashing (detect near-duplicates)
- [ ] Face detection quality (for portraits)
- [ ] Architectural detail preservation metric
- [ ] Color accuracy vs. expected material colors
- [ ] ML-based quality scoring (train on approved outputs)
- [ ] Web UI for review workflow
- [ ] Batch review tools (approve multiple at once)

## Threshold Calibration

Current thresholds are placeholders. Calibrate by:

1. Process 50+ images with current presets
2. Manually rate each as "acceptable" or "needs review"
3. Run QC metrics on all outputs
4. Plot metrics vs. human ratings
5. Adjust thresholds to maximize agreement

**Target:** 90%+ agreement between auto-QC and human review

---

*Auto-QC scaffolding defined. Implement in router after preset calibration stabilizes.*
