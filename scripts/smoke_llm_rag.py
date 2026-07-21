# scripts/smoke_llm_rag.py
"""Manual live smoke test: boots nothing, expects server on :8000 and real LLM keys in env.
Usage: RUN server first (uvicorn src.api.main:app --port 8000), then: python scripts/smoke_llm_rag.py
"""

import json
import urllib.request

BASE = "http://localhost:8000"


def post(path, payload):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read())


if __name__ == "__main__":
    print("1. retrieve-context (offline RAG)...")
    rc = post("/api/llm/retrieve-context", {"query": "fair value gap", "max_results": 3})
    assert rc["success"], rc
    print(f"   mode={rc['data']['retrieval_mode']} chunks={len(rc['data']['chunks'])}")

    print("2. knowledge term...")
    kt = get("/api/llm/knowledge/FVG")
    assert kt["success"], kt
    print(f"   FVG: {kt['data']['definition'][:80]}")

    print("3. enhanced-analysis (live LLM)...")
    ea = post("/api/llm/enhanced-analysis", {"query": "What is a fair value gap and how is it traded?"})
    assert ea["success"], ea
    print(f"   analysis: {ea['data']['analysis'][:200]}")
    print(f"   knowledge_used: {ea['data']['knowledge_used']}")

    print("4. test-hypothesis (live LLM)...")
    th = post("/api/llm/test-hypothesis", {"hypothesis_name": "overnight_margin_cascade"})
    print(f"   success={th['success']} keys={list((th.get('data') or {}).keys())}")

    print("SMOKE OK")
