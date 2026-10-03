"""Q1 runner: signals alone, per the pre-registered plan (section 3).

Runs the 19 registry signals at their registry default thresholds
against the frozen frame and the plan's event sets, and writes the
machine-readable results plus human tables.  Every output repeats the
frame sha256 and the commit it ran on.  Nothing here tunes anything:
thresholds, event sets, label rule and conclusion language are fixed by
``docs/btc-bottom-study/00-plan.md`` (written before any result).

Standing limits (plan section 7, repeated in every report)
----------------------------------------------------------
Hindsight labels; ``confirm_date`` is optimistic (a +30% bounce occurred
before the final low in 2018, 2022 and 2026); the 2026 low is
provisional and can still move; MVRV-Z amplitude has decayed across
cycles; macro series revised after release are excluded; Coin Metrics
restates its latest days (treat the last 5 rows of on-chain columns as
provisional); BTC prices come from Yahoo; overlapping forward windows
are not independent draws; no trading costs or sizing are modelled;
yield-curve snapshots are not used in this study.

Honesty sentence (plan section 0, repeated in every report)
-----------------------------------------------------------
Pre-registration here is only partly honest: signal thresholds were
written by builders who know BTC's history, and some are textbook
numbers; "primary = defaults" is discipline against cherry-picking from
the sweep, not independence from the data.

Set P (the provisional 2026 low) never enters any rate, lift, placebo
or label; it appears only in the latest-episode view and the 2026
question table.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import warnings
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from src.research.btc_bottoms import study
from src.research.btc_bottoms.events import find_bottoms
from src.research.btc_bottoms.frame import FRAME_CACHE_NAME, asof, build_frame
from src.research.btc_bottoms.labels import label
from src.research.btc_bottoms.signals import SIGNAL_REGISTRY, compute_signals
from src.research.data._paths import cache_dir

#: Frozen frame hash fixed by the plan (section 1).
FRAME_SHA256 = "7e1107e2e653e493af552efdc516e99dd020a0855e73d3b4d1d917dc8247087e"

#: The +30% bounce that was broken by the June 2026 low (plan section 3:
#: prior-false-confirmation reference date for the 2026 question).
BOUNCE_2026 = pd.Timestamp("2026-05-10")

#: Plan section 3: primary family denominator (printed in every run).
PRIMARY_CELLS = len(SIGNAL_REGISTRY) * 2  # 19 signals x 2 horizons

PLACEBO_SHIFTS = 2000
PLACEBO_SEED = 42

__all__ = [
    "FRAME_SHA256",
    "verify_frame_hash",
    "load_study_data",
    "event_sets",
    "evaluable_events",
    "evaluate_signal_battery",
    "sweep_signal",
    "latest_question",
    "run",
    "main",
]


# ---------------------------------------------------------------------------
# Frozen data
# ---------------------------------------------------------------------------


def verify_frame_hash(path: Path | str, expected: str = FRAME_SHA256) -> str:
    """Return the frame's sha256; raise on mismatch (plan rule: never run on unfrozen data)."""
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if digest != expected:
        raise ValueError(
            f"frame hash mismatch: {path} is {digest}, plan expects {expected}; refusing to run on unfrozen data"
        )
    return digest


def _git_commit() -> str:
    try:
        root = Path(__file__).resolve().parents[3]
        return subprocess.run(  # noqa: S603 - fixed argv, read-only
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:  # pragma: no cover - offline / non-repo fallback
        return "unknown"


def load_study_data(frame_path: Path | None = None) -> dict[str, Any]:
    """Load the frozen frame, its asof view, and both event tables.

    Events come from the raw frame (plan section 1: ``find_bottoms(frame,
    horizon)`` with defaults); signals are computed on ``asof(frame, 5)``.
    """
    path = Path(frame_path) if frame_path else cache_dir() / FRAME_CACHE_NAME
    sha = verify_frame_hash(path)
    frame = build_frame(refresh=False)
    return {
        "sha256": sha,
        "commit": _git_commit(),
        "frame": frame,
        "frame_asof": asof(frame, 5),
        "events_cycle": find_bottoms(frame, "cycle"),
        "events_swing": find_bottoms(frame, "swing"),
    }


def event_sets(events_cycle: pd.DataFrame, events_swing: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Plan section 2 sets: A, B, S (plus pooled A+B, descriptive only)."""
    a = events_cycle[events_cycle["severity"] == "bear_bottom"].copy()
    b = events_cycle[
        (events_cycle["severity"] == "deep_correction") & (~events_cycle["provisional"].astype(bool))
    ].copy()
    p = events_cycle[events_cycle["provisional"].astype(bool)].copy()
    return {
        "A": a,
        "B": b,
        "P": p,
        "S": events_swing.copy(),
        "A+B (pooled, descriptive)": pd.concat([a, b], ignore_index=True),
    }


# ---------------------------------------------------------------------------
# Evaluability (plan section 2: rates are k of n_evaluable)
# ---------------------------------------------------------------------------


def evaluable_events(
    value: pd.Series, events: pd.DataFrame, pre_window: int
) -> tuple[pd.DataFrame, list[pd.Timestamp]]:
    """Keep only events whose hit window has at least one non-NaN value.

    An event is *evaluable* for a signal if the signal is non-NaN
    somewhere in ``[bottom_date - pre_window, confirm_date]``.  Events
    dropped for NaN are returned so the report can list them.
    """
    keep, dropped = [], []
    for _, row in events.iterrows():
        lo = row["bottom_date"] - pd.Timedelta(days=pre_window)
        window = value.loc[lo : row["confirm_date"]]
        (keep if window.notna().any() else dropped).append(row["bottom_date"])
    return events[events["bottom_date"].isin(keep)], dropped


# ---------------------------------------------------------------------------
# Per-signal battery (plan section 3)
# ---------------------------------------------------------------------------


def _horizon_of(set_name: str) -> str:
    return "swing" if set_name.startswith("S") else "cycle"


def evaluate_signal_battery(
    fire: pd.Series,
    value: pd.Series,
    events_by_set: Mapping[str, pd.DataFrame],
    close: pd.Series,
    placebo_shifts: int = PLACEBO_SHIFTS,
    placebo_seed: int = PLACEBO_SEED,
) -> dict[str, Any]:
    """evaluate / placebo / leave-one-out / forward returns per set.

    Set P is excluded here by construction (callers pass only the sets
    it may enter); pooled A+B gets evaluate-only metrics (the plan shows
    the pool next to A and B, descriptively, never silently).
    """
    out: dict[str, Any] = {}
    for set_name, events in events_by_set.items():
        horizon = _horizon_of(set_name)
        cfg = study.config_for(horizon)
        ev, dropped = evaluable_events(value, events, cfg.pre_window)
        pooled = "pooled" in set_name
        entry: dict[str, Any] = {"n_events": int(len(events)), "dropped_for_nan": [str(d.date()) for d in dropped]}
        if ev.empty:
            entry["metrics"] = {"n_events": 0}
            entry["label"] = "cannot evaluate"
            out[set_name] = entry
            continue
        et = study.evaluate(fire, ev, horizon=horizon)
        entry["metrics"] = {k: (None if pd.isna(v) else v) for k, v in et.metrics.items()}
        if pooled:
            entry["label"] = "pooled, descriptive only"
            out[set_name] = entry
            continue
        pl = study.placebo(fire, ev, shifts=placebo_shifts, seed=placebo_seed, horizon=horizon)
        entry["placebo"] = {
            "p_hits": pl.p_hits,
            "p_lift": None if np.isnan(pl.p_lift) else pl.p_lift,
            "n_eligible_shifts": pl.n_eligible_shifts,
            "exclusion_zone": pl.exclusion_zone,
        }
        loo = study.leave_one_out(fire, ev, horizon=horizon)
        loo_rates = loo["hit_rate"].dropna()
        entry["leave_one_out"] = {
            "min_hit_rate": float(loo_rates.min()) if len(loo_rates) else None,
            "rows": [
                {k: (str(v) if isinstance(v, pd.Timestamp) else v) for k, v in r.items()}
                for r in loo.to_dict(orient="records")
            ],
        }
        fr = study.forward_returns(fire, close, ev, horizon=horizon)
        entry["forward_returns"] = {
            "episode_n_valid": fr.episode_n_valid,
            "unconditional_n_valid": fr.unconditional_n_valid,
            "overlap_pairs": fr.overlap_pairs,
            "n_incomplete_drawdown": fr.n_incomplete_drawdown,
            "episode_quantiles": {str(w): _quantiles(fr.episode_returns[w]) for w in fr.windows},
            "unconditional_quantiles": {str(w): _quantiles(fr.unconditional_returns[w]) for w in fr.windows},
            "further_drawdown_quantiles": _quantiles(fr.further_drawdown),
        }
        out[set_name] = entry
    return out


def _quantiles(s: pd.Series) -> dict[str, float | None]:
    clean = s.dropna()
    if clean.empty:
        return {q: None for q in ("p10", "p25", "p50", "p75", "p90")}
    qs = clean.quantile([0.1, 0.25, 0.5, 0.75, 0.9])
    return {q: float(v) for q, v in zip(("p10", "p25", "p50", "p75", "p90"), qs, strict=True)}


def sweep_signal(
    df: pd.DataFrame,
    name: str,
    events_by_set: Mapping[str, pd.DataFrame],
    value: pd.Series,
) -> dict[str, Any]:
    """Registry-grid sweep per set (robustness only; cells counted)."""
    out: dict[str, Any] = {"n_cells": 0}
    for set_name, events in events_by_set.items():
        horizon = _horizon_of(set_name)
        cfg = study.config_for(horizon)
        ev, _dropped = evaluable_events(value, events, cfg.pre_window)
        if ev.empty:
            out[set_name] = {"lift_median": None, "lift_min": None, "lift_max": None}
            continue
        # study.sweep's summary medians emit a benign "Mean of empty
        # slice" RuntimeWarning when a metric column is all-NaN (e.g. a
        # grid cell where the signal never fires); the NaN result is
        # correct, the warning is noise. Suppressed here rather than
        # editing study.py (outside this task's territory).
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            sw = study.sweep(df, name, ev, horizon=horizon)
        if out["n_cells"] == 0:
            out["n_cells"] = sw.n_cells
        out[set_name] = {
            "lift_median": sw.summary["lift"]["median"],
            "lift_min": sw.summary["lift"]["min"],
            "lift_max": sw.summary["lift"]["max"],
            "hit_rate_median": sw.summary["hit_rate"]["median"],
        }
    return out


def label_from(battery: Mapping[str, Any], sweep: Mapping[str, Any], set_name: str) -> str:
    """Apply the plan-section-6 rule to one set's battery + sweep results."""
    entry = battery[set_name]
    metrics = entry["metrics"]
    loo_min = entry.get("leave_one_out", {}).get("min_hit_rate")
    p_lift = entry.get("placebo", {}).get("p_lift")
    sweep_med = sweep.get(set_name, {}).get("lift_median")
    n_eval = int(metrics.get("n_events", 0))
    lift = metrics.get("lift")
    # None here means the engine returned NaN for that input: missing
    # evidence (labels.py NaN policy) -> cannot evaluate.
    if n_eval == 0 or any(x is None for x in (loo_min, p_lift, sweep_med, lift)):
        return "cannot evaluate"
    return label(
        n_evaluable=n_eval,
        n_usable_leads=int(metrics["n_covered"]),
        lift=float(lift),
        n_episodes=int(metrics["n_episodes"]),
        placebo_p_lift=float(p_lift),
        sweep_median_lift=float(sweep_med),
        loo_min_hit_rate=float(loo_min),
    )


# ---------------------------------------------------------------------------
# The 2026 question (set P; never enters any rate above)
# ---------------------------------------------------------------------------


def latest_question(fire: pd.Series, close: pd.Series, p_event: pd.DataFrame) -> dict[str, Any]:
    """Per-signal 2026 table row: first fire vs the low and confirmation.

    Definitions (documented choices, plan section 3 wording kept):
    - "inside the 2026 episode" = fire days within the event's own span
      ``[peak_date, confirm_date]``.
    - "prior false confirmation" = any fire day in ``[peak_date,
      BOUNCE_2026]`` (the +30% bounce the plan says was broken by the
      June low).
    """
    row = p_event.iloc[0]
    span = fire.loc[row["peak_date"] : row["confirm_date"]]
    fired = span.fillna(False).astype(bool)
    low_close = float(close.loc[row["bottom_date"]])
    out: dict[str, Any] = {
        "bottom_date": str(row["bottom_date"].date()),
        "confirm_date": str(row["confirm_date"].date()),
        "prior_false_confirmation": bool(fire.loc[row["peak_date"] : BOUNCE_2026].fillna(False).astype(bool).any()),
    }
    if not fired.any():
        out.update(
            first_fire=None,
            days_vs_low=None,
            days_vs_confirm=None,
            close_at_first_fire=None,
        )
    else:
        first = fired[fired].index[0]
        c = float(close.loc[first])
        out.update(
            first_fire=str(first.date()),
            days_vs_low=int((row["bottom_date"] - first).days),
            days_vs_confirm=int((row["confirm_date"] - first).days),
            close_at_first_fire=c,
            premium_vs_low_close=c / low_close - 1.0,
        )
        last = close.index[-1]
        out["return_first_fire_to_last_row"] = float(close.loc[last] / c - 1.0)
    return out


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run(
    placebo_shifts: int = PLACEBO_SHIFTS,
    placebo_seed: int = PLACEBO_SEED,
    only_signals: list[str] | None = None,
    fires_override: Mapping[str, pd.Series] | None = None,
    data: Mapping[str, Any] | None = None,
    out_json: Path | str | None = None,
    out_md: Path | str | None = None,
) -> dict[str, Any]:
    """Run Q1 end to end and return the results dict (also writes files).

    ``only_signals`` / ``fires_override`` are test seams: production
    runs leave them None and every registry signal is computed from the
    frozen frame.
    """
    data = data or load_study_data()
    frame_asof: pd.DataFrame = data["frame_asof"]
    close = frame_asof["close"].astype(float)
    sets = event_sets(data["events_cycle"], data["events_swing"])
    names = list(only_signals) if only_signals else list(SIGNAL_REGISTRY)

    signals_out = compute_signals(frame_asof) if fires_override is None else None
    results: dict[str, Any] = {
        "frame_sha256": data["sha256"],
        "commit": data["commit"],
        "placebo": {"shifts": placebo_shifts, "seed": placebo_seed},
        "primary_cells": PRIMARY_CELLS,
        "sweep_cells_per_signal": {},
        "signals": {},
    }
    eval_sets = {k: v for k, v in sets.items() if k != "P"}

    for name in names:
        kind, _thr, _grid = SIGNAL_REGISTRY[name]
        col = name if kind == "boolean" else f"{name}_fire"
        if fires_override is not None:
            fire = fires_override[name].astype("boolean")
            value = fires_override[name]
        else:
            assert signals_out is not None
            fire = signals_out[col]
            value = signals_out[name]
        battery = evaluate_signal_battery(
            fire, value, eval_sets, close, placebo_shifts=placebo_shifts, placebo_seed=placebo_seed
        )
        sweep = sweep_signal(frame_asof, name, eval_sets, value)
        results["sweep_cells_per_signal"][name] = sweep["n_cells"]
        per_signal: dict[str, Any] = {"kind": kind, "battery": battery, "sweep": sweep}
        for set_name in eval_sets:
            if set_name.startswith("A+B"):
                per_signal["label_" + set_name.split(" ")[0]] = "pooled, descriptive only"
            else:
                per_signal["label_" + set_name] = label_from(battery, sweep, set_name)
        p_event = sets["P"]
        if len(p_event):
            per_signal["question_2026"] = latest_question(fire, close, p_event)
        results["signals"][name] = per_signal

    md = _render(results, sets)
    if out_json is not None:
        path = Path(out_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_to_builtin(results), indent=2, sort_keys=True))
    if out_md is not None:
        Path(out_md).write_text(md)
    print(md)
    print(f"\nPrimary family cells: {PRIMARY_CELLS} (19 signals x 2 horizons)")
    total_sweep = sum(results["sweep_cells_per_signal"].values())
    print(f"Sweep cells tried: {total_sweep} across {len(names)} signals (robustness only)")
    return results


def _to_builtin(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _to_builtin(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_builtin(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return None if np.isnan(v) else v
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, pd.Timestamp):
        return str(obj.date())
    if isinstance(obj, float) and np.isnan(obj):
        return None
    return obj


def _render(results: dict[str, Any], sets: Mapping[str, pd.DataFrame]) -> str:
    """Human tables via study.render_markdown + the ranked label table."""
    lines = [
        "# Q1: signals alone (machine-rendered tables)",
        "",
        f"frame sha256 `{results['frame_sha256']}`, commit `{results['commit']}`.",
        "",
        "## Labels per signal and set (plan section 6 rule)",
        "",
        "| signal | A | B | S |",
        "| :--- | :--- | :--- | :--- |",
    ]
    for name, per in results["signals"].items():
        lines.append(f"| {name} | {per.get('label_A', '')} | {per.get('label_B', '')} | {per.get('label_S', '')} |")
    lines += ["", "## Set A detail (counts k of n)", ""]
    for name, per in results["signals"].items():
        m = per["battery"].get("A", {}).get("metrics", {})
        pl = per["battery"].get("A", {}).get("placebo", {})
        if not m.get("n_events"):
            lines.append(f"- **{name}**: no evaluable events in A")
            continue
        lead = m.get("mean_lead_days")
        lift = m.get("lift")
        lines.append(
            f"- **{name}**: covered {int(m['n_covered'])}/{int(m['n_events'])} "
            + (f"(mean lead {lead:.1f} d), " if lead is not None else "(no usable lead), ")
            + f"episodes {int(m['n_episode_hits'])}/{int(m['n_episodes'])}, "
            + (f"lift {lift:.2f}, " if lift is not None else "lift n/a, ")
            + f"placebo p_lift {pl.get('p_lift')}"
        )
    lines += [
        "",
        "## Standing limits (plan section 7)",
        "",
        "Hindsight labels; confirm_date is optimistic (a +30% bounce occurred before the final "
        "low in 2018, 2022 and 2026); the 2026 low is provisional and can still move; MVRV-Z "
        "amplitude has decayed across cycles; macro series revised after release are excluded; "
        "Coin Metrics restates its latest days; BTC prices come from Yahoo; overlapping forward "
        "windows are not independent draws; no trading costs or sizing are modelled.",
        "",
        "Pre-registration here is only partly honest: thresholds were written by builders who "
        "know BTC's history; primary = defaults is discipline against cherry-picking from the "
        "sweep, not independence from the data.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:  # pragma: no cover - CLI entry, exercised via run()
    out_json = cache_dir("btc_bottoms/results") / "signals.json"
    out_md = cache_dir("btc_bottoms/results") / "signals-rendered.md"
    run(out_json=out_json, out_md=out_md)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
