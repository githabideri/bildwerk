"""Classification manifest loader and router.

Resolution order:
1. overrides.json (manual overrides)
2. manifest.corrected.json (corrected classification)
3. Fallback to review (if not found in either)

Paths are configured via environment variables:
- BILDWORK_CLASSIFICATION_DIR: Base directory for classification files (default: classification/)
- BILDWORK_MANIFEST_FILE: Manifest filename (default: manifest.corrected.json)
- BILDWORK_OVERRIDES_FILE: Overrides filename (default: overrides.json)
"""

import json
import os
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

# Bucket to preset mapping
ARCHETYPE_TO_PRESET = {
    'interior_passage': 'interior_passage_v2_p1',
    'veduta_city': 'veduta_city_v1_p1',
    'facade': 'facade_v1_p1',
    'portrait_engraving': 'portrait_engraving_v1_p1',
}


def get_classification_dir() -> Path:
    """Get the classification directory from environment or use default."""
    return Path(os.environ.get('BILDWORK_CLASSIFICATION_DIR', 'classification'))


def get_manifest_path() -> Path:
    """Get the manifest file path from environment or use default."""
    return get_classification_dir() / os.environ.get('BILDWORK_MANIFEST_FILE', 'manifest.corrected.json')


def get_overrides_path() -> Path:
    """Get the overrides file path from environment or use default."""
    return get_classification_dir() / os.environ.get('BILDWORK_OVERRIDES_FILE', 'overrides.json')


def load_overrides(path: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    """Load manual overrides from overrides.json.
    
    Args:
        path: Optional path to overrides file. If None, uses BILDWORK_OVERRIDES_FILE env var.
    
    Returns dict mapping filename → override_info
    Format: {"filename": {"bucket": "interior_passage", "reason": "manual correction"}}
    """
    if path is None:
        path = get_overrides_path()
    
    if path.exists():
        with open(path, 'r') as f:
            return json.load(f)
    return {}


def load_classification_manifest(path: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    """Load and validate classification manifest.
    
    Args:
        path: Optional path to manifest file. If None, uses BILDWORK_MANIFEST_FILE env var.
    
    Returns dict mapping filename → file_info for easy lookup.
    
    Supports both formats:
    - Array format (actual): [{"filename": "...", "bucket": "..."}, ...]
    - Object format (planned): {"files": [...]}
    """
    if path is None:
        path = get_manifest_path()
    
    if not path.exists():
        raise FileNotFoundError(f"Manifest file not found: {path}")
    
    with open(path, 'r') as f:
        manifest = json.load(f)
    
    # Handle both formats
    if isinstance(manifest, list):
        files = manifest
    elif isinstance(manifest, dict) and 'files' in manifest:
        files = manifest['files']
    else:
        raise ValueError(f"Invalid manifest format: {type(manifest)}")
    
    return {file['filename']: file for file in files}


def route_file(filename: str, manifest: Dict[str, Dict[str, Any]], 
               overrides: Optional[Dict[str, Dict[str, Any]]] = None) -> Tuple[Optional[str], bool]:
    """Route file to preset based on classification.
    
    Resolution order:
    1. overrides.json (manual overrides)
    2. manifest.corrected.json (corrected classification)
    3. Fallback to review (if not found)
    
    Args:
        filename: Source filename (e.g., "331.jpg")
        manifest: Loaded manifest dict from load_classification_manifest()
        overrides: Loaded overrides dict from load_overrides() (optional)
    
    Returns:
        (preset_name, requires_review)
        - preset_name: Preset to use, or None if should route to review
        - requires_review: True if file should go to review folder
    """
    # 1. Check overrides first (manual corrections)
    if overrides and filename in overrides:
        override = overrides[filename]
        bucket = override.get('bucket')
        if bucket and bucket in ARCHETYPE_TO_PRESET:
            preset = ARCHETYPE_TO_PRESET[bucket]
            return preset, False  # Override takes precedence, no review needed
        elif bucket == 'unclear':
            return None, True  # Override to unclear → review
        else:
            # Invalid override bucket → review
            return None, True
    
    # 2. Check manifest
    if filename not in manifest:
        # No classification available - manual routing needed
        return None, True
    
    file_info = manifest[filename]
    bucket = file_info.get('bucket') or file_info.get('assigned_bucket')  # Support both formats
    confidence = file_info.get('confidence', 0.0)
    
    # Handle string confidence ("high"/"low")
    if isinstance(confidence, str):
        if confidence.lower() == 'low':
            return None, True  # Route to review
        elif confidence.lower() == 'high':
            pass  # Continue with auto-routing
        else:
            return None, True  # Unknown confidence → review
    
    # Handle numeric confidence (0.0-1.0)
    elif isinstance(confidence, (int, float)):
        if confidence < 0.7:
            return None, True  # Route to review
    
    # Unclear bucket → review
    if bucket == 'unclear':
        return None, True
    
    # Map bucket to preset
    preset = ARCHETYPE_TO_PRESET.get(bucket)
    if preset is None:
        return None, True  # Unknown bucket → review
    
    return preset, False


def get_bucket_stats(manifest: Dict[str, Dict[str, Any]]) -> Dict[str, int]:
    """Get classification distribution by bucket.
    
    Returns dict mapping bucket → count
    """
    buckets = {}
    for file_info in manifest.values():
        bucket = file_info.get('bucket') or file_info.get('assigned_bucket')
        buckets[bucket] = buckets.get(bucket, 0) + 1
    return buckets
