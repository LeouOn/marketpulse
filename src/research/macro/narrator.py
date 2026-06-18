"""LLMJudgeNarrator -- structured-output LLM call for regime probabilities (W3/T13).

A single ``async`` LLM call produces a :class:`RegimeJudgeOutput` containing:

* ``regime_probs`` -- 5 probabilities (one per :class:`Regime`), summing to
  1.0 +/- 0.05.  Used by T14's :class:`MacroRegimeModel` ensembler to blend
  the rules-based classifier (T12) with the LLM judge via the ``alpha``
  mixing weight.
* ``narrative`` -- 2-3 sentence explanation citing a historical analog.
  Surfaced to the operator UI so a human can sanity-check the LLM call.

Design constraints (Metis MUST NOT / G7):

* **No new LLM providers.**  Uses the existing :class:`ModelRouter`
  (DeepSeek → LM Studio → OpenRouter fallback chain).  Do NOT add a new
  client library.
* **Skippable in backtest.**  This module is *inert* unless explicitly
  invoked.  T14's :class:`MacroRegimeModel` carries a ``use_llm: bool``
  flag that defaults to ``False`` in backtest context; in that mode the
  narrator is never called and ``alpha = 1.0`` (rules-only).
* **Async only.**  ``judge_and_narrate`` is a coroutine -- callers must
  ``await`` it.  The ModelRouter itself is async and routes through
  ``aiohttp``.
* **Stub Fed statements.**  v1 accepts ``fed_statements: str = ""`` and
  the prompt degrades gracefully ("no recent statements available").
  Fetching Fed RSS / FOMC minutes is OUT OF SCOPE here; TODO(T15+).

Caching
-------

One parquet file at ``data/macro/narrator_cache.parquet`` keyed by
``(as_of_date, ticker)`` with a 24-hour TTL.  Cache hits skip the LLM
entirely.  Writes are atomic (``.tmp`` + rename).

Retry
-----

On JSON parse failure OR :class:`pydantic.ValidationError`, the narrator
retries **once** with a stricter prompt that forbids markdown fences and
re-states the schema.  A second failure raises :class:`LLMJudgeError`;
T14 catches that and falls back to rules-only.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
from loguru import logger
from pydantic import BaseModel, Field, ValidationError, field_validator

# ---------------------------------------------------------------------------
# Regime enum -- defensive import from T12
# ---------------------------------------------------------------------------
#
# T12 ships ``src/research/macro/regimes.py`` with the canonical ``Regime``
# enum.  T13 runs in parallel with T12, so the file may not exist yet at
# import time.  We try the canonical import first and fall back to a local
# ``str, Enum`` with IDENTICAL string values.  The ``.value`` strings are
# part of the public serialization contract (LLM prompt schema, cache
# parquet) and MUST match whatever T12 ships.
#
# When T12 lands, the try-import succeeds and the fallback is dead code
# (harmless).  Tests that pre-populate regime_probs with string keys
# ("RISK_ON") work against either definition because both use the name as
# the value.
try:
    from src.research.macro.regimes import Regime  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover -- T12 not yet landed at import time

    class Regime(str, Enum):
        """Local fallback; superseded by ``src.research.macro.regimes.Regime``.

        Values MUST match T12's canonical enum so cache entries written
        under the fallback are interchangeable with entries written under
        T12's enum.
        """

        RISK_ON = "RISK_ON"
        DEFLATION_SCARE = "DEFLATION_SCARE"
        INFLATION_ACCEL = "INFLATION_ACCEL"
        REAL_YIELD_SHOCK = "REAL_YIELD_SHOCK"
        RECESSION = "RECESSION"


if TYPE_CHECKING:
    from src.llm.model_router import ModelRouter
    from src.research.data import AssetConfig


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Tolerance on the "probabilities sum to 1.0" check.  The LLM is allowed
#: to be slightly off without forcing a retry (Metis EC2 -- "don't be
#: pedantic about float arithmetic the model can't do in its head").
_PROB_TOLERANCE: float = 0.05

#: Cache TTL -- entries older than 24h force a re-fetch even if the
#: ``(date, ticker)`` key matches.  Matches the spec's "TTL = 1 day".
_CACHE_TTL: timedelta = timedelta(days=1)

#: Cache filename (under ``cache_dir``).
_CACHE_FILENAME: str = "narrator_cache.parquet"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class LLMJudgeError(RuntimeError):
    """Raised when the LLM fails to produce valid output after one retry.

    Caller (T14 :class:`MacroRegimeModel`) catches this and falls back
    to rules-only mode (``alpha = 1.0``).
    """


# ---------------------------------------------------------------------------
# Pydantic structured output
# ---------------------------------------------------------------------------


class RegimeJudgeOutput(BaseModel):
    """Structured LLM output: regime probabilities + narrative.

    Fields
    ------
    regime_probs : dict[Regime, float]
        5 probabilities (one per :class:`Regime`), summing to 1.0
        +/- ``_PROB_TOLERANCE``.  The LLM emits string keys
        ("RISK_ON" etc.) which pydantic coerces into :class:`Regime`
        enum members.
    narrative : str
        2-3 sentence explanation of the call, citing at least one
        historical analog.  ``min_length=20`` filters trivially-short
        LLM deflections.
    """

    regime_probs: dict[Regime, float] = Field(
        ...,
        description="5 probabilities (one per Regime), summing to ~1.0",
    )
    narrative: str = Field(
        ...,
        min_length=20,
        description="2-3 sentence explanation citing a historical analog",
    )

    @field_validator("regime_probs")
    @classmethod
    def _probabilities_sum_to_one(
        cls, v: dict[Regime, float]
    ) -> dict[Regime, float]:
        """Reject sums outside [1.0 - tol, 1.0 + tol] OR any p ∉ [0, 1]."""
        if not v:
            raise ValueError("regime_probs must not be empty")
        probs = [float(p) for p in v.values()]
        for regime, p in zip(v.keys(), probs):
            if not (0.0 <= p <= 1.0):
                raise ValueError(
                    f"regime_probs[{regime.value if isinstance(regime, Regime) else regime}]"
                    f" = {p} out of [0, 1] range"
                )
        total = sum(probs)
        if not (1.0 - _PROB_TOLERANCE <= total <= 1.0 + _PROB_TOLERANCE):
            raise ValueError(
                f"regime_probs must sum to ~1.0 "
                f"(tolerance {_PROB_TOLERANCE}); got {total}"
            )
        return v


# ---------------------------------------------------------------------------
# LLMJudgeNarrator
# ---------------------------------------------------------------------------


class LLMJudgeNarrator:
    """Single-call LLM narrator producing :class:`RegimeJudgeOutput`.

    Usage (live mode)::

        async with ModelRouter() as router:
            narrator = LLMJudgeNarrator(model_router=router)
            output = await narrator.judge_and_narrate(
                factor_snapshot=snapshot_dict,
                trajectory=factor_df.tail(180),
                asset_config=AssetRegistry["BTC"],
                timestamp=as_of_dt,
            )

    Backtest mode: do NOT construct this narrator at all (or never call
    ``judge_and_narrate``); T14's ``use_llm=False`` enforces that.
    """

    JUDGE_PROMPT = """You are a macroeconomist assessing the current market regime.

Given:
- Current factor snapshot (z-scored values, latest observation):
{factor_snapshot}
- 6-month trajectory (first -> last, with delta):
{trajectory_summary}
- Recent Fed statements (last 90 days):
{fed_statements}
- Asset under analysis: {asset_ticker} ({asset_class})

Assess the probability of each of the following 5 macro regimes:
- RISK_ON: growth strong, volatility low, equities / risk assets favored
- DEFLATION_SCARE: falling inflation expectations, flight to long bonds
- INFLATION_ACCEL: rising inflation, pressure on nominal bonds, commodities bid
- REAL_YIELD_SHOCK: sharp rise in real yields, discount-rate stress on duration
- RECESSION: Sahm-triggered, growth contracting, defensive posture

Produce JSON ONLY (no markdown fences, no commentary, no leading prose):
{{
  "regime_probs": {{
    "RISK_ON": <0-1>,
    "DEFLATION_SCARE": <0-1>,
    "INFLATION_ACCEL": <0-1>,
    "REAL_YIELD_SHOCK": <0-1>,
    "RECESSION": <0-1>
  }},
  "narrative": "<2-3 sentences explaining the call, citing at least one historical analog>"
}}

Constraints:
- Probabilities MUST sum to 1.0.
- Narrative MUST be at least 20 characters and reference a historical analog
  (e.g. "similar to Q4 2018", "echoes of the 1973 oil shock", "1995 soft-landing setup").
"""

    RETRY_PROMPT = """Your previous response was malformed or failed schema validation.

Output ONLY valid JSON -- NO markdown fences (```), NO commentary, NO leading text.
The very first character of your response MUST be `{{` and the last MUST be `}}`.

Schema reminder (probabilities sum to 1.0, each in [0, 1]; narrative >= 20 chars):

{schema}

Now try again. Respond with the JSON object ONLY.
"""

    def __init__(
        self,
        model_router: ModelRouter | None = None,
        cache_dir: Path | str = Path("data/macro"),
    ) -> None:
        #: ModelRouter instance (or None in rules-only mode -- caller must
        #: not invoke ``judge_and_narrate`` then).
        self._router: ModelRouter | None = model_router
        self.cache_dir: Path = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_path: Path = self.cache_dir / _CACHE_FILENAME

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def judge_and_narrate(
        self,
        factor_snapshot: dict[str, float],
        trajectory: pd.DataFrame,
        asset_config: AssetConfig,
        timestamp: datetime | None = None,
        fed_statements: str = "",
    ) -> RegimeJudgeOutput:
        """Produce a :class:`RegimeJudgeOutput` for one asset at one point in time.

        Parameters
        ----------
        factor_snapshot
            ``{factor_name: value}`` for the current date (typically the
            last row of ``MacroFactorProvider.load_factors`` as a dict).
            Values may be raw or z-scored; the LLM treats them as context.
        trajectory
            Trailing ~6-month factor frame (used for narrative colour; the
            LLM does NOT do math on it -- we precompute first/last/delta).
        asset_config
            :class:`src.research.data.AssetConfig` whose regime is being
            judged.  ``ticker`` and ``asset_class`` are injected into the
            prompt; ``ticker`` also forms part of the cache key.
        timestamp
            Evaluation time.  Defaults to ``datetime.now(timezone.utc)``.
            ``timestamp.date()`` is the "as-of" part of the cache key.
        fed_statements
            Optional recent central-bank statements.  **v1 stub**: callers
            pass ``""`` and the prompt notes "no recent statements available".
            TODO(T15+): wire Fed RSS / FOMC-minute retrieval.

        Returns
        -------
        RegimeJudgeOutput

        Raises
        ------
        LLMJudgeError
            If the LLM fails to produce valid output after one retry.
            The caller (T14) catches this and falls back to rules-only.
        """
        ts = timestamp or datetime.now(timezone.utc)
        # Normalise tz: compare everything in UTC for cache TTL arithmetic.
        if ts.tzinfo is not None:
            ts = ts.astimezone(timezone.utc).replace(tzinfo=None)

        # 1. Cache lookup (returns None on miss / stale / corrupt).
        cached = self._read_cache(ts.date(), asset_config.ticker)
        if cached is not None:
            logger.info(
                f"narrator: cache hit for {asset_config.ticker} @ {ts.date()}"
            )
            return cached

        # 2. Build prompt.
        trajectory_summary = self._summarise_trajectory(trajectory)
        prompt = self.JUDGE_PROMPT.format(
            factor_snapshot=json.dumps(factor_snapshot, default=str, indent=2),
            trajectory_summary=trajectory_summary,
            fed_statements=fed_statements or "(no recent statements available)",
            asset_ticker=asset_config.ticker,
            asset_class=asset_config.asset_class,
        )

        # 3. Call the LLM with one retry on validation failure.
        output = await self._call_with_retry(prompt)

        # 4. Cache and return.
        self._write_cache(ts.date(), asset_config.ticker, output=output, cached_at=ts)
        return output

    # ------------------------------------------------------------------
    # LLM call + retry
    # ------------------------------------------------------------------

    async def _call_with_retry(self, prompt: str) -> RegimeJudgeOutput:
        """Call the router; on validation failure, retry once with RETRY_PROMPT."""
        if self._router is None:
            raise LLMJudgeError(
                "LLMJudgeNarrator has no ModelRouter -- cannot call the LLM. "
                "Either pass model_router= at construction, or run in "
                "rules-only mode (T14 use_llm=False)."
            )

        # --- First attempt ---
        try:
            raw = await self._generate(prompt)
            return self._parse_and_validate(raw)
        except (ValidationError, ValueError, json.JSONDecodeError, TypeError) as exc:
            logger.warning(
                f"narrator: first LLM call failed validation ({type(exc).__name__}): "
                f"{exc}; retrying with stricter prompt"
            )

        # --- Retry with stricter prompt ---
        retry_prompt = self.RETRY_PROMPT.format(schema=self._schema_reminder())
        try:
            raw = await self._generate(retry_prompt)
            return self._parse_and_validate(raw)
        except (ValidationError, ValueError, json.JSONDecodeError, TypeError) as exc:
            logger.error(f"narrator: retry LLM call also failed: {exc}")
            raise LLMJudgeError(
                "LLM failed to produce a valid RegimeJudgeOutput after retry"
            ) from exc

    async def _generate(self, prompt: str) -> str | None:
        """Route the prompt through ModelRouter; return raw text content.

        Uses ``capability="structured_output"`` so ModelRouter picks the
        best model for JSON-shaped responses (per its capability map).
        """
        assert self._router is not None  # checked by caller (_call_with_retry)
        messages: list[dict[str, str]] = [{"role": "user", "content": prompt}]
        response: Any = await self._router.generate(
            messages=messages,
            capability="structured_output",
            max_tokens=600,
            temperature=0.2,
        )
        if not response or "choices" not in response:
            return None
        try:
            return response["choices"][0]["message"].get("content")
        except (KeyError, IndexError, TypeError):
            return None

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_and_validate(raw: str | None) -> RegimeJudgeOutput:
        """JSON-parse + pydantic-validate the LLM's text response.

        Raises ``json.JSONDecodeError`` on malformed JSON,
        ``pydantic.ValidationError`` on schema violation, or
        ``ValueError`` on empty input.  The caller catches all three.
        """
        if not raw or not raw.strip():
            raise ValueError("Empty LLM response")
        cleaned = LLMJudgeNarrator._strip_markdown_fences(raw)
        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            raise ValueError(
                f"LLM response must be a JSON object; got {type(parsed).__name__}"
            )
        return RegimeJudgeOutput.model_validate(parsed)

    @staticmethod
    def _strip_markdown_fences(text: str) -> str:
        """Remove ````` ```` / `````json ```` fences if present.

        Many chat-tuned models wrap JSON in markdown fences despite
        instructions.  This is a *non-fatal* normalisation -- the first
        call doesn't fail just because of fences.
        """
        text = text.strip()
        # Match ```json\n...\n``` OR ```\n...\n``` (with DOTALL so newlines
        # inside are captured).
        match = re.match(
            r"^```(?:json|JSON)?\s*\n?(.*?)\n?```\s*$", text, re.DOTALL
        )
        if match:
            return match.group(1).strip()
        return text

    @staticmethod
    def _schema_reminder() -> str:
        """JSON skeleton echoed back to the LLM in the retry prompt."""
        return json.dumps(
            {
                "regime_probs": {
                    "RISK_ON": 0.2,
                    "DEFLATION_SCARE": 0.2,
                    "INFLATION_ACCEL": 0.2,
                    "REAL_YIELD_SHOCK": 0.2,
                    "RECESSION": 0.2,
                },
                "narrative": ">= 20 chars; cite a historical analog (e.g. 'Q4 2018 selloff')",
            },
            indent=2,
        )

    # ------------------------------------------------------------------
    # Trajectory summary (prompt context only; LLM does no math)
    # ------------------------------------------------------------------

    @staticmethod
    def _summarise_trajectory(trajectory: pd.DataFrame | None) -> str:
        """Compact per-factor summary: ``first -> last (Δ=...)`` over the window.

        The LLM gets the *change* pre-computed; we do not ask it to do
        arithmetic.  Returns a placeholder string on empty / unreadable
        input so the prompt still renders.
        """
        if trajectory is None or not isinstance(trajectory, pd.DataFrame):
            return "(no trajectory data available)"
        if trajectory.empty:
            return "(trajectory is empty)"

        try:
            first = trajectory.iloc[0]
            last = trajectory.iloc[-1]
            lines: list[str] = []
            for col in trajectory.columns:
                v0 = first.get(col)
                v1 = last.get(col)
                if pd.isna(v1):
                    lines.append(f"  {col}: NaN")
                    continue
                if pd.isna(v0):
                    lines.append(f"  {col}: {v1}")
                    continue
                try:
                    delta = float(v1) - float(v0)
                    lines.append(f"  {col}: {v0} -> {v1} (delta={delta:+.3f})")
                except (TypeError, ValueError):
                    lines.append(f"  {col}: {v0} -> {v1}")
            return "\n".join(lines) if lines else "(no numeric columns)"
        except Exception as exc:  # pragma: no cover -- defensive
            logger.warning(f"narrator: trajectory summary failed: {exc}")
            return f"(trajectory summary unavailable: {exc})"

    # ------------------------------------------------------------------
    # Cache (single parquet file, atomic write)
    # ------------------------------------------------------------------

    def _read_cache(
        self, cache_date: date, ticker: str
    ) -> RegimeJudgeOutput | None:
        """Return a cached entry if present and within TTL, else ``None``.

        Stale (>24h old), corrupt, or missing caches all return ``None``;
        the caller treats that as a cache miss and re-fetches.
        """
        if not self._cache_path.exists():
            return None
        try:
            df = pd.read_parquet(self._cache_path)
        except Exception as exc:
            logger.warning(
                f"narrator: corrupt cache {self._cache_path}: {exc}; ignoring"
            )
            return None
        if df.empty or "cache_date" not in df.columns:
            return None

        mask = (df["cache_date"] == pd.Timestamp(cache_date)) & (
            df["ticker"] == ticker
        )
        hits = df.loc[mask]
        if hits.empty:
            return None

        # Latest write wins (defensive against duplicate keys).
        row = hits.iloc[-1]
        cached_at = pd.to_datetime(row["cached_at"])
        # Coerce to tz-naive UTC for arithmetic against ``datetime.utcnow``.
        if getattr(cached_at, "tzinfo", None) is not None:
            cached_at = cached_at.tz_convert("UTC").tz_localize(None)

        age = datetime.now(timezone.utc).replace(tzinfo=None) - cached_at.to_pydatetime()
        if age > _CACHE_TTL:
            logger.debug(
                f"narrator: cache stale for {ticker} @ {cache_date} "
                f"(age={age}, ttl={_CACHE_TTL})"
            )
            return None

        try:
            probs_raw = json.loads(row["regime_probs_json"])
            probs = {Regime(k): float(v) for k, v in probs_raw.items()}
            return RegimeJudgeOutput(
                regime_probs=probs,
                narrative=str(row["narrative"]),
            )
        except Exception as exc:
            logger.warning(
                f"narrator: cache row parse failed for {ticker} @ {cache_date}: {exc}"
            )
            return None

    def _write_cache(
        self,
        cache_date: date,
        ticker: str,
        output: RegimeJudgeOutput,
        cached_at: datetime,
    ) -> None:
        """Append-or-overwrite a ``(date, ticker)`` row; atomic write."""
        new_row = pd.DataFrame(
            [
                {
                    "cache_date": pd.Timestamp(cache_date),
                    "ticker": ticker,
                    # Enum keys -> their string values for JSON round-trip.
                    "regime_probs_json": json.dumps(
                        {
                            (r.value if isinstance(r, Regime) else str(r)): float(p)
                            for r, p in output.regime_probs.items()
                        }
                    ),
                    "narrative": output.narrative,
                    "cached_at": pd.Timestamp(cached_at),
                }
            ]
        )

        # Load existing, drop any prior row for this key, append new, save.
        existing = pd.DataFrame()
        if self._cache_path.exists():
            try:
                existing = pd.read_parquet(self._cache_path)
            except Exception as exc:
                logger.warning(
                    f"narrator: cache read-before-write failed ({exc}); "
                    "starting fresh"
                )
                existing = pd.DataFrame()

        if not existing.empty and "cache_date" in existing.columns:
            keep = ~(
                (existing["cache_date"] == pd.Timestamp(cache_date))
                & (existing["ticker"] == ticker)
            )
            existing = existing.loc[keep]

        combined = pd.concat([existing, new_row], ignore_index=True)

        # Atomic write: .tmp then rename (matches factors.py pattern).
        tmp = self._cache_path.with_suffix(self._cache_path.suffix + ".tmp")
        combined.to_parquet(tmp, index=False)
        tmp.replace(self._cache_path)
