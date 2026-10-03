"""Bottom-signal evaluation engine for the BTC bottom study (wave 2a).

Owned by g4 under the shared contract.  Where wave 1 produced *causal
candidate signals*, this module answers, per signal and per horizon
(cycle / swing):

    "Would this signal have told you, before the low was identifiable,
    that a low was near - and how often does it cry wolf?"

Every number is reported as **k of n** with the count visible.  With
about 4 cycle lows nothing here can prove anything; the engine's job is
to rank evidence and expose what is luck.

Design decisions (challenge these)
----------------------------------
1. **Episodes, not days, are the actionable unit.**  A fire episode is
   a maximal run of fire days, with runs separated by fewer than
   ``cooldown`` calendar days merged (gap = next start - previous end;
   merged when ``gap <= cooldown``).  Episode START is the actionable
   date.  NA fire days act as False for episode finding: you cannot
   act on "unknown".
2. **Hit, lead, usable, late.**  For event ``b`` an episode hits when
   its start lies in ``[bottom_date - pre_window, confirm_date]``.
   ``lead = bottom_date - first_hit_start`` days (positive = before the
   low; negative = after).  A hit is usable by construction (it starts
   no later than ``confirm_date``); episodes starting in
   ``(confirm_date, bottom_date + post_window]`` are counted
   **late** - they fired, but only after the low was already
   identifiable.  Events with no hit and at least one late episode are
   ``late_only``; the rest are ``missed``.
3. **The base rate is the comparator.**  Precision = fraction of ALL
   episodes with a bottom of this horizon inside
   ``[start, start + forward_window]``.  The base rate is the same
   fraction over ALL days.  Lift = precision / base_rate.  Without the
   base rate, "it fired near lows" is vacuous - bottoms cluster where
   drawdowns live.
4. **Placebo, not p-values.**  The fire series is circularly shifted
   (autocorrelation and fire rate preserved; edge wrap-around is a
   known, documented artefact) and the add-one fraction
   ``(1 + matches) / (1 + N)`` of shifted copies matching or beating
   the observed hits / lift is reported, so exactly 0 is impossible.
   Shifts are drawn only from offsets that displace the series at
   least ``pre_window + cooldown`` days from zero in both directions:
   near-zero shifts are near-copies of the observed alignment and
   would contaminate the null.  The eligible count (and any fallback)
   is stated in the output, along with the resolution limit
   ``max(1/(shifts+1), 1/(n_events+1))``.
5. **Pre-registration discipline.**  The PRIMARY analysis uses only
   the registry default thresholds (wave 1); the neighbourhood grid is
   robustness (median / min / max reported, never only the best cell)
   and every cell tried is counted - the multiple-comparisons
   denominator.  Combinations are allowed only from an explicitly
   passed short list and join that denominator.  The most recent event
   gets a separate report-only view and is never used to pick
   thresholds.  ``leave_one_out`` reports each cycle held out in turn.
6. **Overlapping windows are flagged, never treated as independent.**
   Forward-return tables report counts and the number of overlapping
   episode pairs; the unconditional comparator overlaps by
   construction and says so.  A forward return whose window extends
   past the last data date is NaN (right-censoring made explicit, with
   ``n_valid`` per window) - never a padded short-window return under
   a long-window label; the same rule marks incomplete further-drawdown
   windows.
7. **Purity.**  All functions are deterministic and side-effect free:
   no I/O, no network, no LLM endpoints; randomness only inside
   ``placebo`` behind a fixed seed (a stdlib ``warnings.warn`` on the
   documented too-few-eligible-shifts fallback is the one exception).
   Per-horizon study defaults (``HORIZON_DEFAULTS`` / ``config_for``)
   keep ``pre_window`` / ``forward_window`` / ``cooldown`` honest for
   cycle vs swing horizons; explicit caller keys always win.

What this engine CANNOT tell you (read before quoting any number)
------------------------------------------------------------------
- With ~4 cycle lows, hit rates move in jumps of 1/n; nothing here is
  significance.  The placebo bounds "how surprising is this given the
  signal's own autocorrelation", not "is the true hit rate > x".
- Thresholds were chosen after looking at history (by wave 1 and by
  anyone who sweeps the grid); the primary/default analysis is a
  discipline, not a guarantee of pre-registration.
- Circular shifts preserve the *marginal* fire pattern, not its
  relation to volatility clustering; a signal that fires on drawdown
  depth can look "significant" against shifts simply because bottoms
  and deep drawdowns coincide by construction.  Lift vs base rate is
  the honest headline; the placebo is a floor check on luck.
- Leave-one-out with n=4 says "did one cycle carry the result", no
  more.

Dependencies: pandas / numpy only, plus ``.signals`` for the sweep
(a thin re-entry - the sweep must use the exact wave-1 fire columns).
Events come from g3 per the contract (``find_bottoms``); this module
consumes any DataFrame with ``bottom_date`` / ``confirm_date``
(plus optional ``horizon``, ``provisional``, ``bottom_price``).
"""

from __future__ import annotations

import itertools
import warnings
from dataclasses import dataclass, field, fields, replace
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

__all__ = [
    "StudyConfig",
    "HORIZON_DEFAULTS",
    "EpisodeTable",
    "PlaceboResult",
    "SweepResult",
    "ForwardReport",
    "config_for",
    "episodes",
    "evaluate",
    "summarise",
    "placebo",
    "sweep",
    "evaluate_combination",
    "leave_one_out",
    "latest_event_view",
    "forward_returns",
    "render_markdown",
]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StudyConfig:
    """Evaluation parameters (all in calendar days; keep them simple).

    pre_window      an episode counts as a hit for event b if it starts
                    in [bottom_date - pre_window, confirm_date].
    cooldown        fire runs separated by <= this many days merge into
                    one episode (gap = next start - previous end).
    forward_window  horizon for precision / base rate / forward returns.
    post_window     late episodes are those starting in
                    (confirm_date, bottom_date + post_window];
                    defaults to forward_window when None.
    horizon         filter events to this horizon when the events table
                    carries a horizon column ("cycle" / "swing").
    include_provisional
                    g3 marks lows that could still move as provisional;
                    they are excluded from the primary analysis unless
                    this is True (the exclusion count is reported).
    """

    pre_window: int = 180
    cooldown: int = 30
    forward_window: int = 180
    post_window: int | None = None
    horizon: str | None = None
    include_provisional: bool = False

    def __post_init__(self) -> None:
        if self.pre_window < 0 or self.cooldown < 0 or self.forward_window <= 0:
            raise ValueError("pre_window/cooldown must be >= 0 and forward_window > 0")
        if self.post_window is None:
            object.__setattr__(self, "post_window", self.forward_window)


# Per-horizon study defaults (see config_for docstring for the reasoning).
HORIZON_DEFAULTS: dict[str, StudyConfig] = {
    "cycle": StudyConfig(pre_window=180, forward_window=180, cooldown=30),
    "swing": StudyConfig(pre_window=30, forward_window=45, cooldown=10),
}


def config_for(horizon: str, **overrides: Any) -> StudyConfig:
    """StudyConfig for a horizon, with caller overrides on top.

    Justification for the shipped values (study defaults, not
    calibrated truths - wave 2b sweeps them):

    - ``cycle`` (pre 180 / forward 180 / cooldown 30): cycle lows are
      multi-month processes; the signals that precede them (drawdown
      depth, Mayer, weekly RSI) evolve over months, so a half-year
      pre-window spans the typical decline phase; 180 days forward is
      a quarter-plus of recovery; a 30-day cooldown merges monthly
      re-tests of the same bottom.
    - ``swing`` (pre 30 / forward 45 / cooldown 10): swing lows are
      weeks; a month of pre-window and ~6 weeks forward keep the
      question "did it call this swing, not the year"; a 10-day
      cooldown merges re-tests within a fortnight.

    Unknown horizons raise: the events contract fixes the vocabulary
    to {"cycle", "swing"}, so a typo must fail loudly.
    Explicit caller keys always win over the horizon defaults.
    """
    if horizon not in HORIZON_DEFAULTS:
        raise ValueError(
            f"unknown horizon {horizon!r}; known: {sorted(HORIZON_DEFAULTS)} (contract fixes the vocabulary)"
        )
    base = {f.name: getattr(HORIZON_DEFAULTS[horizon], f.name) for f in fields(StudyConfig)}
    unknown = set(overrides) - set(base)
    if unknown:
        raise ValueError(f"unknown config keys: {sorted(unknown)}; known: {sorted(base)}")
    return replace(HORIZON_DEFAULTS[horizon], **overrides)


def _resolve_config(cfg: Mapping[str, Any] | None) -> StudyConfig:
    """Config resolution shared by every entry point.

    Precedence: caller's explicit keys > per-horizon defaults (when a
    known ``horizon`` key is present) > StudyConfig defaults.  When the
    caller passes a StudyConfig instance it is used as-is.
    """
    if isinstance(cfg, StudyConfig):
        return cfg
    cfg = dict(cfg or {})
    horizon = cfg.get("horizon")
    if horizon is not None:
        if horizon not in HORIZON_DEFAULTS:
            raise ValueError(
                f"unknown horizon {horizon!r}; known: {sorted(HORIZON_DEFAULTS)} (contract fixes the vocabulary)"
            )
        # Horizon defaults as the base; explicit caller keys win.
        base = {f.name: getattr(HORIZON_DEFAULTS[horizon], f.name) for f in fields(StudyConfig)}
        base.update(cfg)
        return _coerce_config(base)
    return _coerce_config(cfg)


def _coerce_config(cfg: Mapping[str, Any] | None) -> StudyConfig:
    """Validate and build a StudyConfig from plain keys (no horizon logic)."""
    if cfg is None:
        return StudyConfig()
    if isinstance(cfg, StudyConfig):
        return cfg
    known = set(StudyConfig.__dataclass_fields__)
    unknown = set(cfg) - known
    if unknown:
        raise ValueError(f"unknown config keys: {sorted(unknown)}; known: {sorted(known)}")
    return StudyConfig(**dict(cfg))


# ---------------------------------------------------------------------------
# Event normalisation (thin adapter over g3's contract)
# ---------------------------------------------------------------------------


def _normalise_events(events: pd.DataFrame, cfg: StudyConfig) -> tuple[pd.DataFrame, dict[str, int]]:
    """Filter/typed events per the contract; report exclusion counts."""
    required = {"bottom_date", "confirm_date"}
    missing = required - set(events.columns)
    if missing:
        raise ValueError(f"events table missing required columns: {sorted(missing)}")
    ev = events.copy()
    for col in ("bottom_date", "confirm_date"):
        ev[col] = pd.to_datetime(ev[col])
    excluded: dict[str, int] = {"horizon": 0, "provisional": 0}
    if cfg.horizon is not None and "horizon" in ev.columns:
        keep = ev["horizon"] == cfg.horizon
        excluded["horizon"] = int((~keep).sum())
        ev = ev[keep]
    if "provisional" in ev.columns and not cfg.include_provisional:
        keep = ~ev["provisional"].astype(bool)
        excluded["provisional"] = int((~keep).sum())
        ev = ev[keep]
    return ev.sort_values("bottom_date").reset_index(drop=True), excluded


# ---------------------------------------------------------------------------
# Episodes
# ---------------------------------------------------------------------------


def episodes(fire: pd.Series, cooldown: int = 30) -> pd.DataFrame:
    """Maximal fire runs, merging runs closer than ``cooldown`` days.

    NA fire days read as False (you cannot act on "unknown").  Episode
    ``start`` is the actionable date; ``end`` the last fire day of the
    merged run; ``length_days`` the start-to-end span.
    """
    s = fire.astype("boolean").fillna(False).astype(bool)
    arr = s.to_numpy(dtype=bool)
    idx = s.index

    if not arr.any():
        return pd.DataFrame(columns=["start", "end", "length_days"])

    starts = np.flatnonzero(arr & ~np.concatenate(([False], arr[:-1])))
    ends = np.flatnonzero(arr & ~np.concatenate((arr[1:], [False])))

    # Merge runs whose gap (next start - previous end, in days) is
    # <= cooldown.  The index is a daily calendar grid per the frame
    # contract, so positional distance == day distance.
    day = idx.asi8 // (10**9 * 86400)  # ns -> days (tz-naive daily index)
    keep_start = [starts[0]]
    keep_end = [ends[0]]
    for st, en in zip(starts[1:], ends[1:], strict=True):
        if day[st] - day[keep_end[-1]] <= cooldown:
            keep_end[-1] = en
        else:
            keep_start.append(st)
            keep_end.append(en)

    start_ts = idx[keep_start]
    end_ts = idx[keep_end]
    return pd.DataFrame(
        {
            "start": start_ts,
            "end": end_ts,
            "length_days": (end_ts - start_ts).days,
        }
    )


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


@dataclass
class EpisodeTable:
    """Result of evaluate(): episodes, per-event outcomes, k-of-n metrics."""

    episodes: pd.DataFrame
    event_results: pd.DataFrame
    metrics: dict[str, float]
    config: StudyConfig
    label: str = ""


def _base_rate(day_ordinals: np.ndarray, bottoms_ord: np.ndarray, forward: int) -> tuple[int, int]:
    """Fraction of days d with a bottom in [d, d + forward] (k of n)."""
    n = len(day_ordinals)
    if n == 0 or len(bottoms_ord) == 0:
        return 0, n
    covered = np.zeros(n, dtype=bool)
    for b in bottoms_ord:
        lo = np.searchsorted(day_ordinals, b - forward, side="left")
        hi = np.searchsorted(day_ordinals, b, side="right")
        covered[lo:hi] = True
    return int(covered.sum()), n


def _hits_per_episode(starts_ord: np.ndarray, bottoms_ord: np.ndarray, forward: int) -> np.ndarray:
    """Episode starts with any bottom in [start, start + forward]."""
    if len(starts_ord) == 0 or len(bottoms_ord) == 0:
        return np.zeros(len(starts_ord), dtype=bool)
    lo = np.searchsorted(bottoms_ord, starts_ord, side="left")  # first bottom >= start
    hi = np.searchsorted(bottoms_ord, starts_ord + forward, side="right")  # first > start+F
    return hi > lo


def evaluate(
    fire: pd.Series,
    events: pd.DataFrame,
    label: str = "",
    **cfg: Any,
) -> EpisodeTable:
    """Evaluate one fire series against one events table.

    Returns an :class:`EpisodeTable`; the headline numbers live in
    ``.metrics`` and are all k-of-n: ``n_events``, ``n_covered``,
    ``hit_rate``, ``mean_lead_days``, ``min_lead_days``, ``max_lead_days``,
    ``n_late_only``, ``n_missed``, ``n_episodes``, ``n_episode_hits``,
    ``precision``, ``base_rate_k``/``base_rate_n``/``base_rate``,
    ``lift``, plus the exclusion counts from event normalisation.
    """
    conf = _resolve_config(dict(cfg) if cfg else None)
    ev, excluded = _normalise_events(events, conf)
    eps = episodes(fire, conf.cooldown)
    s = fire.astype("boolean").fillna(False).astype(bool)
    day = s.index.asi8 // (10**9 * 86400)

    bottoms_ord = ev["bottom_date"].values.astype("datetime64[D]").astype(np.int64)
    confirm_ord = ev["confirm_date"].values.astype("datetime64[D]").astype(np.int64)
    starts_ord = (
        eps["start"].values.astype("datetime64[D]").astype(np.int64) if len(eps) else np.array([], dtype=np.int64)
    )

    rows = []
    leads: list[int] = []
    for i, (b, c) in enumerate(zip(bottoms_ord, confirm_ord, strict=True)):
        in_hit = (starts_ord >= b - conf.pre_window) & (starts_ord <= c)
        hit_starts = starts_ord[in_hit]
        covered = bool(in_hit.any())
        lead = int(b - hit_starts.min()) if covered else None
        if covered:
            leads.append(lead)
        in_late = (starts_ord > c) & (starts_ord <= b + (conf.post_window or 0))
        rows.append(
            {
                "event": i,
                "bottom_date": ev["bottom_date"].iloc[i],
                "confirm_date": ev["confirm_date"].iloc[i],
                "covered": covered,
                "first_hit_start": pd.Timestamp(hit_starts.min(), unit="D") if covered else pd.NaT,
                "lead_days": lead,
                "n_hit_episodes": int(in_hit.sum()),
                "n_late_episodes": int(in_late.sum()),
                "late_only": (not covered) and bool(in_late.any()),
            }
        )
    event_results = pd.DataFrame(rows)

    ep_hits = _hits_per_episode(starts_ord, bottoms_ord, conf.forward_window)
    n_ep = len(eps)
    n_ep_hits = int(ep_hits.sum())
    precision = n_ep_hits / n_ep if n_ep else float("nan")

    bk, bn = _base_rate(day, bottoms_ord, conf.forward_window)
    base_rate = bk / bn if bn else float("nan")
    lift = precision / base_rate if base_rate and n_ep else float("nan")

    n_events = len(ev)
    metrics: dict[str, float] = {
        "n_events": n_events,
        "n_covered": int(event_results["covered"].sum()) if n_events else 0,
        "hit_rate": (int(event_results["covered"].sum()) / n_events) if n_events else float("nan"),
        "mean_lead_days": float(np.mean(leads)) if leads else float("nan"),
        "min_lead_days": float(np.min(leads)) if leads else float("nan"),
        "max_lead_days": float(np.max(leads)) if leads else float("nan"),
        "n_late_only": int(event_results["late_only"].sum()) if n_events else 0,
        "n_missed": (
            n_events - int(event_results["covered"].sum()) - int(event_results["late_only"].sum()) if n_events else 0
        ),
        "n_episodes": n_ep,
        "n_episode_hits": n_ep_hits,
        "precision": precision,
        "base_rate_k": bk,
        "base_rate_n": bn,
        "base_rate": base_rate,
        "lift": lift,
        "events_excluded_horizon": excluded["horizon"],
        "events_excluded_provisional": excluded["provisional"],
    }
    return EpisodeTable(episodes=eps, event_results=event_results, metrics=metrics, config=conf, label=label)


def summarise(results: Mapping[str, EpisodeTable]) -> pd.DataFrame:
    """One row per evaluated signal, k-of-n counts kept visible."""
    rows = []
    for name, et in results.items():
        m = et.metrics
        rows.append(
            {
                "signal": name or et.label,
                "covered": f"{int(m['n_covered'])}/{int(m['n_events'])}",
                "hit_rate": m["hit_rate"],
                "mean_lead_days": m["mean_lead_days"],
                "late_only": int(m["n_late_only"]),
                "missed": int(m["n_missed"]),
                "episodes": int(m["n_episodes"]),
                "episode_hits": f"{int(m['n_episode_hits'])}/{int(m['n_episodes'])}",
                "precision": m["precision"],
                "base_rate": f"{int(m['base_rate_k'])}/{int(m['base_rate_n'])}",
                "lift": m["lift"],
            }
        )
    return pd.DataFrame(rows).set_index("signal")


# ---------------------------------------------------------------------------
# Placebo
# ---------------------------------------------------------------------------


@dataclass
class PlaceboResult:
    """Circular-shift placebo for one evaluation.

    ``p_hits`` / ``p_lift`` are the fractions of shifted copies whose
    hit count / lift match or beat the observed value.  The
    ``power_note`` must accompany any quoted number - it states the
    resolution limit instead of pretending to a p-value.
    """

    n_shifts: int
    observed_hits: int
    observed_lift: float
    p_hits: float
    p_lift: float
    n_lift_nan: int
    power_note: str = ""
    n_eligible_shifts: int = 0
    exclusion_zone: int = 0


def placebo(
    fire: pd.Series,
    events: pd.DataFrame,
    shifts: int = 2000,
    seed: int = 42,
    **cfg: Any,
) -> PlaceboResult:
    """Circularly shift the fire series and compare hits / lift.

    Shifting preserves the fire pattern (autocorrelation, fire rate);
    the wrap-around at the series edges is a known artefact, acceptable
    because the study period is much longer than any episode.  The base
    rate is shift-invariant and computed once.  Deterministic for a
    fixed seed.
    """
    conf = _resolve_config(dict(cfg) if cfg else None)
    observed = evaluate(fire, events, **_cfg_as_kwargs(conf))
    obs_hits = int(observed.metrics["n_covered"])
    obs_lift = observed.metrics["lift"]

    arr = fire.astype("boolean").fillna(False).astype(bool).to_numpy()
    n = len(arr)
    rng = np.random.default_rng(seed)
    # Exclusion zone: tiny shifts leave the fire geometry nearly
    # aligned with the real events (a near-copy of the observed
    # alignment), contaminating the null in the conservative
    # direction and inflating every p.  Eligible shifts displace the
    # series at least pre_window + cooldown days from zero in BOTH
    # directions (k and n-k, the wrap-around twin).
    zone = conf.pre_window + conf.cooldown
    lo, hi = zone, n - zone  # inclusive bounds on k
    n_eligible = hi - lo + 1 if hi >= lo else 0
    fell_back = False
    if n_eligible < 20:
        warnings.warn(
            f"placebo: only {n_eligible} shifts outside the exclusion zone "
            f"(zone={zone} days, series={n} days); falling back to all "
            "shifts - p values are contaminated by near-copies",
            stacklevel=2,
        )
        lo, hi, n_eligible, fell_back = 1, n - 1, n - 2, True
    shifted_hits = np.empty(shifts, dtype=int)
    shifted_lift = np.empty(shifts, dtype=float)
    for i in range(shifts):
        k = int(rng.integers(lo, hi + 1))
        shifted = pd.Series(np.roll(arr, k), index=fire.index)
        m = evaluate(shifted, events, **_cfg_as_kwargs(conf)).metrics
        shifted_hits[i] = int(m["n_covered"])
        shifted_lift[i] = m["lift"]

    # Add-one form everywhere: (1 + #{shifted >= observed}) / (1 + N),
    # so a p of exactly 0 is never printed (1.0 remains possible when
    # every shifted copy matches or beats the observation).
    with np.errstate(invalid="ignore"):
        p_hits = float((1 + np.count_nonzero(shifted_hits >= obs_hits)) / (shifts + 1))
        finite = np.isfinite(shifted_lift)  # elementwise mask, no ambiguous `and`
        if np.isfinite(obs_lift) and finite.any():
            n_finite = int(np.count_nonzero(finite))
            p_lift = float((1 + np.count_nonzero(shifted_lift[finite] >= obs_lift)) / (n_finite + 1))
        else:
            p_lift = float("nan")
    n_events = int(observed.metrics["n_events"])
    resolution = max(1.0 / (shifts + 1), 1.0 / (n_events + 1))
    zone_note = (
        f" Shifts drawn from {n_eligible} eligible offsets outside a "
        f"{zone}-day exclusion zone"
        + (" (FELL BACK to all shifts - near-copy contamination)" if fell_back else "")
        + "."
    )
    note = (
        f"Placebo resolution is limited: smallest reportable fraction ~{resolution:.3f} "
        f"({shifts} shifts, {n_events} events).{zone_note} Add-one form "
        "(1 + matches) / (1 + N). This bounds luck given the signal's own "
        "autocorrelation and fire rate; it is not a p-value and proves nothing."
    )
    return PlaceboResult(
        n_shifts=shifts,
        observed_hits=obs_hits,
        observed_lift=obs_lift,
        p_hits=p_hits,
        p_lift=p_lift,
        n_lift_nan=int(np.count_nonzero(~np.isfinite(shifted_lift))),
        n_eligible_shifts=n_eligible,
        exclusion_zone=zone,
        power_note=note,
    )


# ---------------------------------------------------------------------------
# Sweep (robustness only - the primary analysis is registry defaults)
# ---------------------------------------------------------------------------


@dataclass
class SweepResult:
    """Grid sweep over one signal's neighbourhood.

    ``rows`` has one row per cell (the default cell marked
    ``is_primary``); ``summary`` holds median / min / max of the key
    metrics over the non-primary cells; ``n_cells`` is the
    multiple-comparisons denominator.  Combinations evaluated
    elsewhere must be added to any quoted denominator by the caller.
    """

    signal: str
    rows: pd.DataFrame
    summary: dict[str, dict[str, float]]
    n_cells: int
    primary: dict[str, float]


def _grid_cells(grid: Mapping[str, Sequence[float]]) -> list[dict[str, float]]:
    keys = sorted(grid)
    return [dict(zip(keys, values, strict=True)) for values in itertools.product(*(grid[k] for k in keys))]


def sweep(
    df: pd.DataFrame,
    signal_name: str,
    events: pd.DataFrame,
    grid: Mapping[str, Sequence[float]] | None = None,
    label: str = "",
    **cfg: Any,
) -> SweepResult:
    """Evaluate ``signal_name`` across its registry neighbourhood grid.

    Re-computes the wave-1 signals per cell (``compute_signals`` with
    the cell's parameter overrides) - intentionally the exact fire
    columns wave 1 ships, not a re-implementation.  The default cell is
    evaluated as PRIMARY and excluded from the robustness summary.
    """
    from src.research.btc_bottoms.signals import SIGNAL_REGISTRY, compute_signals

    kind, _default, registry_grid = SIGNAL_REGISTRY[signal_name]
    fire_col = signal_name if kind == "boolean" else f"{signal_name}_fire"
    cells = _grid_cells(dict(grid) if grid is not None else dict(registry_grid))

    out_default = compute_signals(df)
    primary_metrics = evaluate(out_default[fire_col], events, label=label, **cfg).metrics
    primary_key = _primary_params(signal_name)

    rows = []
    for cell in cells:
        out = compute_signals(df, params={signal_name: cell})
        m = evaluate(out[fire_col], events, label=label, **cfg).metrics
        row = {"params": repr(cell), "is_primary": cell == primary_key}
        row.update({k: m[k] for k in PRIMARY_METRIC_KEYS})
        rows.append(row)
    frame = pd.DataFrame(rows)

    non_primary = frame[~frame["is_primary"]]
    summary = {
        k: {
            "median": float(non_primary[k].median()) if len(non_primary) else float("nan"),
            "min": float(non_primary[k].min()) if len(non_primary) else float("nan"),
            "max": float(non_primary[k].max()) if len(non_primary) else float("nan"),
        }
        for k in PRIMARY_METRIC_KEYS
    }
    return SweepResult(
        signal=signal_name,
        rows=frame,
        summary=summary,
        n_cells=len(cells),
        primary={k: primary_metrics[k] for k in PRIMARY_METRIC_KEYS},
    )


PRIMARY_METRIC_KEYS = (
    "n_covered",
    "n_events",
    "hit_rate",
    "mean_lead_days",
    "n_episodes",
    "precision",
    "lift",
)


def _primary_params(signal_name: str) -> dict[str, float]:
    """The registry-default parameters for a signal, as a cell dict."""
    from src.research.btc_bottoms.signals import DEFAULT_PARAMS, SIGNAL_REGISTRY

    kind, default_threshold, _grid = SIGNAL_REGISTRY[signal_name]
    cell = dict(DEFAULT_PARAMS.get(signal_name, {}))
    if default_threshold is not None:
        cell.setdefault("threshold", default_threshold)
    return cell


def evaluate_combination(
    fires: Mapping[str, pd.Series],
    events: pd.DataFrame,
    **cfg: Any,
) -> EpisodeTable:
    """Evaluate the AND of the named fire series.

    Only combinations from a short, explicitly declared list should be
    evaluated (contract rule 8); each evaluated combination must be
    counted in the multiple-comparisons denominator by the caller.
    NA days read as False via the episode finder (Kleene AND with an
    unknown leg never acts).
    """
    names = list(fires)
    if not names:
        raise ValueError("combination needs at least one fire series")
    combined = None
    for s in fires.values():
        b = s.astype("boolean")
        combined = b if combined is None else (combined & b)
    label = " & ".join(names)
    return evaluate(combined.astype("boolean"), events, label=label, **cfg)


# ---------------------------------------------------------------------------
# Leave-one-out and the latest-event report-only view
# ---------------------------------------------------------------------------


def leave_one_out(fire: pd.Series, events: pd.DataFrame, **cfg: Any) -> pd.DataFrame:
    """Re-evaluate with each event held out in turn.

    One row per held-out event (identified by its bottom_date), plus
    the recomputed metrics on the remaining events.  With n=4 cycles
    this answers "did one cycle carry the result" and nothing more.
    """
    conf = _resolve_config(dict(cfg) if cfg else None)
    ev, _excluded = _normalise_events(events, conf)
    rows = []
    for i in range(len(ev)):
        held_out = ev.iloc[[i]]
        rest = ev.drop(index=i)
        m = evaluate(fire, rest, **_cfg_as_kwargs(conf)).metrics
        row = {"held_out_bottom": held_out["bottom_date"].iloc[0]}
        row.update({k: m[k] for k in PRIMARY_METRIC_KEYS})
        rows.append(row)
    return pd.DataFrame(rows)


def _cfg_as_kwargs(conf: StudyConfig) -> dict[str, Any]:
    return {
        "pre_window": conf.pre_window,
        "cooldown": conf.cooldown,
        "forward_window": conf.forward_window,
        "post_window": conf.post_window,
        "horizon": conf.horizon,
        "include_provisional": conf.include_provisional,
    }


def latest_event_view(fire: pd.Series, events: pd.DataFrame, **cfg: Any) -> dict[str, Any]:
    """Report-only view of the most recent event (never threshold fuel).

    The most recent event (e.g. the 2026 low) is intrinsically the one
    everyone tuned towards; it is reported separately and must never be
    used to pick thresholds.  The returned dict says so.
    """
    conf = _resolve_config(dict(cfg) if cfg else None)
    ev, _excluded = _normalise_events(events, conf)
    if ev.empty:
        return {"report_only": True, "note": "no events", "n_events": 0}
    last = ev.iloc[-1]
    et = evaluate(fire, ev.iloc[[-1]], **_cfg_as_kwargs(conf))
    er = et.event_results.iloc[0]
    return {
        "report_only": True,
        "bottom_date": last["bottom_date"],
        "confirm_date": last["confirm_date"],
        "covered": bool(er["covered"]),
        "lead_days": None if pd.isna(er["lead_days"]) else int(er["lead_days"]),
        "n_hit_episodes": int(er["n_hit_episodes"]),
        "n_late_episodes": int(er["n_late_episodes"]),
        "note": (
            "Report-only view of the most recent event; never use it to choose "
            "thresholds (pre-registration discipline, contract rule 7)."
        ),
    }


# ---------------------------------------------------------------------------
# What acting at the fire date would have meant
# ---------------------------------------------------------------------------


@dataclass
class ForwardReport:
    """Forward consequences of acting at episode starts.

    ``episode_returns`` / ``unconditional_returns``: DataFrames indexed
    by anchor day with the forward close-to-close return for each
    window.  A forward return is NaN unless the target date is <= the
    last index date: incomplete windows are right-censored and marked
    missing, never padded with the last close (which would silently
    report a short-window return under a long-window label).
    ``episode_n_valid`` / ``unconditional_n_valid`` report the valid
    count per window so the censoring is visible next to every
    distribution.  ``further_drawdown``: per episode, the worst bottom
    of the horizon inside ``forward_window`` relative to the start
    close; episodes whose forward window is not fully observed read
    NaN (counted in ``n_incomplete_drawdown``) instead of a
    partial-window worst value.  Overlap counts are reported, never
    divided away.
    """

    windows: tuple[int, ...]
    episode_returns: pd.DataFrame
    unconditional_returns: pd.DataFrame
    further_drawdown: pd.Series
    overlap_pairs: dict[int, int]
    unconditional_overlap_note: str
    episode_n_valid: dict[int, int] = field(default_factory=dict)
    unconditional_n_valid: dict[int, int] = field(default_factory=dict)
    n_incomplete_drawdown: int = 0


def forward_returns(
    fire: pd.Series,
    close: pd.Series,
    events: pd.DataFrame,
    windows: Sequence[int] = (30, 90, 180),
    **cfg: Any,
) -> ForwardReport:
    """Forward 30/90/180-day returns after episode starts vs all days.

    The unconditional comparator windows overlap by construction (every
    calendar day is an anchor); episode anchors may also overlap - the
    count of overlapping pairs per window is reported and the
    distributions must not be read as n independent draws.
    """
    conf = _resolve_config(dict(cfg) if cfg else None)
    ev, _excluded = _normalise_events(events, conf)
    eps = episodes(fire, conf.cooldown)
    close = close.astype(float)

    def _fwd(anchors: pd.DatetimeIndex) -> tuple[pd.DataFrame, dict[int, int]]:
        """Exact-grid forward returns; NaN when the window is incomplete."""
        out = {}
        n_valid: dict[int, int] = {}
        anchor_close = close.reindex(anchors)
        last_date = close.index[-1]
        for w in windows:
            target = anchors + pd.Timedelta(days=w)
            shifted = close.reindex(target)  # exact lookup: beyond-data -> NaN
            vals = shifted.to_numpy() / anchor_close.to_numpy() - 1.0
            vals[target > last_date] = np.nan  # censoring made explicit
            out[w] = vals
            n_valid[w] = int(np.count_nonzero(~np.isnan(vals)))
        return pd.DataFrame(out, index=anchors), n_valid

    ep_anchors = pd.DatetimeIndex(eps["start"]) if len(eps) else pd.DatetimeIndex([])
    episode_returns, episode_n_valid = _fwd(ep_anchors)
    unconditional_returns, unconditional_n_valid = _fwd(close.index)

    overlap: dict[int, int] = {}
    if len(ep_anchors) > 1:
        days = ep_anchors.asi8 // (10**9 * 86400)
        for w in windows:
            diffs = np.abs(days[:, None] - days[None, :])
            overlap[w] = int(np.count_nonzero((diffs > 0) & (diffs <= w)) // 2)

    # Further drawdown from each episode start to the next bottom.
    # An episode whose forward window runs past the last data date is
    # INCOMPLETE: report NaN (counted), not a partial-window worst.
    last_date = close.index[-1]
    n_incomplete = 0
    if len(eps) and "bottom_price" in ev.columns:
        starts_ord = eps["start"].values.astype("datetime64[D]").astype(np.int64)
        last_ord = np.datetime64(last_date, "D").astype(np.int64)
        bottoms_ord = ev["bottom_date"].values.astype("datetime64[D]").astype(np.int64)
        prices = ev["bottom_price"].to_numpy(dtype=float)
        start_close = close.reindex(pd.DatetimeIndex(eps["start"])).to_numpy()
        worst = np.full(len(eps), np.nan)
        for i, (s, sc) in enumerate(zip(starts_ord, start_close, strict=True)):
            if s + conf.forward_window > last_ord:
                n_incomplete += 1
                continue
            mask = (bottoms_ord >= s) & (bottoms_ord <= s + conf.forward_window)
            if mask.any() and np.isfinite(sc):
                worst[i] = prices[mask].min() / sc - 1.0
        further_dd = pd.Series(worst, index=pd.DatetimeIndex(eps["start"]), name="further_drawdown")
    else:
        further_dd = pd.Series(np.nan, index=ep_anchors, name="further_drawdown", dtype="float64")

    return ForwardReport(
        windows=tuple(windows),
        episode_returns=episode_returns,
        unconditional_returns=unconditional_returns,
        further_drawdown=further_dd,
        overlap_pairs=overlap,
        unconditional_overlap_note=(
            "Unconditional anchors are every calendar day: their windows overlap "
            "by construction. Episode anchors may overlap too (counts reported). "
            "Neither distribution is n independent draws. Windows extending past "
            "the last data date are censored to NaN; n_valid is shown per window."
        ),
        episode_n_valid=episode_n_valid,
        unconditional_n_valid=unconditional_n_valid,
        n_incomplete_drawdown=n_incomplete,
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _fmt(x: Any, digits: int = 3) -> str:
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "n/a"
    if isinstance(x, float):
        return f"{x:.{digits}f}"
    return str(x)


def _df_to_markdown(frame: pd.DataFrame) -> str:
    """Dependency-free markdown table (pandas to_markdown needs tabulate,
    which the shared venv does not install and must not be modified)."""
    if not len(frame):
        return "_(empty)_"
    cols = [str(c) for c in frame.reset_index().columns]
    rows = [[str(v) for v in row] for row in frame.reset_index().to_numpy()]
    align = []
    for j, _c in enumerate(cols):
        numeric = all(_is_num(r[j]) for r in rows) if rows else False
        align.append("---:" if numeric else ":---")
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(align) + " |"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def _is_num(value: Any) -> bool:
    try:
        float(value)
        return not isinstance(value, bool)
    except (TypeError, ValueError):
        return isinstance(value, float) and bool(np.isfinite(value))


def render_markdown(
    title: str,
    summary: pd.DataFrame | None = None,
    evaluations: Mapping[str, EpisodeTable] | None = None,
    placebos: Mapping[str, PlaceboResult] | None = None,
    sweep_results: Mapping[str, SweepResult] | None = None,
    latest: Mapping[str, Any] | None = None,
) -> str:
    """Render the study tables as markdown with every count visible.

    Pure string building; no I/O.  Sections are skipped when their
    input is absent, so a caller can assemble a partial report.
    """
    lines: list[str] = [f"# {title}", ""]
    lines.append(
        "_Every rate below is k of n with the count shown. With ~4 cycle lows "
        "nothing here is significance; the job is to rank evidence and expose "
        "what is luck._"
    )
    lines.append("")

    if summary is not None and len(summary):
        lines.append("## Primary analysis (registry defaults only)")
        lines.append("")
        lines.append(_df_to_markdown(summary))
        lines.append("")

    if evaluations:
        lines.append("## Per-event detail")
        lines.append("")
        for name, et in evaluations.items():
            m = et.metrics
            lines.append(
                f"- **{name or et.label}**: covered {int(m['n_covered'])}/{int(m['n_events'])} "
                f"(mean lead {_fmt(m['mean_lead_days'], 1)} d, late-only {int(m['n_late_only'])}, "
                f"missed {int(m['n_missed'])}); episodes {int(m['n_episode_hits'])}/{int(m['n_episodes'])} "
                f"near a bottom (precision {_fmt(m['precision'])}), base rate "
                f"{int(m['base_rate_k'])}/{int(m['base_rate_n'])}, lift {_fmt(m['lift'], 2)}"
                + (
                    f"; excluded {int(m['events_excluded_provisional'])} provisional events"
                    if m["events_excluded_provisional"]
                    else ""
                )
            )
        lines.append("")

    if placebos:
        lines.append("## Placebo (circular shifts)")
        lines.append("")
        for name, p in placebos.items():
            lines.append(
                f"- **{name}**: observed hits {p.observed_hits}; shifted copies matching or "
                f"beating them: {_fmt(p.p_hits)} ({p.n_shifts} shifts); lift p {_fmt(p.p_lift)}. " + p.power_note
            )
        lines.append("")

    if sweep_results:
        lines.append("## Robustness (grid sweep - NOT the primary analysis)")
        lines.append("")
        for name, sw in sweep_results.items():
            s = sw.summary
            lines.append(
                f"- **{name}**: {sw.n_cells} cells tried (multiple-comparisons denominator). "
                f"hit_rate median {_fmt(s['hit_rate']['median'])} "
                f"[min {_fmt(s['hit_rate']['min'])}, max {_fmt(s['hit_rate']['max'])}]; "
                f"lift median {_fmt(s['lift']['median'], 2)} "
                f"[min {_fmt(s['lift']['min'], 2)}, max {_fmt(s['lift']['max'], 2)}]. "
                "Median/min/max, never only the best cell."
            )
        lines.append("")

    if latest:
        lines.append("## Latest event (report only - never threshold fuel)")
        lines.append("")
        for name, view in latest.items():
            lines.append(f"- **{name}**: {view}")
        lines.append("")

    return "\n".join(lines)
