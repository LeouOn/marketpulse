"""Model Router -- Capability-Based Multi-Provider Dispatch

Routes LLM requests to the best available provider + model for each
capability class.  Handles provider health tracking and automatic
fallback when the primary provider is unavailable.

Usage::

    router = ModelRouter()
    async with router:
        client, model_id = await router.route("reasoning")
        response = await client.generate_completion(messages, model=model_id)

Capability classes
------------------
===============  ============================  =====================
Capability        Typical Use                   Preferred Model
===============  ============================  =====================
reasoning         Multi-step analysis,          deepseek-v4-pro
                  hypothesis testing
fast              Quick checks, data            deepseek-v4-flash
                  validation, simple queries
standard          Default chat / general        deepseek-v4-pro
                  analysis
structured_output Function calling, typed       deepseek-v4-pro
                  JSON responses
===============  ============================  =====================

Provider fallback chain is defined in ``model_routing`` config section.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from ..core.config import get_settings
from .deepseek_client import DeepSeekClient
from .llm_client import LMStudioClient, OpenRouterClient


# ---------------------------------------------------------------------------
# Provider registry entry
# ---------------------------------------------------------------------------

@dataclass
class ProviderEntry:
    name: str                        # "deepseek", "lm_studio", "openrouter"
    client: Any = None               # Client instance (lazy-init)
    healthy: bool | None = None      # None = unchecked
    priority: int = 0                # Lower = higher priority


# ---------------------------------------------------------------------------
# ModelRouter
# ---------------------------------------------------------------------------

class ModelRouter:
    """Dispatch LLM requests to the best provider for each capability."""

    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self._routing = self.settings.llm.model_routing
        self._deepseek_cfg = self.settings.llm.deepseek

        # Capability → (provider_name, model_id)
        self._capability_map: dict[str, tuple[str, str]] = {}

        # Provider registry -- populated on __aenter__
        self._providers: dict[str, ProviderEntry] = {}
        self._entered = False

        # Build capability map from config
        self._build_capability_map()

        self._fallback_chain: list[str] = [
            p.strip()
            for p in self._routing.fallback_providers.split(",")
            if p.strip()
        ]

    # -- capability map ---------------------------------------------------

    def _build_capability_map(self) -> None:
        """Map each capability to (provider, model_id) from config."""
        primary = self._routing.primary_provider

        for cap in ("reasoning", "fast", "standard", "structured_output"):
            model_id = getattr(self._routing, cap, "")
            if not model_id:
                continue
            # Determine provider from model id prefix or config
            provider = self._provider_for_model(model_id, primary)
            self._capability_map[cap] = (provider, model_id)

        # Always register a "fallback" capability
        self._capability_map["fallback"] = (primary, self._deepseek_cfg.model_pro)

    def _provider_for_model(self, model_id: str, default: str) -> str:
        """Heuristic: which provider owns this model id?"""
        if "deepseek" in model_id.lower():
            return "deepseek"
        if "gpt" in model_id.lower() or "openai" in model_id.lower():
            return "openrouter"
        # For local models (no cloud prefix), use lm_studio
        return "lm_studio"

    # -- context manager --------------------------------------------------

    async def __aenter__(self):
        if self._entered:
            return self

        # Initialise providers lazily
        self._providers["deepseek"] = ProviderEntry(
            name="deepseek",
            client=DeepSeekClient(self.settings),
            priority=0,  # highest
        )
        self._providers["lm_studio"] = ProviderEntry(
            name="lm_studio",
            client=LMStudioClient(self.settings),
            priority=1,
        )
        self._providers["openrouter"] = ProviderEntry(
            name="openrouter",
            client=OpenRouterClient(self.settings),
            priority=2,
        )

        # Enter clients that have async context managers
        for entry in self._providers.values():
            if hasattr(entry.client, "__aenter__"):
                try:
                    await entry.client.__aenter__()
                except Exception as e:
                    logger.warning(
                        f"Failed to enter provider {entry.name}: {e}"
                    )

        # Quick health check on primary
        primary = self._routing.primary_provider
        if primary in self._providers:
            await self._check_provider(primary)

        self._entered = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        for entry in self._providers.values():
            if hasattr(entry.client, "__aexit__"):
                with _suppress():
                    await entry.client.__aexit__(exc_type, exc_val, exc_tb)
        self._entered = False

    # -- health -----------------------------------------------------------

    async def _check_provider(self, name: str) -> bool:
        """Check a provider's health.  Returns True if healthy."""
        entry = self._providers.get(name)
        if entry is None:
            return False

        client = entry.client
        if hasattr(client, "check_health"):
            try:
                healthy = await client.check_health()
            except Exception:
                healthy = False
            entry.healthy = healthy
            logger.debug(f"Provider {name} health={healthy}")
            return healthy

        # LMStudioClient doesn't have check_health -- try a quick model probe
        if hasattr(client, "_auto_detect_model"):
            try:
                await client._auto_detect_model()
                detected = client._detected_model
                entry.healthy = detected is not None and detected != ""
                logger.debug(f"Provider {name} auto-detect={detected}")
                return bool(entry.healthy)
            except Exception:
                entry.healthy = False
                return False

        # Unknown -- assume healthy
        entry.healthy = True
        return True

    async def check_all(self) -> dict[str, bool]:
        """Run health checks on all providers.  Returns ``{name: healthy}``."""
        results = {}
        for name in self._providers:
            results[name] = await self._check_provider(name)
        return results

    @property
    def provider_status(self) -> dict[str, dict[str, Any]]:
        """Snapshot of provider health."""
        return {
            name: {
                "healthy": entry.healthy,
                "priority": entry.priority,
            }
            for name, entry in self._providers.items()
        }

    # -- routing ----------------------------------------------------------

    async def route(
        self, capability: str = "standard"
    ) -> tuple[Any, str]:
        """Resolve a capability to ``(client, model_id)``.

        Returns the highest-priority healthy provider that can serve
        the capability.  Falls through the provider chain if the
        primary is unhealthy.
        """
        if not self._entered:
            raise RuntimeError("ModelRouter not entered -- use 'async with'")

        # Look up capability
        cap_entry = self._capability_map.get(capability)
        if cap_entry is None:
            # Unknown capability -- use best available
            cap_entry = ("deepseek", self._deepseek_cfg.model_pro)

        preferred_provider, model_id = cap_entry

        # Try preferred provider first
        if preferred_provider in self._providers:
            entry = self._providers[preferred_provider]
            if entry.healthy or await self._check_provider(preferred_provider):
                logger.debug(
                    f"ModelRouter: {capability} → {preferred_provider}/{model_id}"
                )
                return entry.client, model_id

        # Fallback chain
        primary = self._routing.primary_provider
        fallback_names = [primary] + [
            n for n in self._fallback_chain if n != preferred_provider
        ]

        for name in fallback_names:
            if name not in self._providers:
                continue
            entry = self._providers[name]
            if entry.healthy or await self._check_provider(name):
                # Map capability to a model on this fallback provider
                fb_model = self._fallback_model_for(name, capability)
                logger.warning(
                    f"ModelRouter: {capability} → FALLBACK "
                    f"{name}/{fb_model} (preferred {preferred_provider} unhealthy)"
                )
                return entry.client, fb_model

        # Last resort -- return primary client even if unhealthy
        entry = self._providers.get(primary)
        if entry:
            logger.error(
                f"ModelRouter: all providers unhealthy for {capability} -- "
                f"returning {primary} anyway"
            )
            return entry.client, model_id

        raise RuntimeError(
            f"No provider available for capability '{capability}'"
        )

    def _fallback_model_for(self, provider: str, capability: str) -> str:
        """Pick a sensible model on a fallback provider."""
        if provider == "deepseek":
            if capability == "fast":
                return self._deepseek_cfg.model_flash
            return self._deepseek_cfg.model_pro
        if provider == "lm_studio":
            # LM Studio auto-detects -- return empty to use whatever is loaded
            return ""
        if provider == "openrouter":
            # Sensible OpenRouter defaults
            if capability in ("reasoning", "structured_output"):
                return "deepseek/deepseek-chat"
            return "openai/gpt-4o-mini"
        return ""

    # -- convenience: generate with routing -------------------------------

    async def generate(
        self,
        messages: list[dict[str, str]],
        capability: str = "standard",
        max_tokens: int = 800,
        temperature: float = 0.3,
        tools: list[dict[str, Any]] | None = None,
        **kwargs,
    ) -> dict[str, Any] | None:
        """Route + generate in one call."""
        client, model_id = await self.route(capability)

        if tools and hasattr(client, "generate_with_tools"):
            # If a tool_handler is provided, use the agent loop
            tool_handler = kwargs.pop("tool_handler", None)
            if tool_handler:
                return await client.generate_with_tools(
                    messages=messages,
                    tools=tools,
                    tool_handler=tool_handler,
                    model=model_id,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    **kwargs,
                )

        return await client.generate_completion(
            messages=messages,
            model=model_id or None,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=tools,
            **kwargs,
        )

    # -- model listing ----------------------------------------------------

    def list_available_models(self) -> list[dict[str, Any]]:
        """Return a combined model list for the UI."""
        models: list[dict[str, Any]] = []

        # DeepSeek models
        ds = self._deepseek_cfg
        models.append({
            "id": ds.model_pro,
            "provider": "deepseek",
            "capability": "reasoning",
            "description": "DeepSeek V4 Pro -- full reasoning, function calling",
            "recommended": True,
        })
        models.append({
            "id": ds.model_flash,
            "provider": "deepseek",
            "capability": "fast",
            "description": "DeepSeek V4 Flash -- fast, cost-effective",
            "recommended": False,
        })

        # LM Studio (local) -- placeholder; real models populated at runtime
        models.append({
            "id": "lm-studio-local",
            "provider": "lm_studio",
            "capability": "fallback",
            "description": "Local model via LM Studio (auto-detected)",
            "recommended": False,
        })

        return models


# -- helpers ---------------------------------------------------------------

class _suppress:
    """Context manager that silently swallows all exceptions."""

    def __enter__(self):
        pass

    def __exit__(self, *args):
        return True
