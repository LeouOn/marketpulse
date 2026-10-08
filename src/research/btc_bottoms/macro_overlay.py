"""Q2 macro context for the BTC bottom study (wave 2b, g1).

Implements the six pre-registered macro conditions (plan section 4), the
descriptive comparator (4a) and the six declared combinations (4b) exactly as
the plan defines them. The plan is ``docs/btc-bottom-study/00-plan.md``; it
was fixed before any result existed and overrides intuition -- nothing here is
tuned to a result, and any deviation is reported in ``02-macro.md``.

Conditions (daily, causal, computed from ``asof(frame, 5)`` columns with
``net_liquidity`` recomputed after the fill -- use :func:`prepare_macro_frame`):

====  ====  ===============  ==================================================
id    col   name             definition (plan 4 table)
====  ====  ===============  ==================================================
M1    m1    real_yield_easing ``dfii10`` 21-day change < 0
M2    m2    dollar_easing     ``dxy_ice`` 21-day percent change < 0
M3a   m3a   vix_fade          ``vix`` <= 0.8 x trailing 21-day maximum
M3b   m3b   credit_easing     ``baa10y`` 21-day change < 0
M4    m4    liquidity_up      ``net_liquidity`` 63-day change > 0
M5    m5    valuation_low     ``mvrv_z`` < 0  (extras: < 0.5, < 1.0)
====  ====  ===============  ==================================================

Honesty rules specific to this module:

* Condition columns are floats ``1.0 / 0.0 / NaN``: an unknown input day is
  NaN, never False-by-default. Warm-up (diff/rolling windows), pre-2018
  on-chain-free days and the ``baa10y`` / ``hy_oas`` coverage limits propagate
  as NaN.
* All lookups are trailing (``diff`` / ``pct_change`` / ``rolling`` on windows
  ending at the row), so every condition is prefix-invariant by construction
  -- and tested for it.
* ``labels.py`` (g4) implements the section-6 conclusion rule. Until it lands
  on ``main`` this module calls a local stub that returns the marker string
  ``PENDING(labels.py not on main)`` instead of a label; the rule is NOT
  reimplemented here. The label *inputs* are reported either way.

Runner (module main): verifies the frozen-frame sha256 before touching
anything, prints the hash and the ``main`` commit, then runs the whole part
offline (no network, no refresh).
"""

from __future__ import annotations

import hashlib
import subprocess
import time
from pathlib import Path

import numpy as np
import pandas as pd

from src.research.btc_bottoms.frame import asof
from src.research.btc_bottoms.labels import label  # g4's frozen section-6 rule

__all__ = [
    "COMBINATIONS",
    "M_EXTRA_THRESHOLDS",
    "CONDITION_DEFS",
    "prepare_macro_frame",
    "macro_conditions",
    "descriptive",
    "funding_2026_view",
    "label_inputs",
    "run_all",
    "main",
]

#: Declared combinations, exactly these six (plan 4b): id -> (signal, condition).
COMBINATIONS: dict[str, tuple[str, str]] = {
    "C1": ("fgi_extreme_streak", "m3a"),
    "C2": ("dd_ath", "m1"),
    "C3": ("mayer_multiple", "m4"),
    "C4": ("washout_stabilise", "m3b"),
    "C5": ("dd_ath", "m5"),
    "C6": ("capitulation_vol", "m2"),
}

#: M5 robustness thresholds (plan: "robustness only: 0.5 and 1.0").
M_EXTRA_THRESHOLDS: tuple[float, ...] = (0.5, 1.0)

CONDITION_DEFS: dict[str, str] = {
    "m1": "real_yield_easing: dfii10 21-day change < 0",
    "m2": "dollar_easing: dxy_ice 21-day pct change < 0",
    "m3a": "vix_fade: vix <= 0.8 x trailing 21-day max",
    "m3b": "credit_easing: baa10y 21-day change < 0",
    "m4": "liquidity_up: net_liquidity 63-day change > 0",
    "m5": "valuation_low: mvrv_z < 0",
}

_EXPECTED_SHA = "7e1107e2e653e493af552efdc516e99dd020a0855e73d3b4d1d917dc8247087e"


def label_inputs(**kwargs) -> dict[str, object]:
    """Collect the section-6 label arguments for one evaluated series."""
    return dict(kwargs)


# ---------------------------------------------------------------------------
# Frame preparation
# ---------------------------------------------------------------------------


def prepare_macro_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """``asof(frame, 5)`` with ``net_liquidity`` recomputed from filled columns.

    The stored ``net_liquidity`` is NaN on Sundays/Mondays (raw RRP placement);
    after the as-of fill the inputs are present, so the plan recomputes it.
    """
    af = asof(frame, max_stale_days=5).copy()
    af["net_liquidity"] = af["walcl"] - af["wtregen"] - 1_000.0 * af["rrp_onday"]
    return af


def _btest(values: pd.Series, op: str, rhs: pd.Series) -> pd.Series:
    """NaN-propagating comparison -> float 1.0 / 0.0 / NaN."""
    lhs = values.astype("Float64")
    other = rhs.astype("Float64")
    if op == "<":
        out = lhs < other
    elif op == ">":
        out = lhs > other
    elif op == "<=":
        out = lhs <= other
    else:  # pragma: no cover - guarded by callers
        raise ValueError(f"unknown op {op!r}")
    return out.astype("float")


def macro_conditions(macro_frame: pd.DataFrame) -> pd.DataFrame:
    """The six plan conditions (plus M5 robustness extras) as float columns.

    Args:
        macro_frame: output of :func:`prepare_macro_frame` (or any frame with
            the as-of columns ``dfii10, dxy_ice, vix, baa10y, net_liquidity,
            mvrv_z``).

    Returns:
        DataFrame on the same index with columns ``m1, m2, m3a, m3b, m4, m5``
        and extras ``m5_lt_0.5`` / ``m5_lt_1.0``; values 1.0 (held), 0.0 (did
        not hold), NaN (input unknown -- warm-up or coverage gap).
    """
    zero = pd.Series(0.0, index=macro_frame.index)
    out = pd.DataFrame(index=macro_frame.index)
    out["m1"] = _btest(macro_frame["dfii10"].diff(21), "<", zero)
    out["m2"] = _btest(macro_frame["dxy_ice"].pct_change(21, fill_method=None), "<", zero)
    roll_max = macro_frame["vix"].rolling(21).max()
    out["m3a"] = _btest(macro_frame["vix"], "<=", 0.8 * roll_max)
    out["m3b"] = _btest(macro_frame["baa10y"].diff(21), "<", zero)
    out["m4"] = _btest(macro_frame["net_liquidity"].diff(63), ">", zero)
    out["m5"] = _btest(macro_frame["mvrv_z"], "<", zero)
    for thr in M_EXTRA_THRESHOLDS:
        out[f"m5_lt_{thr}"] = _btest(macro_frame["mvrv_z"], "<", thr * zero + float(thr))
    return out


def _and_boolean(a: pd.Series, b: pd.Series) -> pd.Series:
    """Nullable-boolean AND: NA stays NA, never False-by-accident."""
    return a.astype("boolean") & b.astype("boolean")


# ---------------------------------------------------------------------------
# Descriptive analysis (plan 4a)
# ---------------------------------------------------------------------------


def descriptive(
    macro_frame: pd.DataFrame,
    conds: pd.DataFrame,
    events: pd.DataFrame,
    window_days: int = 60,
    deep_dd: float = -0.40,
) -> dict[str, pd.DataFrame]:
    """Per-event condition shares vs deep-drawdown comparator days.

    * ``per_event``: for every event, per condition, ``k`` of ``n`` days in
      ``[bottom - window_days, bottom]`` on which the condition held
      (``n`` counts non-NaN days only).
    * ``comparator``: the same ``k`` of ``n`` on all *other* days inside deep
      drawdowns (``close / cummax(close) - 1 <= deep_dd``), with every event
      window (all horizons, including P) removed -- the 2026 episode must not
      sit inside its own baseline.
    * ``majority_A``: per condition, the number of *cycle bear_bottom* events
      whose window share exceeds 0.5, with the count of such events.
    """
    close = macro_frame["close"].astype(float)
    dd = close / close.cummax() - 1.0
    windows: list[pd.DatetimeIndex] = []
    for b in events["bottom_date"]:
        windows.append(pd.date_range(b - pd.Timedelta(days=window_days), b, freq="D"))
    in_any_window = pd.DatetimeIndex([]).append(windows) if windows else pd.DatetimeIndex([])

    rows = []
    for _, ev in events.iterrows():
        b = ev["bottom_date"]
        win = pd.date_range(b - pd.Timedelta(days=window_days), b, freq="D")
        for col in conds.columns:
            # windows can start before the frame (2015 low - 60d < 2014-09-17):
            # reindex keeps only in-frame days, missing stay NaN
            s = conds[col].reindex(win)
            n = int(s.notna().sum())
            k = int(s.sum())
            rows.append(
                {
                    "horizon": ev.get("horizon", ""),
                    "bottom_date": b,
                    "provisional": bool(ev.get("provisional", False)),
                    "condition": col,
                    "k": k,
                    "n": n,
                    "share": k / n if n else float("nan"),
                }
            )
    per_event = pd.DataFrame(rows)

    comp_mask = (dd <= deep_dd) & ~macro_frame.index.isin(in_any_window)
    comp_rows = []
    for col in conds.columns:
        s = conds.loc[comp_mask, col]
        n = int(s.notna().sum())
        k = int(s.sum())
        comp_rows.append({"condition": col, "k": k, "n": n, "share": k / n if n else float("nan")})
    comparator = pd.DataFrame(comp_rows)

    a_mask = (events["horizon"] == "cycle") if "horizon" in events.columns else None
    if a_mask is None:  # pragma: no cover - events contract always carries horizon
        a_events = events
    else:
        prov = events["provisional"].astype(bool) if "provisional" in events.columns else False
        sev = events["severity"].astype(str) if "severity" in events.columns else "bear_bottom"
        # plan: majority is over the A events (cycle bear_bottom, not provisional)
        a_events = events[a_mask & ~prov & (sev == "bear_bottom")]
    maj_rows = []
    for col in conds.columns:
        n_events = n_majority = 0
        for _, ev in a_events.iterrows():
            row = per_event[(per_event["bottom_date"] == ev["bottom_date"]) & (per_event["condition"] == col)]
            if row.empty or row.iloc[0]["n"] == 0:
                continue
            n_events += 1
            n_majority += int(row.iloc[0]["share"] > 0.5)
        maj_rows.append({"condition": col, "n_events_majority": n_majority, "n_events_evaluable": n_events})
    majority_A = pd.DataFrame(maj_rows)

    return {"per_event": per_event, "comparator": comparator, "majority_A": majority_A}


def funding_2026_view(macro_frame: pd.DataFrame, low: pd.Timestamp, last: pd.Timestamp) -> dict[str, float]:
    """Descriptive-only funding summary over the 2026 episode (plan 4a).

    Funding has ~1 year of history, so it is described, never tested.
    """
    s = macro_frame["funding_rate"].loc[low:last].dropna()
    return {
        "n_days": float(len(s)),
        "mean_daily": float(s.mean()) if len(s) else float("nan"),
        "median_daily": float(s.median()) if len(s) else float("nan"),
        "min_daily": float(s.min()) if len(s) else float("nan"),
        "max_daily": float(s.max()) if len(s) else float("nan"),
        "share_negative_days": float((s < 0).mean()) if len(s) else float("nan"),
    }


# ---------------------------------------------------------------------------
# Combination evaluation (plan 4b)
# ---------------------------------------------------------------------------

_METRIC_KEYS = ("n_events", "n_covered", "hit_rate", "n_episodes", "precision", "base_rate", "lift")


def _fire_of(sig: pd.DataFrame, name: str) -> pd.Series:
    """Fire series of a registry signal: ``<name>_fire`` for continuous
    signals (thresholded at the registry default), the boolean column itself
    for ``boolean``-kind signals (no ``_fire`` column exists for them)."""
    from src.research.btc_bottoms.signals import SIGNAL_REGISTRY

    kind = SIGNAL_REGISTRY[name][0]
    if kind == "continuous":
        return sig[f"{name}_fire"]
    return sig[name].astype("boolean")


def _evaluate_side(
    name: str,
    fire: pd.Series,
    asof_frame: pd.DataFrame,
    signal_name: str | None,
    sets: list[tuple[str, pd.DataFrame, str]],
    *,
    shifts: int,
    seed: int,
) -> list[dict[str, object]]:
    from src.research.btc_bottoms import study

    # diagnostics computed once on the whole frame (not per set)
    years = max((fire.index[-1] - fire.index[0]).days / 365.25, 1e-9)
    fire_day_share = float(fire.fillna(False).astype(bool).mean())

    rows: list[dict[str, object]] = []
    for set_name, ev, horizon in sets:
        if len(ev) == 0:
            continue
        conf = study.config_for(horizon)
        kw = {"pre_window": conf.pre_window, "cooldown": conf.cooldown, "forward_window": conf.forward_window}
        tab = study.evaluate(fire, ev, label=name, **kw)
        plac = study.placebo(fire, ev, shifts=shifts, seed=seed, **kw)
        loo = study.leave_one_out(fire, ev, **kw)
        loo_min = float(loo["hit_rate"].min()) if "hit_rate" in loo and len(loo) else float("nan")
        sweep_med = float("nan")
        if signal_name is not None:
            res = study.sweep(asof_frame, signal_name, ev, **kw)
            sweep_med = float(res.summary["lift"]["median"]) if res.summary.get("lift") else float("nan")
        rows.append(
            {
                "series": name,
                "set": set_name,
                "fire_day_share": fire_day_share,
                "episodes_per_year": float(tab.metrics["n_episodes"]) / years,
                **{k: tab.metrics[k] for k in _METRIC_KEYS},
                "placebo_p_lift": plac.p_lift,
                "loo_min_hit_rate": loo_min,
                "sweep_median_lift": sweep_med,
                "label": label(
                    n_evaluable=int(tab.metrics["n_events"]),
                    n_usable_leads=int(tab.metrics["n_covered"]),
                    lift=float(tab.metrics["lift"]),
                    n_episodes=int(tab.metrics["n_episodes"]),
                    placebo_p_lift=float(plac.p_lift),
                    sweep_median_lift=sweep_med,
                    loo_min_hit_rate=loo_min,
                ),
            }
        )
    return rows


def run_all(
    frame: pd.DataFrame,
    events_a: pd.DataFrame,
    events_b: pd.DataFrame,
    events_cycle_nonprovisional: pd.DataFrame,
    events_swing: pd.DataFrame,
    *,
    shifts: int = 2000,
    seed: int = 42,
) -> dict[str, object]:
    """Run the full Q2 part: conditions, descriptives, combos, signal-alone.

    Pure compute on the frozen frame. The signal side comes from
    ``signals.compute_signals(prepare_macro_frame(frame))`` per the plan;
    combinations are ANDed fire series evaluated with ``study.evaluate``
    (same engine ``evaluate_combination`` uses) for sets A, B and S, plus the
    pooled A+B table shown *next to* A and B as the plan permits. Metrics,
    placebo and leave-one-out are computed per series; the sweep exists only
    for signals (registry grid; combos have no pre-registered grid, so their
    ``sweep_median_lift`` is NaN and the label call receives NaN). The label
    is delegated to g4's ``labels.label`` (stub-marked until it lands).
    """
    from src.research.btc_bottoms.signals import compute_signals

    af = prepare_macro_frame(frame)
    conds = macro_conditions(af)
    sig = compute_signals(af)

    sets = [
        ("A", events_a, "cycle"),
        ("B", events_b, "cycle"),
        ("A+B pooled", events_cycle_nonprovisional, "cycle"),
        ("S", events_swing, "swing"),
    ]

    desc = descriptive(
        af,
        conds,
        pd.concat([events_cycle_nonprovisional, events_swing], ignore_index=True),
    )

    combo_rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for cid, (signal_name, cond_col) in COMBINATIONS.items():
        fire_sig = _fire_of(sig, signal_name)
        fire_cond = conds[cond_col].astype("boolean")
        combined = _and_boolean(fire_sig, fire_cond)
        combo_rows.extend(
            _evaluate_side(
                f"{cid} ({signal_name} & {cond_col})",
                combined,
                af,
                None,
                sets,
                shifts=shifts,
                seed=seed,
            )
        )
        if signal_name not in seen:
            seen.add(signal_name)
            combo_rows.extend(
                _evaluate_side(
                    f"{signal_name} (alone)",
                    _fire_of(sig, signal_name),
                    af,
                    signal_name,
                    sets,
                    shifts=shifts,
                    seed=seed,
                )
            )

    return {
        "macro_frame": af,
        "conditions": conds,
        "coverage": pd.DataFrame(
            {
                "first_valid": {c: conds[c].dropna().index.min() for c in conds.columns},
                "pct_non_null": {c: 100.0 * conds[c].notna().mean() for c in conds.columns},
            }
        ),
        "descriptive": desc,
        "combos": pd.DataFrame(combo_rows),
        "last_row": {c: conds[c].iloc[-1] for c in ("m1", "m2", "m3a", "m3b", "m4", "m5")},
    }


# ---------------------------------------------------------------------------
# Post-plan extras (decided after seeing results; CANNOT change any label)
# ---------------------------------------------------------------------------


def combination_robustness_sweep(
    asof_frame: pd.DataFrame,
    cond: pd.Series,
    signal_name: str,
    events: pd.DataFrame,
    horizon: str = "cycle",
) -> dict[str, object]:
    """Sweep the FIRST signal's registry grid with the macro gate held fixed.

    POST-PLAN EXTRA, decided after seeing results: the plan registered no
    grid for combinations, so their ``sweep_median_lift`` input is NaN and
    the frozen rule reads such combinations as "cannot evaluate". This
    sweep is reported as extra context ONLY -- it is not a label input and
    cannot rescue one.

    Returns the number of grid cells tried and median / min / max lift of
    the gated series across them (NaN lifts -- never-firing cells -- are
    excluded from the summary, which is stated in the doc).
    """
    import itertools

    from src.research.btc_bottoms import study
    from src.research.btc_bottoms.signals import SIGNAL_REGISTRY, compute_signals

    kind, _default, grid = SIGNAL_REGISTRY[signal_name]
    fire_col = signal_name if kind == "boolean" else f"{signal_name}_fire"
    keys = sorted(grid)
    cells = [dict(zip(keys, values, strict=True)) for values in itertools.product(*(grid[k] for k in keys))]

    conf = study.config_for(horizon)
    kw = {"pre_window": conf.pre_window, "cooldown": conf.cooldown, "forward_window": conf.forward_window}
    lifts: list[float] = []
    for cell in cells:
        sig = compute_signals(asof_frame, params={signal_name: cell})
        gated = _and_boolean(sig[fire_col], cond.astype("boolean"))
        m = study.evaluate(gated, events, **kw).metrics
        lift = float(m["lift"])
        if lift == lift:  # NaN (never firing) cells are excluded, counted below
            lifts.append(lift)
    n_nan = len(cells) - len(lifts)
    return {
        "n_cells": len(cells),
        "n_never_firing": n_nan,
        "median_lift": float(np.median(lifts)) if lifts else float("nan"),
        "min_lift": float(np.min(lifts)) if lifts else float("nan"),
        "max_lift": float(np.max(lifts)) if lifts else float("nan"),
    }


def episode_view(
    fire: pd.Series,
    close: pd.Series,
    peak: pd.Timestamp,
    low: pd.Timestamp,
    confirm: pd.Timestamp,
) -> dict[str, object]:
    """Set-P (2026) report-only view: fires inside the episode span.

    Mirrors g4's convention (``run_study.py``): "inside the episode" = fire
    days within ``[peak_date, confirm_date]``. P never enters any rate,
    lift, placebo or label.
    """
    span = fire.loc[peak:confirm].fillna(False).astype(bool)
    n_days = int(span.sum())
    if n_days == 0:
        return {
            "fire_days": 0,
            "first_fire": None,
            "days_before_low": None,
            "days_before_confirm": None,
            "close_at_first_fire": None,
            "low_close": float(close.loc[low]),
            "ret_first_fire_to_last": None,
        }
    first = span[span].index.min()
    last = close.index.max()
    return {
        "fire_days": n_days,
        "first_fire": first,
        "days_before_low": int((low - first).days),
        "days_before_confirm": int((confirm - first).days),
        "close_at_first_fire": float(close.loc[first]),
        "low_close": float(close.loc[low]),
        "ret_first_fire_to_last": float(close.loc[last] / close.loc[first] - 1.0),
    }


# ---------------------------------------------------------------------------
# Runner: frozen frame, offline, hash-checked
# ---------------------------------------------------------------------------


def _frame_path() -> Path:
    import os

    root = Path(os.environ.get("MARKETPULSE_DATA_DIR", "data/cache"))
    return root / "btc_bottoms" / "frame.parquet"


def main() -> int:
    from src.research.btc_bottoms.events import find_bottoms
    from src.research.btc_bottoms.frame import build_frame

    t0 = time.time()
    path = _frame_path()
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    print(f"frame sha256: {sha}")
    if sha != _EXPECTED_SHA:
        print(f"ABORT: frame hash mismatch (expected {_EXPECTED_SHA})")
        return 2
    main_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    print(f"main commit: {main_commit}")

    frame = build_frame(refresh=False)
    cyc = find_bottoms(frame, "cycle")
    swg = find_bottoms(frame, "swing")

    a = cyc[(cyc["severity"] == "bear_bottom") & (~cyc["provisional"])]
    b = cyc[(cyc["severity"] == "deep_correction") & (~cyc["provisional"])]
    p = cyc[cyc["provisional"]]
    ab = cyc[~cyc["provisional"]]
    print(f"events: A={len(a)} B={len(b)} P={len(p)} S={len(swg)}")

    out = run_all(frame, a, b, ab, swg)

    pd.set_option("display.width", 220)
    pd.set_option("display.max_rows", 400)
    print("\n== condition coverage ==")
    print(out["coverage"].to_string())
    print("\n== descriptive: per event (A, B, P marked) ==")
    print(out["descriptive"]["per_event"].to_string(index=False))
    print("\n== descriptive: comparator (other deep-drawdown days, dd <= -40%) ==")
    print(out["descriptive"]["comparator"].to_string(index=False))
    print("\n== descriptive: majority over A events ==")
    print(out["descriptive"]["majority_A"].to_string(index=False))

    low = p["bottom_date"].iloc[0] if len(p) else pd.NaT
    print("\n== funding, 2026 episode only (descriptive, not tested) ==")
    print(funding_2026_view(out["macro_frame"], low=low, last=frame.index.max()))

    print("\n== combos and first signals alone (macro family denominator: 6 conditions + 6 combinations) ==")
    print(out["combos"].to_string(index=False))

    p_ev = cyc[cyc["provisional"]]
    if len(p_ev):
        prow = p_ev.iloc[0]
        peak, low, confirm = prow["peak_date"], prow["bottom_date"], prow["confirm_date"]
        af = out["macro_frame"]
        conds = out["conditions"]
        from src.research.btc_bottoms.signals import compute_signals

        sig = compute_signals(af)
        print(
            f"\n== set P (2026 episode, report-only; peak {peak.date()} low {low.date()} confirm {confirm.date()}) =="
        )
        rows = []
        seen: set[str] = set()
        for cid, (signal_name, cond_col) in COMBINATIONS.items():
            rows.append(
                {
                    "series": f"{cid} ({signal_name} & {cond_col})",
                    **episode_view(
                        _and_boolean(_fire_of(sig, signal_name), conds[cond_col].astype("boolean")),
                        af["close"],
                        peak,
                        low,
                        confirm,
                    ),
                }
            )
            if signal_name not in seen:
                seen.add(signal_name)
                rows.append(
                    {
                        "series": f"{signal_name} (alone)",
                        **episode_view(_fire_of(sig, signal_name), af["close"], peak, low, confirm),
                    }
                )
        print(pd.DataFrame(rows).to_string(index=False))

    print(
        "\n== POST-PLAN EXTRA (decided after results; NOT a label and cannot change one): "
        "combo robustness -- first signal's registry grid swept, macro gate fixed, set A =="
    )
    a_ev = cyc[(cyc["severity"] == "bear_bottom") & (~cyc["provisional"])]
    extra_rows = []
    for cid, (signal_name, cond_col) in COMBINATIONS.items():
        extra_rows.append(
            {
                "combo": cid,
                "signal": signal_name,
                "gate": cond_col,
                **combination_robustness_sweep(out["macro_frame"], out["conditions"][cond_col], signal_name, a_ev),
            }
        )
    print(pd.DataFrame(extra_rows).to_string(index=False))

    print("\n== last-row condition values (for the case-file author) ==")
    print({k: (None if v != v else v) for k, v in out["last_row"].items()})
    print(f"\nruntime: {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
