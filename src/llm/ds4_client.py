"""ds4 client -- local DeepSeek V4 Flash server (antirez's implementation).

ds4 is an OpenAI-compatible local server: no auth (any bearer token),
native ``tool_calls``, SSE streaming and ``reasoning_content`` in
responses. It speaks the same protocol as the cloud DeepSeek API, so
this client subclasses :class:`DeepSeekClient` and only repoints the
configuration at ``settings.llm.ds4`` (plus a health check that is
never optimistic: a local server is healthy only if it answers).

Health rule (mirrors MiniMaxClient): ``GET {base_url}/models`` must
return HTTP 200 with a JSON content type. An unreachable server
reports unhealthy, never raises.
"""

from __future__ import annotations

import aiohttp

from ..core.config import get_settings
from .deepseek_client import DeepSeekClient


class DS4Client(DeepSeekClient):
    """OpenAI-compatible client for the local ds4 server."""

    def __init__(self, settings=None):
        # Deliberately not calling super().__init__: DeepSeekClient reads
        # settings.llm.deepseek (the cloud config) -- we read llm.ds4.
        self.settings = settings or get_settings()
        ds4 = self.settings.llm.ds4
        self.base_url = ds4.base_url
        self.api_key = ds4.api_key
        self.timeout = ds4.timeout
        # ds4 serves a single model; keep both DeepSeekClient aliases so
        # inherited ``model or self.model_pro`` defaults resolve to it.
        self.model_pro = ds4.model
        self.model_flash = ds4.model
        self.session: aiohttp.ClientSession | None = None
        self._health: bool | None = None

    async def check_health(self) -> bool:
        """GET /models; healthy only for HTTP 200 + JSON. Never raises.

        Unlike the cloud clients there is no optimistic "key present"
        path: a local server either answers or it does not.
        """
        try:
            if self.session and not self.session.closed:
                async with self.session.get(f"{self.base_url}/models") as r:
                    return r.status == 200 and "json" in r.headers.get("Content-Type", "")
            # No (or closed) session: open a short-lived one. A refused
            # connection or timeout lands in the except clause below.
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=3),
            ) as probe:
                async with probe.get(f"{self.base_url}/models") as r:
                    return r.status == 200 and "json" in r.headers.get("Content-Type", "")
        except Exception:
            return False
