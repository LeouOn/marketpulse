#!/usr/bin/env python3
"""Quick script to test if FastAPI routes are registered"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    from src.api.main import app

    print("\n=== Registered Routes ===\n")
    for route in app.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            methods = ', '.join(route.methods) if route.methods else 'N/A'
            print(f"{methods:10} {route.path}")
        elif hasattr(route, 'path'):
            print(f"{'ROUTE':10} {route.path}")

    print("\n=== Market Endpoints ===\n")
    market_routes = [r for r in app.routes if hasattr(r, 'path') and '/api/market/' in r.path]
    for route in market_routes:
        methods = ', '.join(route.methods) if hasattr(route, 'methods') else 'N/A'
        print(f"{methods:10} {route.path}")

    print("\n=== LLM Endpoints ===\n")
    llm_routes = [r for r in app.routes if hasattr(r, 'path') and '/api/llm/' in r.path]
    for route in llm_routes:
        methods = ', '.join(route.methods) if hasattr(route, 'methods') else 'N/A'
        print(f"{methods:10} {route.path}")

except Exception as e:
    print(f"Error loading app: {e}")
    import traceback
    traceback.print_exc()
