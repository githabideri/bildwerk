#!/usr/bin/env python3
"""
Test with interior_passage preset
"""

import asyncio
import sys
import os

sys.path.insert(0, '/var/lib/clawdbot/workspace/agents/hgg16/bildwerk')
os.chdir('/var/lib/clawdbot/workspace/agents/hgg16/bildwerk')

from router import Router

async def test_interior(filename: str):
    """Test processing with interior_passage preset"""
    config_path = '/var/lib/clawdbot/workspace/agents/hgg16/bildwerk/router/config.yaml'
    
    router = Router(config_path)
    
    try:
        await router.start()
        
        print(f"\n{'='*60}")
        print(f"Testing INTERIOR PASSAGE preset with: {filename}")
        print(f"{'='*60}\n")
        print(f"Preset: interior_passage")
        print(f"  - denoise: 0.25 (preserve composition)")
        print(f"  - cfg: 5.5 (respect source over prompt)")
        print(f"  - steps: 30 (more detail)")
        print(f"  - positive: historic stone vaulted corridor...")
        print(f"  - negative: drawing, sketch, CGI, washed out...")
        print(f"{'='*60}\n")
        
        # Temporarily change the preset loading
        original_load_preset = router.config.load_preset
        def load_interior_preset(name):
            if name == 'vedute':
                return original_load_preset('interior_passage')
            return original_load_preset(name)
        router.config.load_preset = load_interior_preset
        
        success = await router.process_file(filename)
        
        print(f"\n{'='*60}")
        if success:
            print(f"✅ SUCCESS: {filename} processed with interior_passage preset")
        else:
            print(f"❌ FAILED: {filename} processing failed")
        print(f"{'='*60}\n")
        
        return success
        
    finally:
        await router.stop()

async def main():
    if len(sys.argv) > 1:
        filename = sys.argv[1]
        success = await test_interior(filename)
        sys.exit(0 if success else 1)
    else:
        print("Usage: python3 test_interior.py <filename>")
        print("Example: python3 test_interior.py 331.jpg")

if __name__ == "__main__":
    asyncio.run(main())
