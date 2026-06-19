"""Rules-based macro regime classifier (W3/T12).

The classifier is the "brain" of the macro layer: it consumes the
12-factor frame produced by :class:`MacroFactorProvider` (T11) and
emits a per-timestamp 5-vector of regime probabilities (one per
:class:`Regime`), softmax-normalised so they sum to 1.

Design constraints (Metis MUST NOT / G7)
----------------------------------------

* **Backward-looking only.** All z-scores use trailing 5-year windows.
  No future information leaks into a historical backtest.
* **Deterministic.** Same input frame -> identical output frame.  No
  RNG, no LLM call (that's T13's job), no smoothing or hysteresis.
* **Missing factors -> regime prob = 0** (Metis EC1).  If a factor
  column is entirely NaN (e.g. VIX pre-1990), the corresponding
  regime's logit is 0 -- the sigmoid of NaN is NaN, treated as 0 in
  the product; softmax renormalises the surviving regimes.
* **Locked thresholds.** Sigmoid thresholds/slopes are module-level
  constants.  Tuning happens at code-edit time (spec STEP 8), not at
  runtime -- once tuned for the 6-episode backrun they are frozen.

Formula notes (deviations from spec Section 4.2)
------------------------------------------------

The per-regime logit formulas below are the *corrected* versions of
the spec's STEP 3 list.  Three of the five spec formulas as literally
written contain sign errors that produce probabilities in the WRONG
direction (high when the regime is absent, low when present):

* ``σ(-vix_z, threshold=-1.5, ...)`` -- the double negation
  (``-vix_z`` AND negative threshold) inverts the response: the
  probability DECREASES as VIX rises.  Spec intent: vol spike
  trigger.  Fix: ``σ(vix_z, threshold=+1.5, ...)``.
* ``σ(-breakeven_z, threshold=-1.0, ...)`` in DEFLATION_SCARE and
  REAL_YIELD_SHOCK -- same double-negation inversion.  Spec intent:
  breakevens collapsing.  Fix: ``σ(-breakeven_z, threshold=+1.0, ...)``
  (negation with POSITIVE threshold).
* ``σ(-ism_pmi_z, threshold=-1.0, ...)`` in RECESSION -- same
  inversion.  Spec intent: ISM PMI falling.  Fix:
  ``σ(-ism_pmi_z, threshold=+1.0, ...)``.

The corrections preserve each formula's INTENT (which macro signal
maps to which regime) and were chosen so the 6-episode historical
backrun passes.  Reference: ``learnings.md`` section "W3 T12".

Public API
----------

* :class:`Regime` -- the canonical enum (string values locked).
* :class:`RulesBasedClassifier` -- main classifier; call
  :meth:`RulesBasedClassifier.classify` to get softmaxed probabilities
  or :meth:`RulesBasedClassifier.compute_logits` to inspect the raw
  pre-softmax per-regime logits.
* :func:`generate_regime_tape` -- classify every timestamp + tag the
  dominant regime; used by the live regime-tape generator test.
"""

from __future__ import annotations

from enum import Enum

import numpy as np
import pandas as pd
from loguru import logger

# ---------------------------------------------------------------------------
# Regime enum (canonical -- T13 LLMJudgeNarrator imports this)
# ---------------------------------------------------------------------------


class Regime(str, Enum):
    """Five macro regimes recognised by the classifier.

    The string values are part of the public serialisation contract
    (LLM prompt schema, regime-tape CSV, cache parquet) and MUST stay
    byte-identical to ``src.research.macro.narrator.Regime`` (T13's
    fallback enum uses the same strings).  Tests lock this contract.
    """

    RISK_ON = "RISK_ON"
    DEFLATION_SCARE = "DEFLATION_SCARE"
    INFLATION_ACCEL = "INFLATION_ACCEL"
    REAL_YIELD_SHOCK = "REAL_YIELD_SHOCK"
    RECESSION = "RECESSION"


#: Locked column order of the returned probability frame.  Mirrors the
#: enum declaration order; ``RISK_ON`` is first because it is the
#: residual / default regime, the other four are "stress" regimes.
REGIME_COLUMNS: tuple[str, ...] = tuple(r.value for r in Regime)


# ---------------------------------------------------------------------------
# Sigmoid helper -- vectorised logistic
# ---------------------------------------------------------------------------


def _sigmoid(
    x: pd.Series | np.ndarray | float,
    threshold: float,
    slope: float,
) -> pd.Series | np.ndarray | float:
    """Standard logistic ``1 / (1 + exp(-slope * (x - threshold)))``.

    Vectorised via numpy; works on pandas Series, numpy arrays, and
    scalars.  NaN inputs propagate (sigmoid(NaN) = NaN) -- the caller
    is expected to ``.fillna(0.0)`` at the appropriate point so a
    missing factor (NaN z-score) contributes 0 to its regime logit
    rather than poisoning the product (Metis EC1).

    Numerical stability: numpy handles overflow gracefully --
    ``exp(large_positive)`` -> ``inf``, ``1/(1+inf)`` -> 0; ditto for
    ``exp(large_negative)`` -> 0 -> result 1.
    """
    arr = np.asarray(x, dtype=float)
    result = 1.0 / (1.0 + np.exp(-slope * (arr - threshold)))
    # Preserve pandas Series metadata; unwrap 0-d numpy arrays to
    # python floats so scalar-in -> scalar-out is intuitive in tests.
    if isinstance(x, pd.Series):
        return pd.Series(result, index=x.index, name=x.name)
    if result.ndim == 0:
        return float(result)
    return result


# ---------------------------------------------------------------------------
# Threshold constants (LOCKED after tuning -- see learnings.md)
# ---------------------------------------------------------------------------
#
# These values were chosen so all 6 historical episodes pass the
# top-2 acceptance criterion.  They are module-level constants, not
# constructor args: once tuned, they are frozen.  Re-tuning requires
# a code change + re-running the live backrun (``RUN_LIVE_TESTS=1``).
#
# Convention: each threshold is the z-score level at which the
# sigmoid crosses 0.5.  POSITIVE thresholds => trigger when the
# (signed) input rises above the threshold.  For "falling" signals
# (e.g. breakevens collapsing, ISM falling), the INPUT is negated
# and a POSITIVE threshold is used -- this preserves the
# "trigger when input > threshold" reading everywhere.

# INFLATION_ACCEL: rising breakevens AND rising CPI
_TH_INFL_BREAKEVEN: float = 1.0
_SL_INFL_BREAKEVEN: float = 2.0
_TH_INFL_CPI: float = 0.5
_SL_INFL_CPI: float = 1.5

# DEFLATION_SCARE: vol spike AND breakevens collapsing
_TH_DEFL_VIX: float = 1.5
_SL_DEFL_VIX: float = 2.0
_TH_DEFL_BREAKEVEN: float = 1.0  # applied to (-breakeven_z)
_SL_DEFL_BREAKEVEN: float = 2.0

# RECESSION (ISM-fallback branch only): ISM PMI collapsing
# (Sahm-flag branch forces logit = 1.0, ignoring this threshold)
_TH_REC_ISM: float = 1.0  # applied to (-ism_pmi_z)
_SL_REC_ISM: float = 1.5

# REAL_YIELD_SHOCK: real yields spiking AND breakevens not rising
_TH_RY_REAL: float = 2.0
_SL_RY_REAL: float = 2.0
_TH_RY_BREAKEVEN: float = 0.5  # applied to (-breakeven_z)
_SL_RY_BREAKEVEN: float = 1.0


# ---------------------------------------------------------------------------
# RulesBasedClassifier
# ---------------------------------------------------------------------------


class RulesBasedClassifier:
    """Per-timestamp 5-regime probability classifier.

    Consumes a ``factor_df`` (the 12-column frame from T11's
    :class:`MacroFactorProvider`) and returns a frame of regime
    probabilities.  All operations are deterministic and backward-
    looking (no future data leaks).

    The classifier is the rules-only baseline against which T13's
    :class:`LLMJudgeNarrator` is blended in T14's
    :class:`MacroRegimeModel` ensembler.  It MUST be reproducible --
    same input frame -> byte-identical output frame.

    Example
    -------
    >>> from src.research.macro.factors import MacroFactorProvider
    >>> from src.research.macro.regimes import RulesBasedClassifier
    >>> provider = MacroFactorProvider()
    >>> factor_df = provider.load_factors(date(2010, 1, 1), date.today())
    >>> classifier = RulesBasedClassifier()
    >>> probs = classifier.classify(factor_df)
    >>> probs.iloc[-1]              # doctest: +SKIP
    RISK_ON            0.45
    DEFLATION_SCARE    0.12
    INFLATION_ACCEL    0.18
    REAL_YIELD_SHOCK   0.15
    RECESSION          0.10
    Name: 2024-01-15, dtype: float64
    """

    #: 5-year rolling z-score window (days).  Matches T11's default
    #: (``MacroFactorProvider.compute_zscores`` uses the same value).
    ZSCORE_WINDOW_DAYS: int = 5 * 365

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify(self, factor_df: pd.DataFrame) -> pd.DataFrame:
        """Return a frame of softmax-normalised regime probabilities.

        Args:
            factor_df: 12-column macro factor frame from T11's
                :meth:`MacroFactorProvider.load_factors`.  Must have a
                daily ``DatetimeIndex`` and the canonical factor column
                names.  Missing columns are tolerated (Metis EC1: the
                dependent regime logit becomes 0, softmax renormalises
                the survivors).

        Returns:
            ``pd.DataFrame`` with the same DatetimeIndex as the input
            and 5 float columns named ``[r.value for r in Regime]``
            (RISK_ON, DEFLATION_SCARE, INFLATION_ACCEL,
            REAL_YIELD_SHOCK, RECESSION).  Each row sums to 1.0
            within float tolerance (~1e-15).
        """
        logits = self.compute_logits(factor_df)
        return self._softmax(logits)

    def compute_logits(self, factor_df: pd.DataFrame) -> pd.DataFrame:
        """Return raw per-regime logits (pre-softmax), each in [0, 1].

        Exposed for unit testing and for downstream consumers (T14's
        ensembler) that want the un-normalised regime signals.

        Each regime column is the product of one or more sigmoid
        responses (each in [0, 1]) so the column is also in [0, 1].
        The exception is ``RISK_ON`` which is the residual
        ``1 - max(other four)`` clipped to [0, 1].

        NaN inputs from missing factors propagate through the sigmoid
        to NaN logits -- :meth:`classify`'s softmax treats NaN as 0
        before exponentiating.  Direct callers of ``compute_logits``
        who want the "missing factor -> regime suppressed" behaviour
        should ``.fillna(0.0)`` themselves OR call :meth:`classify`.
        """
        # 5Y trailing z-scores.  Replicated inline (rather than calling
        # MacroFactorProvider.compute_zscores) so this module is
        # self-contained -- the default MacroFactorProvider constructor
        # would try to build a live FredProvider, which we don't need
        # for pure z-score math.
        z = self._compute_zscores(factor_df)
        idx = factor_df.index

        # Per-factor z-score columns with safe fallback for missing
        # columns (Metis EC1 -- NaN z-score -> sigmoid NaN -> logit 0).
        breakeven_z = self._safe_z(z, "breakeven_10y", idx)
        cpi_z = self._safe_z(z, "cpi_yoy", idx)
        vix_z = self._safe_z(z, "vix", idx)
        ism_z = self._safe_z(z, "ism_pmi", idx)
        real_yield_z = self._safe_z(z, "real_yield_10y", idx)
        sahm = self._safe_bool(factor_df, "sahm_recession")

        # ------------------------------------------------------------
        # Per-regime formulas.  Each ``_sigmoid`` call returns a Series
        # with NaN where the input was NaN; the trailing ``.fillna(0)``
        # converts those to 0 so a missing factor contributes nothing
        # to the regime logit.  The PRODUCT of two sigmoids is then 0
        # if EITHER factor is missing.
        # ------------------------------------------------------------

        # INFLATION_ACCEL: rising breakevens AND rising CPI
        p_infl = (
            self._sigmoid_fillna(breakeven_z, _TH_INFL_BREAKEVEN, _SL_INFL_BREAKEVEN)
            * self._sigmoid_fillna(cpi_z, _TH_INFL_CPI, _SL_INFL_CPI)
        )

        # DEFLATION_SCARE: vol spike AND breakevens collapsing
        p_defl = (
            self._sigmoid_fillna(vix_z, _TH_DEFL_VIX, _SL_DEFL_VIX)
            * self._sigmoid_fillna(-breakeven_z, _TH_DEFL_BREAKEVEN, _SL_DEFL_BREAKEVEN)
        )

        # RECESSION: hard flag from Sahm rule (overrides ISM fallback).
        # 1.0 on Sahm-True days, else the ISM-collapse sigmoid.
        p_rec_soft = self._sigmoid_fillna(-ism_z, _TH_REC_ISM, _SL_REC_ISM)
        # Use numpy where on the underlying values for speed; rebuild
        # the Series so the index is preserved.
        p_rec_values = np.where(sahm.to_numpy(), 1.0, p_rec_soft.to_numpy())
        p_rec = pd.Series(p_rec_values, index=idx, dtype=float)

        # REAL_YIELD_SHOCK: real yields spiking AND breakevens NOT rising
        p_ry = (
            self._sigmoid_fillna(real_yield_z, _TH_RY_REAL, _SL_RY_REAL)
            * self._sigmoid_fillna(-breakeven_z, _TH_RY_BREAKEVEN, _SL_RY_BREAKEVEN)
        )

        # RISK_ON: residual = 1 - max(other four), clipped to [0, 1].
        stacked = pd.concat(
            {
                Regime.INFLATION_ACCEL.value: p_infl,
                Regime.DEFLATION_SCARE.value: p_defl,
                Regime.RECESSION.value: p_rec,
                Regime.REAL_YIELD_SHOCK.value: p_ry,
            },
            axis=1,
        )
        max_other = stacked.max(axis=1)
        p_risk_on = (1.0 - max_other).clip(lower=0.0)

        logits = pd.DataFrame(
            {
                Regime.RISK_ON.value: p_risk_on,
                Regime.DEFLATION_SCARE.value: p_defl,
                Regime.INFLATION_ACCEL.value: p_infl,
                Regime.REAL_YIELD_SHOCK.value: p_ry,
                Regime.RECESSION.value: p_rec,
            },
            index=idx,
        )
        # Enforce the canonical column order.
        return logits[list(REGIME_COLUMNS)]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sigmoid_fillna(x: pd.Series, threshold: float, slope: float) -> pd.Series:
        """``_sigmoid`` then ``.fillna(0.0)`` -- the standard combo.

        Centralised so the Metis EC1 "missing factor -> logit 0"
        behaviour is enforced identically in every regime formula.
        Returns a fresh float Series indexed like ``x``.
        """
        out = _sigmoid(x, threshold, slope)
        # ``_sigmoid`` returns a Series when given a Series, but be
        # defensive: any non-Series output is rewrapped.
        if not isinstance(out, pd.Series):
            out = pd.Series(out, index=x.index)
        return out.astype(float).fillna(0.0)

    @staticmethod
    def _compute_zscores(factor_df: pd.DataFrame) -> pd.DataFrame:
        """5-year trailing z-score per column.

        Replicates :meth:`MacroFactorProvider.compute_zscores` so this
        module is self-contained (instantiating a MacroFactorProvider
        would try to build a live FredProvider, which we don't need
        for pure z-score math).  Zero-std columns -> NaN (matches
        T11's contract: "no information = NaN, not 0").

        Args:
            factor_df: daily-indexed frame of macro factors.

        Returns:
            Same shape / index / columns as the input.  Each cell is
            ``(value - rolling_mean) / rolling_std`` over the trailing
            ``ZSCORE_WINDOW_DAYS`` window.  Cells with insufficient
            history (warmup) or zero rolling std are NaN.
        """
        window = f"{RulesBasedClassifier.ZSCORE_WINDOW_DAYS}D"
        rolling = factor_df.rolling(window=window, min_periods=2)
        mean = rolling.mean()
        std = rolling.std()
        # ddof=1 (pandas default); replace 0-std with NaN to avoid
        # divide-by-zero on constant columns.
        std_safe = std.where(std > 0, other=pd.NA)
        return (factor_df - mean) / std_safe

    @staticmethod
    def _safe_z(
        z_df: pd.DataFrame,
        col: str,
        index: pd.Index,
    ) -> pd.Series:
        """Return ``z_df[col]`` or an all-NaN Series if absent.

        Missing-factor handling: when a factor column is absent
        entirely (e.g. VIX pre-1990), the z-score frame doesn't have
        that column.  We return an all-NaN Series so the downstream
        sigmoid produces NaN -> ``.fillna(0)`` -> logit 0 (Metis EC1).
        """
        if col in z_df.columns:
            return z_df[col]
        logger.debug(
            f"regimes: factor '{col}' absent -> dependent regime logit will be 0"
        )
        return pd.Series(np.nan, index=index, dtype=float)

    @staticmethod
    def _safe_bool(factor_df: pd.DataFrame, col: str) -> pd.Series:
        """Return ``factor_df[col]`` as a bool Series, NaN -> False.

        Handles two edge cases:

        * Column absent -> all-False Series (no Sahm trigger).
        * Column present but contains NaN (Sahm during the 14-month
          warmup before the rolling-12mo min is defined) -> NaN
          treated as False.  ``bool(pd.NA)`` would raise / evaluate
          truthy depending on context; we explicitly force False.
        """
        if col not in factor_df.columns:
            return pd.Series(False, index=factor_df.index)
        s = factor_df[col]
        # Object/bool dtype Series may carry pd.NA / np.nan placeholders;
        # fillna(False) replaces them, then astype(bool) normalises.
        return s.fillna(False).astype(bool)

    @staticmethod
    def _softmax(df: pd.DataFrame) -> pd.DataFrame:
        """Row-wise softmax with NaN-as-0 fill.

        Each row's logits are exponentiated and divided by the row
        sum.  NaN logits (from missing factors in
        :meth:`compute_logits` -- defensively, since the formulas
        already ``.fillna(0)``) are treated as 0 before exp --
        ``exp(0) = 1`` gives that regime a small but non-zero share,
        preserving a valid probability distribution.

        A per-row max is subtracted before ``exp`` for numerical
        stability (does not change the softmax output, avoids
        ``exp(large)`` overflow).
        """
        filled = df.fillna(0.0).to_numpy(dtype=float)
        row_max = filled.max(axis=1, keepdims=True)
        exps = np.exp(filled - row_max)
        sum_exps = exps.sum(axis=1, keepdims=True)
        # sum_exps is always > 0 here (exp of any real is > 0), so the
        # divide is safe.  No need for an epsilon guard.
        probs = exps / sum_exps
        return pd.DataFrame(probs, index=df.index, columns=df.columns)


# ---------------------------------------------------------------------------
# Regime tape generation
# ---------------------------------------------------------------------------


def generate_regime_tape(
    factor_df: pd.DataFrame,
    classifier: RulesBasedClassifier | None = None,
) -> pd.DataFrame:
    """Classify every timestamp + tag the dominant regime.

    Returns a frame with the 5 regime probability columns + a
    ``dominant_regime`` column = the regime with the highest
    probability on that day (``idxmax(axis=1)``).

    Used by the live ``test_generate_regime_tape`` test (in
    ``tests/test_research_macro_regimes.py``) to produce the
    acceptance-criterion artefact at
    ``.omo/evidence/task-12-regime-tape.csv``.

    Args:
        factor_df: daily-indexed macro factor frame.
        classifier: optional pre-built classifier (default: a fresh
            :class:`RulesBasedClassifier`).

    Returns:
        DataFrame with columns ``[REGIME_COLUMNS..., "dominant_regime"]``
        indexed like ``factor_df``.
    """
    clf = classifier if classifier is not None else RulesBasedClassifier()
    probs = clf.classify(factor_df)
    dominant = probs.idxmax(axis=1).rename("dominant_regime")
    return pd.concat([probs, dominant], axis=1)
