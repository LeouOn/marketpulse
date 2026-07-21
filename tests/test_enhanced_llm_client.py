# tests/test_enhanced_llm_client.py
import pytest


class _FakeRouter:
    def __init__(self):
        self._entered = True
        self.calls = []

    async def generate(self, *, messages, capability="standard", max_tokens=800, temperature=0.3):
        self.calls.append({"messages": messages, "capability": capability})
        return {"choices": [{"message": {"content": "fake analysis"}}]}


@pytest.mark.asyncio
async def test_analyze_with_knowledge_uses_injected_router():
    from src.llm.enhanced_llm_client import EnhancedLLMClient

    router = _FakeRouter()
    client = EnhancedLLMClient(router=router)
    result = await client.analyze_with_knowledge("what is an FVG?")
    assert result == "fake analysis"
    assert router.calls, "router.generate was not called"
    prompt_text = router.calls[0]["messages"][-1]["content"]
    assert "FVG" in prompt_text or "fair value gap" in prompt_text.lower()


@pytest.mark.asyncio
async def test_legacy_class_removed():
    import src.llm.enhanced_llm_client as m

    assert not hasattr(m, "EnhancedLMStudioClient")
