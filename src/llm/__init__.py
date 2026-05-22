"""MarketPulse LLM Integration
Primary: LM Studio (local models)
Fallback: OpenRouter (cloud APIs)
"""

from .llm_client import LLMManager, LMStudioClient, OpenRouterClient

__all__ = ["LMStudioClient", "OpenRouterClient", "LLMManager"]
