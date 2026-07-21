"""Search FRED for Case-Shiller metro home price indexes.

Uses FredProvider.api_key (the working 32-char key from credentials.yaml /
environment), NOT the broken 14-char key in .env.

FRED API note: the older `series_search_text` query parameter was deprecated;
the current parameter is `search_text`. Using the old name returns
`{"error_code":400, "error_message":"Variable search_text is not set."}` even
though you passed `series_search_text`. This script uses the correct name.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from src.research.data.fred import FredProvider

# Use FredProvider's working key (loads from credentials.yaml, not .env)
fp = FredProvider()
key = fp.api_key
print(f"Key length: {len(key)}")
if not key or len(key) < 20:
    sys.exit(1)


def search(text, limit=20):
    r = requests.get(
        "https://api.stlouisfed.org/fred/series/search",
        params={
            "search_text": text,
            "api_key": key,
            "file_type": "json",
            "limit": limit,
            "order_by": "popularity",
            "sort_order": "desc",
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def show(data, n=20):
    for s in data.get("seriess", [])[:n]:
        sid = s["id"]
        title = s["title"][:62]
        freq = s["frequency"]
        start = s.get("observation_start", "?")
        end = s.get("observation_end", "?")
        print(f"  {sid:<16} {freq:<10} {start} to {end}  {title}")


# Search for Case-Shiller home price indexes
print()
print("=== Case-Shiller Home Price Index (top 25 by popularity) ===")
d = search("Case-Shiller Home Price Index", 50)
print(f"Total matches: {d.get('count', 0)}")
show(d, 25)

print()
print("--- San Francisco specific search ---")
d2 = search("San Francisco home price index", 20)
show(d2, 15)

print()
print("--- Oakland specific search ---")
d3 = search("Oakland home price", 20)
show(d3, 15)

print()
print("--- FHFA Oakland-Berkeley-Livermore MSA ---")
d4 = search("Oakland Berkeley Livermore house price", 20)
show(d4, 10)

print()
print("--- SF price tiers ---")
d5 = search("San Francisco tier home", 20)
show(d5, 10)
