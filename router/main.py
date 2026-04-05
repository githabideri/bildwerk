#!/usr/bin/env python3
"""Main entry point for bildwerk router"""
from bildwerk.router import main

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())