"""
POST /api/llm/chat must not leak MiniMax's inline <think>...</think> reasoning.

Reasoning models (MiniMax-M3) return their chain of thought inline in the
message content. The chat router used to hand that raw <think> block to the
user (docs/STATUS.md known issue #4). These tests pin the stripping contract:

- a complete leading block is removed, leaving only the answer
- multiple blocks and multi-line blocks are all removed
- an unterminated opening <think> drops from the tag to the end
- normal text is returned untouched
- leading whitespace left after removal is trimmed

Seams follow tests/test_llm_chat_cached_data.py: the collector lives on
``src.api.routers.deps.collector`` and the LLM client is obtained via
``_get_router()`` + ``router.route("standard")``.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))


def _fake_router(reply):
    """Build a fake ModelRouter whose routed client returns ``reply``."""
    client = AsyncMock()

    def completion(**kwargs):
        return {"choices": [{"message": {"content": reply}}]}

    client.generate_completion.side_effect = completion

    router = AsyncMock()
    router.route.return_value = (client, "test-model")

    async def _fake_get_router():
        return router

    return _fake_get_router


def _post_chat(message):
    """POST /api/llm/chat on a minimal app, with LLM reply mocked at the seam."""
    import src.api.routers.llm as llm_mod

    app = FastAPI()
    app.include_router(llm_mod.router)

    with (
        patch("src.api.routers.deps.collector", None),
        patch.object(llm_mod, "_get_router", new=_fake_router(_post_chat.reply)),
        patch.object(llm_mod, "_selected_model", None),
    ):
        resp = TestClient(app).post(
            "/api/llm/chat",
            json={"message": message},
        )
    return resp


def test_http_strips_leading_think_block():
    """HTTP 200 with only the final answer in the response text."""
    _post_chat.reply = "<think>secret reasoning</think>Final answer"

    resp = _post_chat("In one short sentence: what is a stop loss?")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True, body
    assert body["data"]["response"] == "Final answer", body["data"]["response"]
    assert "secret" not in body["data"]["response"]
    assert "<think>" not in body["data"]["response"]


def test_http_strips_multiple_blocks():
    """Every complete block is removed, answer text between them survives."""
    _post_chat.reply = "<think>first</think>Part one <think>second</think>Part two"

    resp = _post_chat("hello")

    assert resp.status_code == 200, resp.text
    text = resp.json()["data"]["response"]
    assert text == "Part one Part two", repr(text)


def test_http_strips_multiline_block_and_trims_leading_whitespace():
    """A multi-line block is removed and leftover leading whitespace trimmed."""
    _post_chat.reply = "<think>line one\nline two\nline three</think>\n\n  Final answer"

    resp = _post_chat("hello")

    assert resp.status_code == 200, resp.text
    text = resp.json()["data"]["response"]
    assert text == "Final answer", repr(text)


def test_http_unterminated_think_drops_to_end():
    """An unterminated opening <think> drops from the tag to the end."""
    _post_chat.reply = "Visible intro<think>half-finished reasoning that never closes"

    resp = _post_chat("hello")

    assert resp.status_code == 200, resp.text
    text = resp.json()["data"]["response"]
    assert text == "Visible intro", repr(text)
    assert "half-finished" not in text


def test_http_normal_text_untouched():
    """Text without think blocks is returned byte-for-byte unchanged."""
    normal = "A stop loss limits downside.\nIt should sit below support — not at round numbers."
    _post_chat.reply = normal

    resp = _post_chat("hello")

    assert resp.status_code == 200, resp.text
    text = resp.json()["data"]["response"]
    assert text == normal, repr(text)


def test_strip_helper_contract():
    """Unit-level contract for the strip helper used by the endpoint."""
    from src.api.routers.llm import _strip_think

    assert _strip_think("<think>a</think>b") == "b"
    assert _strip_think("<THINK>a</THINK>b") == "b"
    assert _strip_think("<think>only reasoning</think>") == ""
    assert _strip_think("no tags here") == "no tags here"
    assert _strip_think("") == ""
    assert _strip_think(None) is None


if __name__ == "__main__":
    print("=" * 70)
    print("LLM chat <think> strip - Unit Tests")
    print("=" * 70)

    tests = [
        test_http_strips_leading_think_block,
        test_http_strips_multiple_blocks,
        test_http_strips_multiline_block_and_trims_leading_whitespace,
        test_http_unterminated_think_drops_to_end,
        test_http_normal_text_untouched,
        test_strip_helper_contract,
    ]

    passed = 0
    failed = 0
    for test_fn in tests:
        try:
            test_fn()
            print(f"  PASS: {test_fn.__name__}")
            passed += 1
        except Exception as e:
            import traceback

            print(f"  FAIL: {test_fn.__name__}: {e}")
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 70)
    print(f"Results: {passed}/{len(tests)} passed, {failed} failed")
    print("=" * 70)
    sys.exit(0 if failed == 0 else 1)
