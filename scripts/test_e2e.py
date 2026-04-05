#!/usr/bin/env python3
"""
End-to-end test for one file through the complete router lifecycle
"""

import asyncio
import sys
import os

# Add router to path
sys.path.insert(0, '/var/lib/clawdbot/workspace/agents/hgg16/bildwerk')
os.chdir('/var/lib/clawdbot/workspace/agents/hgg16/bildwerk')

from router import Router

async def test_one_file(filename: str):
    """Test processing one specific file"""
    config_path = '/var/lib/clawdbot/workspace/agents/hgg16/bildwerk/router/config.yaml'
    
    router = Router(config_path)
    
    try:
        await router.start()
        
        print(f"\n{'='*60}")
        print(f"Testing end-to-end processing of: {filename}")
        print(f"{'='*60}\n")
        
        success = await router.process_file(filename)
        
        print(f"\n{'='*60}")
        if success:
            print(f"✅ SUCCESS: {filename} processed end-to-end")
        else:
            print(f"❌ FAILED: {filename} processing failed")
        print(f"{'='*60}\n")
        
        return success
        
    finally:
        await router.stop()

async def list_inbox():
    """List files in inbox"""
    config_path = '/var/lib/clawdbot/workspace/agents/hgg16/bildwerk/router/config.yaml'
    
    router = Router(config_path)
    
    try:
        await router.start()
        
        base_path = router.config.nextcloud['folders']['base']
        inbox_folder = router.config.nextcloud['folders']['inbox']
        inbox_full_path = f"{base_path}/{inbox_folder}"
        
        files = await router.nextcloud.list_folder(inbox_full_path)
        
        print(f"Files in inbox ({inbox_full_path}):")
        if files:
            for f in files:
                print(f"  - {f}")
        else:
            print("  (empty)")
        
        return files
        
    finally:
        await router.stop()

async def main():
    if len(sys.argv) > 1:
        if sys.argv[1] == 'list':
            files = await list_inbox()
            if files:
                print(f"\nUse: python3 test_e2e.py <filename> to process a specific file")
        else:
            filename = sys.argv[1]
            success = await test_one_file(filename)
            sys.exit(0 if success else 1)
    else:
        print("Usage:")
        print("  python3 test_e2e.py list              - List files in inbox")
        print("  python3 test_e2e.py <filename>        - Process one file end-to-end")
        print()
        print("Example:")
        print("  python3 test_e2e.py list")
        print("  python3 test_e2e.py sketch_001.png")

if __name__ == "__main__":
    asyncio.run(main())
