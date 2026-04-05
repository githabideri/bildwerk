#!/usr/bin/env python3
"""Test classification manifest loading and routing."""

import json
import sys

# Add router to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MANIFEST_PATH = '$(BILDWORK_CLASSIFICATION_DIR:-classification)/manifest.json'

def load_classification_manifest(path: str) -> dict:
    """Load and validate classification manifest
    
    Returns dict mapping filename → file_info for easy lookup
    """
    with open(path, 'r') as f:
        manifest = json.load(f)
    
    # Handle both formats:
    # - Array format (actual): [{"filename": "...", "bucket": "..."}, ...]
    # - Object format (planned): {"files": [...]}
    if isinstance(manifest, list):
        files = manifest
    elif isinstance(manifest, dict) and 'files' in manifest:
        files = manifest['files']
    else:
        raise ValueError(f"Invalid manifest format: {type(manifest)}")
    
    return {file['filename']: file for file in files}

def route_file(filename: str, manifest: dict) -> tuple[str, bool]:
    """
    Route file to preset based on classification.
    
    Returns: (preset_name, requires_review)
    """
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
    ARCHETYPE_TO_PRESET = {
        'interior_passage': 'interior_passage_v2_p1',
        'veduta_city': 'veduta_city_v1_p1',
        'facade': 'facade_v1_p1',
        'portrait_engraving': 'portrait_engraving_v1_p1',
    }
    
    preset = ARCHETYPE_TO_PRESET.get(bucket)
    if preset is None:
        return None, True  # Unknown bucket → review
    
    return preset, False

def main():
    print("Loading classification manifest...")
    manifest = load_classification_manifest(MANIFEST_PATH)
    print(f"✓ Loaded {len(manifest)} files\n")
    
    # Summary by bucket
    print("Classification summary:")
    buckets = {}
    for file_info in manifest.values():
        bucket = file_info.get('bucket') or file_info.get('assigned_bucket')
        buckets[bucket] = buckets.get(bucket, 0) + 1
    
    for bucket, count in sorted(buckets.items()):
        print(f"  {bucket}: {count}")
    print()
    
    # Test routing for each bucket
    print("Testing preset routing:")
    test_cases = [
        ('301.jpg', 'facade'),
        ('302.jpg', 'interior_passage'),
        ('303.jpg', 'veduta_city'),
        ('331.jpg', 'interior_passage'),  # Our test file
    ]
    
    for filename, expected_bucket in test_cases:
        if filename not in manifest:
            print(f"  ✗ {filename}: NOT IN MANIFEST")
            continue
        
        preset, requires_review = route_file(filename, manifest)
        actual_bucket = manifest[filename].get('bucket')
        
        if requires_review:
            print(f"  ⚠ {filename}: → REVIEW (bucket: {actual_bucket})")
        else:
            print(f"  ✓ {filename}: {actual_bucket} → {preset}")
    
    print()
    
    # Check for unclear/low confidence
    unclear = [f for f, info in manifest.items() 
               if (info.get('bucket') == 'unclear' or 
                   (isinstance(info.get('confidence'), str) and info['confidence'].lower() == 'low'))]
    
    if unclear:
        print(f"⚠ {len(unclear)} files flagged for review (unclear/low confidence):")
        for f in unclear[:5]:
            print(f"    - {f}")
    else:
        print("✓ No files flagged for review (all high confidence)")
    
    print()
    print("✓ Manifest validation complete")

if __name__ == '__main__':
    main()
