# Task 6 Report: Embedding disk cache

**Status:** DONE_WITH_CONCERNS

**Commits:**
- `b88d4b1` — feat(rag): disk cache for knowledge embeddings (hash-keyed, incremental)

**One-line test summary:** `tests/rag/` 1 passed, 1 failed (`test_second_instance_uses_cache`); 4 existing embedding/rag tests still pass.

**Files touched:**
- `src/llm/embedding_rag.py` (modified)
- `tests/rag/__init__.py` (new, empty)
- `tests/rag/test_embedding_cache.py` (new)
- `.gitignore` (appended `data/rag_cache/`)

**Implementation summary:**

- Added `cache_dir: str = "data/rag_cache"` parameter to `EmbeddingRAG.__init__`; stored as `Path`.
- Added `_chunk_id(chunk) -> str` static method — `sha256(title + "\x00" + content)[:16]`.
- Replaced the eager `model.encode(texts)` block in `_ensure_initialized` with a call to new `_load_or_build_embeddings()`.
- `_load_or_build_embeddings()` reads `<cache_dir>/manifest.json` + `<cache_dir>/embeddings.npz`; computes chunk ids; copies cached vectors into the output matrix; batches and encodes only the missing/changed chunk ids; rewrites both files atomically. Cache is rebuilt (with warning) on read failure.
- Sorted `concepts_dir.glob("*.md")` and `hypotheses/<status_dir>.glob("*.md")` so chunk order is deterministic across runs (required for the cache to be stable).
- `data/rag_cache/` appended to `.gitignore`.
- `ruff check` + `ruff format --check` pass on both changed files.

**Concerns:**

1. **`test_second_instance_uses_cache` fails** — `assert 3 == 2`. The brief's `_FakeModel.encode_calls` counter increments on **every** `encode(...)` call, but `EmbeddingRAG.retrieve_context` encodes the **query** on every call (line 217 of the existing implementation: `query_embedding = self._model.encode([query], ...)`). The doc-batch encode happens exactly once (cache hits on second instance), but the query encode is per-call. Trace for the failing test:
   - `rag1.retrieve_context("gaps", top_k=2)` → 1 doc-batch encode + 1 query encode = `encode_calls == 2`
   - `calls_after_first = 2`
   - `rag2.retrieve_context("gaps", top_k=2)` → 0 doc encodes (cached) + 1 query encode = `encode_calls == 3`
   - Assertion `3 == 2` fails.
   - The intent of the test ("unchanged docs must not be re-embedded") is satisfied — the cache is working. The brief assertion conflates "any encode call" with "doc encode call."

   The brief test was copied verbatim per directive. To make it pass without scope creep, the assertion could be `assert fake_st.encode_calls == calls_after_first + 1` (only the query re-encodes). Alternatively, an in-memory query cache could be added to `retrieve_context`, but that exceeds the brief's scope (which specifies only the disk cache keyed by chunk id). The second test (`test_changed_file_reembeds_only_changed`) passes because it uses `>` not `==`, so the query encode doesn't trip it.

2. **Disk cache writes on every init** — even when the cache is fully hit, `_load_or_build_embeddings` rewrites `manifest.json` and `embeddings.npz` with the same content. Harmless on local SSD; could be optimized (skip write if `new_manifest == manifest` and no to_embed) if it ever shows up in profiles. Not done here per brief.

3. **`EmbeddingRAG` is still instantiated via `__init__` at module load in some callers** (lazy `_ensure_initialized` defers the cache write, so this is OK), but anyone importing `EmbeddingRAG` and constructing it at module top-level will trigger a cache write on first `retrieve_context`. Behavior is unchanged from pre-task; just noting.

4. **KnowledgeGraph still loads on each instance** — `_ensure_kg` is per-instance, so two `EmbeddingRAG` instances load the KG twice (visible in test logs: "KnowledgeGraph: 62 nodes, 46 edges" appears twice). Not a regression; KG loading is unchanged. Could be addressed in a future task if needed.

---

## Fix Appendix (post-review)

**Reviewer finding:** Concern 1 above (`test_second_instance_uses_cache`) was flagged as a fixable assertion bug. The cache implementation is correct; the brief's assertion conflates "any encode call" with "doc-batch encode call." `retrieve_context` always re-encodes the query on every call — this is expected behavior, not a cache miss.

**Fix applied (option a — minimal, intent-preserving):** Replaced the exact-equality assertion on `fake_st.encode_calls` with an upper-bound assertion that allows for exactly one extra encode (the per-call query re-encode), while still failing loudly if any doc re-embed leaks through the cache:

```python
# before
assert fake_st.encode_calls == calls_after_first, "unchanged docs must not be re-embedded"
# after
assert fake_st.encode_calls <= calls_after_first + 1, (
    f"second instance should reuse doc cache "
    f"(only query re-encode expected), got delta={fake_st.encode_calls - calls_after_first}"
)
```

The `<= + 1` form preserves the original intent ("unchanged docs must not be re-embedded") — any delta greater than 1 would indicate a cache leak, and the message includes the actual delta for diagnostics.

**Verification:**
- `python -m pytest tests/rag/test_embedding_cache.py -q` → **2 passed**.
- `python -m pytest tests/ -q -k "rag or embedding"` → **5 passed, 938 deselected** (no regressions; covers the second test in the file plus other pre-existing embedding/rag tests).
- `ruff check tests/rag/test_embedding_cache.py` → All checks passed.
- `ruff format --check tests/rag/test_embedding_cache.py` → 1 file already formatted.

**Commit:** `<hash>` — `test(rag): correct off-by-one in cache-hit assertion (query re-encode is expected)` (new commit on top of `b88d4b1`, not an amend).
