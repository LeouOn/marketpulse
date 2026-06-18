"""MacroRegimeModel -- weighted ensemble of rules + LLM judge (W3/T14).

This is the top-level "regime classifier" the rest of the research lab
talks to.  It blends two complementary signals:

* :class:`src.research.macro.regimes.RulesBasedClassifier` (T12) -- a
  deterministic, backward-looking, sigmoid-driven 5-regime probability
  classifier.  Always runs.  Always reproducible.  This is the
  backtest-safe baseline.
* :class:`src.research.macro.narrator.LLMJudgeNarrator` (13) -- an async,
  probabilistic LLM call that returns regime probabilities + a 2-3
  sentence narrative citing a historical analog.  Skipped by default;
  callers opt in per-call via ``use_llm=True`` AND ``alpha < 1.0``.

The blend is a single convex combination::

    final_p[r] = alpha * rules_p[r] + (1 - alpha) * llm_p[r]    for r in Regime

where ``alpha in [0, 1]``.  ``alpha = 1.0`` means "rules only" (LLM is
not consulted even if ``use_llm=True``); ``alpha = 0.0`` would mean "LLM
only" (caller's choice; rarely sensible).  Typical live use is
``alpha = 0.7`` (70% rules, 30% LLM).

Design constraints (Metis MUST NOT / G7)
----------------------------------------

* **Backtest determinism.**  ``use_llm`` defaults to ``False``.  In a
  backtest the caller MUST NOT set ``use_llm=True`` (the LLM is
  nondeterministic and would make the backtest irreproducible).
* **No silent LLM invocation.**  ``alpha < 1.0`` + ``use_llm=False`` is
  an ambiguous configuration (the operator asked for a blend but didn't
  enable the LLM) -- we reject it with :class:`ValueError` rather than
  silently running rules-only.
* **No silent rules fallback on misconfig.**  ``use_llm=True`` with no
  judge wired in is also rejected (the operator asked for the LLM but
  didn't provide one).
* **Graceful degradation on LLM failure.**  If the judge raises
  :class:`src.research.macro.narrator.LLMJudgeError` (or any other
  exception), we catch it, log a warning, and return the rules-only
  result with ``source="rules"`` so the caller's pipeline doesn't crash.
* **Async-only.**  :meth:`MacroRegimeModel.classify` is a coroutine --
  the LLM call is async even when skipped (consistent signature for
  callers in both backtest and live mode).

Public API
----------

* :class:`RegimeClassification` -- frozen result dataclass.
* :class:`MacroRegimeModel` -- the ensembler.  Construct once with a
  classifier (required) + optional judge; call :meth:`classify` per
  timestamp.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

import pandas as pd
from loguru import logger

from src.research.macro.narrator import LLMJudgeNarrator
from src.research.macro.regimes import Regime, RulesBasedClassifier

if TYPE_CHECKING:
    from src.research.data import AssetConfig


# ---------------------------------------------------------------------------
# RegimeClassification -- the result contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegimeClassification:
    """Outcome of one :meth:`MacroRegimeModel.classify` call.

    Frozen so callers can safely cache / hash results (regime labels are
    frequently used as dict keys downstream).

    Fields
    ------
    regime : Regime
        ``argmax`` of ``probs``.  The single "what regime are we in?"
        label most consumers want.
    probs : dict[Regime, float]
        5 probabilities (one per :class:`Regime`), summing to ~1.0.
        Keyed by :class:`Regime` enum members (NOT strings).
    alpha : float
        The ensemble weight the caller requested.  ``1.0`` = rules-only.
        Reported back even on LLM-failure fallback (so the caller can
        tell what they asked for vs. what ran -- check ``source``).
    narrative : str | None
        The LLM's 2-3 sentence explanation if ``use_llm=True`` AND the
        call succeeded.  ``None`` for rules-only runs and for ensemble
        runs that fell back after an LLM failure.
    source : str
        ``"rules"`` (deterministic baseline, or LLM-failure fallback) or
        ``"ensemble"`` (successful rules + LLM blend).
    timestamp : datetime | None
        When the classification was made / the as-of point in the
        factor frame.  ``None`` means "use the last row of factor_df".
    """

    regime: Regime
    probs: dict[Regime, float]
    alpha: float
    narrative: str | None
    source: str
    timestamp: datetime | None = None


# ---------------------------------------------------------------------------
# MacroRegimeModel -- the ensembler
# ---------------------------------------------------------------------------


class MacroRegimeModel:
    """Weighted ensemble of :class:`RulesBasedClassifier` + :class:`LLMJudgeNarrator`.

    Construct once per (classifier, judge) pair -- typically once at
    research-lab startup -- then call :meth:`classify` for each
    timestamp / asset you want labelled.

    Parameters
    ----------
    rules : RulesBasedClassifier
        The deterministic rules-based classifier (T12).  Required.
    judge : LLMJudgeNarrator | None
        The LLM narrator (T13).  Optional -- if ``None``, the model is
        rules-only forever and any ``use_llm=True`` call raises a
        :class:`ValueError`.

    Example
    -------
    >>> from src.research.macro.regimes import RulesBasedClassifier
    >>> from src.research.macro.model import MacroRegimeModel
    >>> model = MacroRegimeModel(rules=RulesBasedClassifier())   # judge=None
    >>> # Backtest-safe call (deterministic):
    >>> # result = await model.classify(factor_df)  # doctest: +SKIP
    """

    #: Trajectory window handed to the LLM for narrative context
    #: (matches the spec's "6-month factor trajectory" requirement).
    _TRAJECTORY_WINDOW_DAYS: int = 180

    def __init__(
        self,
        rules: RulesBasedClassifier,
        judge: LLMJudgeNarrator | None = None,
    ) -> None:
        self.rules: RulesBasedClassifier = rules
        self.judge: LLMJudgeNarrator | None = judge

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def classify(
        self,
        factor_df: pd.DataFrame,
        alpha: float = 1.0,
        use_llm: bool = False,
        timestamp: datetime | None = None,
        asset_config: AssetConfig | None = None,
    ) -> RegimeClassification:
        """Classify the macro regime at one point in time.

        Parameters
        ----------
        factor_df : pd.DataFrame
            Daily-indexed 12-column macro factor frame from T11's
            :class:`MacroFactorProvider`.  The rules classifier consumes
            the whole frame (it needs the 5-year trailing z-score
            window); the LLM only sees the snapshot + trajectory at
            ``timestamp``.
        alpha : float, default 1.0
            Ensemble weight in ``[0, 1]``.  ``1.0`` = rules-only (the
            default; backtest-safe).  ``< 1.0`` requires ``use_llm=True``
            or the call is rejected (Metis G7 -- ambiguous config).
        use_llm : bool, default False
            Whether to consult the LLM judge.  ``False`` by default so
            the model is inert in a backtest unless the caller
            explicitly opts in.
        timestamp : datetime | None, default None
            As-of point.  ``None`` means "the last row of factor_df".
            Otherwise the row at-or-before ``timestamp`` is used (so a
            historical replay can ask "what regime was the model in on
            2018-12-15?").
        asset_config : AssetConfig | None, default None
            Required only when ``use_llm=True`` (the narrator uses
            ``ticker`` for its cache key).  Ignored on the rules-only
            path.

        Returns
        -------
        RegimeClassification

        Raises
        ------
        ValueError
            * ``alpha < 1.0`` AND ``use_llm=False`` (ambiguous -- reject).
            * ``use_llm=True`` AND ``self.judge is None`` (no LLM wired).
            * ``timestamp`` is before the start of ``factor_df``.
        """
        # ----- Guardrails (Metis G7) -----------------------------------
        if alpha < 1.0 and not use_llm:
            raise ValueError(
                f"alpha={alpha} < 1.0 requires use_llm=True. "
                f"Set use_llm=True (and provide a judge) or alpha=1.0 "
                f"for rules-only classification."
            )

        if use_llm and self.judge is None:
            raise ValueError(
                "use_llm=True but no LLMJudgeNarrator was provided in the "
                "MacroRegimeModel constructor. Pass judge=LLMJudgeNarrator(...) "
                "or set use_llm=False."
            )

        # ----- Always compute rules probs (deterministic baseline) -----
        rules_probs_df = self.rules.classify(factor_df)

        # Slice to the requested timestamp (or take the last row).
        if timestamp is not None:
            mask = rules_probs_df.index <= pd.Timestamp(timestamp)
            if not mask.any():
                raise ValueError(
                    f"timestamp {timestamp} is before the start of factor_df "
                    f"(first index: {rules_probs_df.index[0]})."
                )
            rules_probs = rules_probs_df.loc[mask].iloc[-1].to_dict()
        else:
            rules_probs = rules_probs_df.iloc[-1].to_dict()

        # ----- Decide whether to consult the LLM -----------------------
        # LLM runs only when ALL three hold: opted in, blend requested,
        # and a judge is wired.  (Guardrails above already proved that
        # if alpha < 1.0 then use_llm=True, and if use_llm=True then
        # judge is not None -- so this predicate is well-formed.)
        should_use_llm = use_llm and alpha < 1.0 and self.judge is not None

        if should_use_llm:
            final_probs, narrative, source = await self._ensemble(
                factor_df=factor_df,
                rules_probs=rules_probs,
                alpha=alpha,
                timestamp=timestamp,
                asset_config=asset_config,
            )
        else:
            final_probs = self._normalize_to_regimes(rules_probs)
            narrative = None
            source = "rules"

        # Argmax for the single-regime label.
        regime = Regime(max(final_probs, key=final_probs.get))

        return RegimeClassification(
            regime=regime,
            probs=final_probs,
            alpha=alpha,
            narrative=narrative,
            source=source,
            timestamp=timestamp,
        )

    # ------------------------------------------------------------------
    # Ensemble path
    # ------------------------------------------------------------------

    async def _ensemble(
        self,
        *,
        factor_df: pd.DataFrame,
        rules_probs: dict,
        alpha: float,
        timestamp: datetime | None,
        asset_config: AssetConfig | None,
    ) -> tuple[dict[Regime, float], str | None, str]:
        """Run the LLM judge and blend its output with the rules probs.

        Returns ``(final_probs, narrative, source)``.  On ANY exception
        from the judge, logs a warning and falls back to rules-only
        (``source="rules"``, ``narrative=None``).
        """
        assert self.judge is not None  # checked by caller

        # The narrator needs an AssetConfig (it uses ticker for the
        # cache key).  If the caller didn't pass one, we cannot call
        # the LLM -- fall back to rules rather than crashing.
        if asset_config is None:
            logger.warning(
                "MacroRegimeModel: use_llm=True but asset_config is None; "
                "the LLM narrator needs a ticker for its cache key. "
                "Falling back to rules-only."
            )
            return self._normalize_to_regimes(rules_probs), None, "rules"

        factor_snapshot = self._build_snapshot(factor_df, timestamp)
        trajectory = self._build_trajectory(factor_df, timestamp)

        try:
            llm_output = await self.judge.judge_and_narrate(
                factor_snapshot=factor_snapshot,
                trajectory=trajectory,
                asset_config=asset_config,
                timestamp=timestamp,
            )
        except Exception as exc:
            # LLMJudgeError, network errors, validation errors -- any
            # failure mode triggers the rules-only fallback so the
            # caller's pipeline stays up.
            logger.warning(
                f"MacroRegimeModel: LLMJudgeNarrator failed ({type(exc).__name__}: "
                f"{exc}); falling back to rules-only."
            )
            return self._normalize_to_regimes(rules_probs), None, "rules"

        llm_probs = llm_output.regime_probs  # dict[Regime, float]
        narrative = llm_output.narrative

        # Weighted ensemble.  Both inputs are ~normalised distributions,
        # so the convex combination is also ~normalised (sums to ~1.0).
        # We key everything by Regime enum so the result is type-stable.
        final_probs: dict[Regime, float] = {}
        for r in Regime:
            rules_p = self._lookup_regime(rules_probs, r)
            llm_p = self._lookup_regime(llm_probs, r)
            final_probs[r] = alpha * rules_p + (1.0 - alpha) * llm_p

        return final_probs, narrative, "ensemble"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _lookup_regime(probs: dict, r: Regime) -> float:
        """Fetch ``probs[r]`` tolerating both Regime and string keys.

        The rules classifier returns a dict keyed by Regime *values*
        (strings like ``"RISK_ON"``); the LLM narrator returns a dict
        keyed by :class:`Regime` enum members.  This helper accepts
        either and always returns a ``float`` (0.0 if missing -- should
        not happen in practice but is defensive).
        """
        v = probs.get(r)
        if v is None:
            v = probs.get(r.value, 0.0)
        return float(v)

    @staticmethod
    def _normalize_to_regimes(probs: dict) -> dict[Regime, float]:
        """Coerce a string-or-Regime-keyed dict to ``dict[Regime, float]`` summing to 1.

        The rules classifier returns ``{regime_value_string: prob}`` --
        this re-keys by :class:`Regime` member and renormalises so the
        caller always sees a well-formed distribution regardless of
        floating-point drift or missing keys.
        """
        out: dict[Regime, float] = {}
        for r in Regime:
            out[r] = MacroRegimeModel._lookup_regime(probs, r)
        total = sum(out.values())
        if total > 0:
            out = {k: v / total for k, v in out.items()}
        return out

    def _build_snapshot(
        self, factor_df: pd.DataFrame, timestamp: datetime | None
    ) -> dict[str, float | None]:
        """Latest factor values as a flat dict for LLM input.

        ``timestamp=None`` means "last row".  NaN values are converted
        to ``None`` so the JSON serialiser the narrator uses doesn't
        choke (``json.dumps(float('nan'))`` produces ``NaN`` which is
        invalid JSON).
        """
        if timestamp is not None:
            mask = factor_df.index <= pd.Timestamp(timestamp)
            if not mask.any():
                # Defensive: classify() already validated this, but the
                # LLM snapshot is built after the rules slice -- keep
                # the guard local so a future caller can't trigger an
                # IndexError here.
                row = factor_df.iloc[-1]
            else:
                row = factor_df.loc[mask].iloc[-1]
        else:
            row = factor_df.iloc[-1]
        return {
            str(k): (None if pd.isna(v) else float(v)) for k, v in row.items()
        }

    def _build_trajectory(
        self, factor_df: pd.DataFrame, timestamp: datetime | None
    ) -> pd.DataFrame:
        """Last ~6 months of factor data for LLM trajectory analysis.

        The narrator doesn't do math on this frame -- it precomputes a
        per-factor ``first -> last (delta=...)`` summary for the prompt.
        We still hand it a DataFrame (not the summary) so the narrator
        owns the summarisation logic (single source of truth).
        """
        if timestamp is not None:
            end = pd.Timestamp(timestamp)
        else:
            end = factor_df.index[-1]
        start = end - pd.Timedelta(days=self._TRAJECTORY_WINDOW_DAYS)
        traj = factor_df.loc[start:end]
        if traj.empty:
            # Edge case: timestamp is the very first row.  Hand back
            # at least one row so the narrator's summary doesn't crash.
            return factor_df.loc[:end].tail(1)
        return traj
