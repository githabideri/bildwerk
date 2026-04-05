#!/usr/bin/env python3
"""Test corrected manifest loading and routing with overrides."""

import json
import sys
from pathlib import Path

# Add router to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from router.manifest_router import (
    load_classification_manifest,
    load_overrides,
    route_file,
    get_bucket_stats
)

def main():
    print("="*60)
    print("CORRECTED MANIFEST ROUTING TEST")
    print("="*60)
    print()
    
    # 1. Load corrected manifest
    print("1. Loading corrected manifest...")
    manifest_path = '$(BILDWORK_CLASSIFICATION_DIR:-classification)/manifest.corrected.json'
    
    if not Path(manifest_path).exists():
        print(f"   ✗ FAILED: Corrected manifest not found at {manifest_path}")
        return False
    
    manifest = load_classification_manifest(manifest_path)
    print(f"   ✓ Loaded {len(manifest)} files from {manifest_path}")
    print()
    
    # 2. Show bucket distribution
    print("2. Classification distribution:")
    stats = get_bucket_stats(manifest)
    for bucket, count in sorted(stats.items()):
        print(f"   - {bucket}: {count} files")
    print()
    
    # 3. Load overrides
    print("3. Loading overrides...")
    overrides_path = '$(BILDWORK_CLASSIFICATION_DIR:-classification)/overrides.json'
    overrides = load_overrides(overrides_path)
    print(f"   ✓ Loaded {len(overrides)} overrides from {overrides_path}")
    print()
    
    # 4. Test 331.jpg routing (critical test - was misclassified before)
    print("4. Testing 331.jpg routing (critical test)...")
    preset, requires_review = route_file('331.jpg', manifest, overrides)
    print(f"   Filename: 331.jpg")
    print(f"   Bucket: {manifest['331.jpg']['bucket']}")
    print(f"   Preset: {preset}")
    print(f"   Requires review: {requires_review}")
    
    if preset == 'interior_passage_v2_p1' and not requires_review:
        print(f"   ✓ PASS: 331.jpg correctly routed to interior_passage_v2_p1")
    else:
        print(f"   ✗ FAIL: 331.jpg not correctly routed")
        return False
    print()
    
    # 5. Test routing for each bucket
    print("5. Testing preset routing for each bucket...")
    test_cases = [
        ('301.jpg', 'facade', 'facade_v1_p1'),
        ('309.jpg', 'interior_passage', 'interior_passage_v2_p1'),
        ('303.jpg', 'veduta_city', 'veduta_city_v1_p1'),
    ]
    
    all_pass = True
    for filename, expected_bucket, expected_preset in test_cases:
        if filename not in manifest:
            print(f"   ✗ {filename}: NOT IN MANIFEST")
            all_pass = False
            continue
        
        preset, requires_review = route_file(filename, manifest, overrides)
        actual_bucket = manifest[filename]['bucket']
        
        if preset == expected_preset and not requires_review:
            print(f"   ✓ {filename}: {actual_bucket} → {preset}")
        else:
            print(f"   ✗ {filename}: {actual_bucket} → {preset} (expected {expected_preset})")
            all_pass = False
    
    print()
    
    # 6. Test unclear bucket routing
    print("6. Testing unclear bucket routing...")
    unclear_files = [f for f, info in manifest.items() if info['bucket'] == 'unclear']
    if unclear_files:
        print(f"   Found {len(unclear_files)} unclear files")
        for filename in unclear_files[:3]:
            preset, requires_review = route_file(filename, manifest, overrides)
            if preset is None and requires_review:
                print(f"   ✓ {filename}: Correctly routed to review")
            else:
                print(f"   ✗ {filename}: Should route to review")
                all_pass = False
    else:
        print("   ℹ No unclear files in manifest")
    print()
    
    # 7. Test override mechanism
    print("7. Testing override mechanism...")
    # Temporarily add an override for testing
    test_overrides = {
        '301.jpg': {
            'bucket': 'interior_passage',
            'reason': 'Test override'
        }
    }
    
    preset, requires_review = route_file('301.jpg', manifest, test_overrides)
    if preset == 'interior_passage_v2_p1':
        print(f"   ✓ Override works: 301.jpg → interior_passage (via override)")
    else:
        print(f"   ✗ Override failed: 301.jpg → {preset}")
        all_pass = False
    print()
    
    # 8. Summary
    print("="*60)
    if all_pass:
        print("✓ ALL TESTS PASSED")
        print()
        print("Corrected manifest is ACTIVE and routing correctly.")
        print("Override mechanism is functional.")
        return True
    else:
        print("✗ SOME TESTS FAILED")
        return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
