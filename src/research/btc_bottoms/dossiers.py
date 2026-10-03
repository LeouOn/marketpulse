"""Q3 case files: per-event dossiers and the current reading (wave 2b, g3).

Plan section 5 deliverables, pre-registered in ``docs/btc-bottom-study/00-plan.md``:

* :func:`dossier` -- for one cycle event, a snapshot table across eight stages
  (``peak``, ``bottom-90/60/30/7``, ``bottom``, ``confirm``, ``last``) with
  close, drawdown from ATH, all 19 registry signal readings and their fire
  flags (``compute_signals`` on ``asof(frame, 5)`` at registry defaults), the
  six macro conditions M1-M5 and the valuation/liquidity context
  (``mvrv_z``, ``fgi_value``, real-yield level, ``baa10y``, ``net_liquidity``).
* :func:`false_confirm_timeline` -- the dated trap lines behind
  ``events.false_confirms``: every +30% bounce off a running low that a later
  lower low broke, with the prices, so a reader can see what the owner saw.
* :func:`current_reading` -- which signals and macro conditions are on at the
  last frame row and for how many days. Descriptive only; explicitly not a
  forecast.
* :func:`first_fire_after` -- per signal, the first fire date at/after a date
  (the 2026 question as a case file).

Design decisions
----------------
* **Stage snapping is causal.** ``bottom-N`` is the last frame row on or
  before ``bottom_date - N days``; a stage that predates the data is an
  all-NaN row (the 2015 event's ``bottom-90`` does not exist).
* **Macro conditions are recomputed here** from ``asof`` columns with the
  plan's exact definitions (section 4), including ``net_liquidity`` rebuilt
  after ``asof`` from the filled components. When g1's ``macro_overlay``
  lands, a pinned test asserts both implementations agree.
* **NaN is preserved.** Conditions are nullable booleans; a missing input is
  NA (``n/a``), never silently ``False``. Rendering says why (series start).
* This module never mutates its inputs and never touches the network; the CLI
  (:func:`main`) verifies the frozen frame's sha256 before doing anything.

Standing limits (plan section 7, repeated in every output): hindsight labels;
``confirm_date`` is optimistic (a +30% bounce occurred before the final low in
2018, 2022 and 2026); the 2026 low is provisional and can still move; MVRV-Z
amplitude has decayed across cycles; revised macro series are excluded; Coin
Metrics restates its latest days (last 5 rows of on-chain columns are
provisional); BTC prices come from Yahoo; overlapping windows are not
independent draws; no trading costs or sizing are modelled.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from src.research.btc_bottoms.events import find_bottoms
from src.research.btc_bottoms.frame import asof, build_frame
from src.research.btc_bottoms.signals import SIGNAL_REGISTRY, compute_signals

__all__ = [
    "SNAPSHOT_STAGES",
    "SIGNAL_NAMES",
    "MACRO_COLUMNS",
    "EXPECTED_FRAME_SHA256",
    "macro_conditions",
    "false_confirm_timeline",
    "dossier",
    "current_reading",
    "first_fire_after",
    "main",
]

#: Frozen frame this study reads (plan section 1). Verified before every run.
EXPECTED_FRAME_SHA256 = "7e1107e2e653e493af552efdc516e99dd020a0855e73d3b4d1d917dc8247087e"

#: The eight snapshot stages of a dossier, in presentation order.
SNAPSHOT_STAGES = ["peak", "bottom-90", "bottom-60", "bottom-30", "bottom-7", "bottom", "confirm", "last"]

#: The 19 registry signals, registry order.
SIGNAL_NAMES: list[str] = list(SIGNAL_REGISTRY)

#: Fire-flag column per signal: boolean signals are their own fire flag.
FIRE_COLUMNS: dict[str, str] = {
    name: name if kind == "boolean" else f"{name}_fire" for name, (kind, _thr, _grid) in SIGNAL_REGISTRY.items()
}

#: The six macro conditions (plan section 4). M3 is split into M3a/M3b.
MACRO_COLUMNS: list[str] = [
    "M1_real_yield_easing",
    "M2_dollar_easing",
    "M3a_vix_fade",
    "M3b_credit_easing",
    "M4_liquidity_up",
    "M5_valuation_low",
]

#: Rebound that marks a confirmation (matches events defaults; see the plan).
CONFIRM_REBOUND = 0.30


# ---------------------------------------------------------------------------
# Macro conditions (plan section 4, exact definitions)
# ---------------------------------------------------------------------------


def _net_liquidity(a: pd.DataFrame) -> pd.Series:
    """Net liquidity ($mn) rebuilt from asof-filled components, per the plan."""
    return a["walcl"] - a["wtregen"] - 1_000.0 * a["rrp_onday"]


def _flag(values: pd.Series, condition: pd.Series) -> pd.Series:
    """Nullable boolean: NA where any input is NA, else the comparison."""
    return condition.astype("boolean").where(values.notna())


def macro_conditions(a: pd.DataFrame) -> pd.DataFrame:
    """M1-M5 as nullable booleans on the asof frame (plan section 4).

    * M1 real_yield_easing: ``dfii10`` 21-day change < 0
    * M2 dollar_easing: ``dxy_ice`` 21-day percent change < 0
    * M3a vix_fade: ``vix`` <= 0.8 x its trailing 21-day maximum
    * M3b credit_easing: ``baa10y`` 21-day change < 0
    * M4 liquidity_up: ``net_liquidity`` (rebuilt above) 63-day change > 0
    * M5 valuation_low: ``mvrv_z`` < 0

    NaN inputs stay NA; the 21-day trailing window for M3a is causal
    (``min_periods=1`` -- defined from the first observation).
    """
    nl = _net_liquidity(a)
    dfii = a["dfii10"]
    dxy = a["dxy_ice"]
    vix = a["vix"]
    baa = a["baa10y"]
    mvrv_z = a["mvrv_z"]
    m = pd.DataFrame(index=a.index)
    m["M1_real_yield_easing"] = _flag(dfii, dfii.diff(21) < 0)
    dxy_chg = dxy.pct_change(21, fill_method=None)
    m["M2_dollar_easing"] = _flag(dxy_chg, dxy_chg < 0)
    vix_bound = 0.8 * vix.rolling(21, min_periods=1).max()
    m["M3a_vix_fade"] = _flag(vix, (vix <= vix_bound) & vix_bound.notna())
    m["M3b_credit_easing"] = _flag(baa, baa.diff(21) < 0)
    nl_chg = nl.diff(63)
    m["M4_liquidity_up"] = _flag(nl_chg, nl_chg > 0)
    m["M5_valuation_low"] = _flag(mvrv_z, mvrv_z < 0)
    return m


# ---------------------------------------------------------------------------
# False-confirmation timeline
# ---------------------------------------------------------------------------


def false_confirm_timeline(
    frame: pd.DataFrame, event: pd.Series, rebound: float = CONFIRM_REBOUND, cycle_dd: float = 0.45
) -> pd.DataFrame:
    """Dated false confirmations inside one event's episode.

    Mirrors the counting logic of ``events.false_confirms`` (pinned by tests):
    walk the episode from its OPEN (the first close at or below
    ``peak_price * (1 - cycle_dd)``, the default 0.45 the plan's build inputs
    use) to ``bottom_date``; whenever the close rebounds ``>= rebound`` above
    the running low and a later row of the same episode makes a lower low,
    emit one row. Bounces before the episode opens are not this event's false
    confirms (the drawdown had not reached cycle scale) and are excluded,
    exactly like the events state machine. Columns: ``low_date, low_close,
    confirm_date, confirm_close, broken_date, broken_close``. The final
    confirmation (off the final low) is never a false confirm.
    """
    close = frame["close"]
    trigger = float(event["peak_price"]) * (1.0 - cycle_dd)
    after_peak = close.loc[close.index >= event["peak_date"]]
    opened = after_peak[after_peak <= trigger]
    columns = ["low_date", "low_close", "confirm_date", "confirm_close", "broken_date", "broken_close"]
    if opened.empty:
        return pd.DataFrame(columns=columns)
    span = close.loc[(close.index >= opened.index[0]) & (close.index <= event["bottom_date"])]
    rows: list[dict] = []
    min_price = np.inf
    min_date = None
    confirmed: tuple[pd.Timestamp, float] | None = None  # (confirm_date, confirm_close)
    for date, value in span.items():
        if value < min_price:
            if confirmed is not None:
                rows.append(
                    {
                        "low_date": min_date,
                        "low_close": float(min_price),
                        "confirm_date": confirmed[0],
                        "confirm_close": confirmed[1],
                        "broken_date": date,
                        "broken_close": float(value),
                    }
                )
                confirmed = None
            min_price = float(value)
            min_date = date
        elif confirmed is None and value >= min_price * (1.0 + rebound):
            confirmed = (date, float(value))
    return pd.DataFrame(
        rows, columns=["low_date", "low_close", "confirm_date", "confirm_close", "broken_date", "broken_close"]
    )


# ---------------------------------------------------------------------------
# Dossier
# ---------------------------------------------------------------------------


def _stage_position(idx: pd.DatetimeIndex, target: pd.Timestamp | None) -> int | None:
    """Position of the last row on or before ``target`` (causal snap)."""
    if target is None or pd.isna(target):
        return None
    pos = idx.searchsorted(target, side="right") - 1
    return int(pos) if pos >= 0 else None


def dossier(frame: pd.DataFrame, events: pd.DataFrame, event_index: int) -> pd.DataFrame:
    """Snapshot table (plan section 5) for ``events.iloc[event_index]``.

    ``frame`` must be the asof frame (``asof(build_frame(refresh=False), 5)``).
    Rows are the eight :data:`SNAPSHOT_STAGES`; columns are the date, close,
    the 19 signal readings (``dd_ath`` among them is the drawdown from ATH),
    their fire flags (boolean signals repeat their reading), the six macro
    conditions, and the context columns ``mvrv_z, fgi_value, real_yield,
    baa10y, net_liquidity``.
    """
    event = events.iloc[event_index]
    idx = frame.index
    targets = {
        "peak": event["peak_date"],
        "bottom-90": event["bottom_date"] - pd.Timedelta(days=90),
        "bottom-60": event["bottom_date"] - pd.Timedelta(days=60),
        "bottom-30": event["bottom_date"] - pd.Timedelta(days=30),
        "bottom-7": event["bottom_date"] - pd.Timedelta(days=7),
        "bottom": event["bottom_date"],
        "confirm": event["confirm_date"],
        "last": idx[-1],
    }
    positions = {stage: _stage_position(idx, target) for stage, target in targets.items()}

    signals = compute_signals(frame)
    macro = macro_conditions(frame)
    nl = _net_liquidity(frame)

    columns = (
        ["date", "close"]
        + SIGNAL_NAMES
        + [f"{name}_fire" for name in SIGNAL_NAMES]
        + MACRO_COLUMNS
        + ["mvrv_z", "fgi_value", "real_yield", "baa10y", "net_liquidity"]
    )
    out = pd.DataFrame(index=pd.Index(SNAPSHOT_STAGES, name="stage"), columns=columns, dtype=object)
    for stage, pos in positions.items():
        if pos is None:
            out.loc[stage, "date"] = pd.NaT
            continue
        ts = idx[pos]
        out.loc[stage, "date"] = ts
        out.loc[stage, "close"] = float(frame["close"].iloc[pos])
        for name in SIGNAL_NAMES:
            out.loc[stage, name] = signals[name].iloc[pos]
            out.loc[stage, f"{name}_fire"] = signals[FIRE_COLUMNS[name]].iloc[pos]
        for cond in MACRO_COLUMNS:
            out.loc[stage, cond] = macro[cond].iloc[pos]
        out.loc[stage, "mvrv_z"] = frame["mvrv_z"].iloc[pos]
        out.loc[stage, "fgi_value"] = frame["fgi_value"].iloc[pos]
        out.loc[stage, "real_yield"] = frame["dfii10"].iloc[pos]
        out.loc[stage, "baa10y"] = frame["baa10y"].iloc[pos]
        out.loc[stage, "net_liquidity"] = nl.iloc[pos]
    return out


# ---------------------------------------------------------------------------
# Current reading and first-fire-after
# ---------------------------------------------------------------------------


def _days_on(series: pd.Series) -> int:
    """Length of the trailing run of True (NA or False stops it)."""
    days = 0
    for value in reversed(series.tolist()):
        if value is pd.NA or value is None or (isinstance(value, float) and np.isnan(value)) or pd.isna(value):
            break
        if bool(value):
            days += 1
        else:
            break
    return days


def current_reading(frame: pd.DataFrame) -> dict:
    """Descriptive reading at the last frame row: what is on, and since when.

    Returns ``{"as_of", "signals", "macro", "counts"}`` where ``signals`` is
    indexed by the 19 registry names (``on`` nullable boolean, ``days_on``
    trailing days on, ``reading`` = last value) and ``macro`` by the six
    conditions. Counts never treat NA as off-*and*-unknown: ``signals_on``
    counts True only, and the totals are printed next to them. This is a
    description of the present, not a forecast.
    """
    signals = compute_signals(frame)
    macro = macro_conditions(frame)
    last = frame.index[-1]
    sig_rows = []
    for name in SIGNAL_NAMES:
        fire = signals[FIRE_COLUMNS[name]]
        sig_rows.append(
            {
                "on": fire.iloc[-1] if not pd.isna(fire.iloc[-1]) else pd.NA,
                "days_on": _days_on(fire),
                "reading": signals[name].iloc[-1],
            }
        )
    macro_rows = []
    for cond in MACRO_COLUMNS:
        macro_rows.append({"on": macro[cond].iloc[-1], "days_on": _days_on(macro[cond]), "value": macro[cond].iloc[-1]})
    sig_df = pd.DataFrame(sig_rows, index=pd.Index(SIGNAL_NAMES, name="signal"))
    macro_df = pd.DataFrame(macro_rows, index=pd.Index(MACRO_COLUMNS, name="condition"))
    return {
        "as_of": last,
        "signals": sig_df,
        "macro": macro_df,
        "counts": {
            "signals_on": int(sig_df["on"].fillna(False).sum()),
            "signals_total": len(SIGNAL_NAMES),
            "macro_on": int(macro_df["on"].fillna(False).sum()),
            "macro_total": len(MACRO_COLUMNS),
        },
    }


def first_fire_after(frame: pd.DataFrame, date: pd.Timestamp) -> pd.Series:
    """First date at/after ``date`` on which each signal fires (NaT if never)."""
    signals = compute_signals(frame)
    out: dict[str, pd.Timestamp | pd.NaT] = {}
    for name in SIGNAL_NAMES:
        fire = signals[FIRE_COLUMNS[name]]
        tail = fire.loc[fire.index >= date]
        fired = tail[tail.astype("boolean") == True]  # noqa: E712 -- nullable comparison
        out[name] = fired.index[0] if len(fired) else pd.NaT
    return pd.Series(out, name="first_fire")


# ---------------------------------------------------------------------------
# CLI: verified-frame table generation for 03-case-files.md
# ---------------------------------------------------------------------------


def _frame_path() -> Path:
    import os

    root = os.environ.get("MARKETPULSE_DATA_DIR", "data/cache")
    return Path(root) / "btc_bottoms" / "frame.parquet"


def _verify_frame() -> str:
    path = _frame_path()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != EXPECTED_FRAME_SHA256:
        raise SystemExit(f"frame sha256 mismatch: {digest} != {EXPECTED_FRAME_SHA256} (refusing to run)")
    return digest


def _git_head() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:  # pragma: no cover - offline fallback
        return "unknown"


def _fmt(value, digits: int = 2) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)) or value is pd.NA or pd.isna(value):
        return "n/a"
    if isinstance(value, (bool, np.bool_)):
        return "yes" if bool(value) else "no"
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, float | np.floating):
        return f"{float(value):.{digits}f}"
    return str(value)


def _first_valid_map(columns: dict[str, pd.Series]) -> dict[str, pd.Timestamp]:
    """First non-NaN date per series, for 'n/a (starts D)' reasons."""
    out: dict[str, pd.Timestamp] = {}
    for name, series in columns.items():
        valid = series.dropna()
        out[name] = valid.index[0] if len(valid) else pd.NaT
    return out


def _fmt_na(value, name: str, firsts: dict[str, pd.Timestamp], date: pd.Timestamp, digits: int = 2) -> str:
    text = _fmt(value, digits)
    if text != "n/a":
        return text
    start = firsts.get(name)
    if start is not None and not pd.isna(start) and date < start:
        return f"n/a (starts {start.date()})"
    return "n/a (gap)"


def _render_tables(frame: pd.DataFrame, events: pd.DataFrame) -> str:
    """Markdown tables for every cycle event plus the current reading."""
    lines: list[str] = []
    signals = compute_signals(frame)
    firsts = _first_valid_map({name: signals[name] for name in SIGNAL_NAMES})
    for i, event in events.iterrows():
        d = dossier(frame, events, i)
        lines.append(
            f"### Event {i} ({event['severity']}): bottom {event['bottom_date'].date()} "
            f"({event['drawdown']:+.1%} from peak {event['peak_date'].date()})\n"
        )
        context_cols = ["close", "dd_ath", "mvrv_z", "fgi_value", "real_yield", "baa10y", "net_liquidity"]
        header = "| stage | date | " + " | ".join(context_cols) + " |"
        lines.append(header)
        lines.append("|" + "---|" * (len(context_cols) + 2))
        for stage in SNAPSHOT_STAGES:
            row = d.loc[stage]
            cells = []
            for col in context_cols:
                v = row[col]
                text = _fmt(v)
                if col == "net_liquidity" and text != "n/a":
                    text = f"{float(v) / 1e6:.2f}tn"
                if col == "dd_ath" and text != "n/a":
                    text = f"{float(v):+.1%}"
                cells.append(text)
            lines.append(f"| {stage} | {_fmt(row['date'])} | " + " | ".join(cells) + " |")
        lines.append("")
        lines.append("| signal | " + " | ".join(SNAPSHOT_STAGES) + " |")
        lines.append("|" + "---|" * (len(SNAPSHOT_STAGES) + 1))
        for name in SIGNAL_NAMES:
            cells = []
            for stage in SNAPSHOT_STAGES:
                reading = d.loc[stage, name]
                fire = d.loc[stage, f"{name}_fire"]
                fired = fire is True or (isinstance(fire, (bool, np.bool_)) and bool(fire))
                text = _fmt_na(reading, name, firsts, d.loc[stage, "date"])
                if fired:
                    text = f"**{text}** FIRE"
                cells.append(text)
            lines.append(f"| {name} | " + " | ".join(cells) + " |")
        lines.append("")
        lines.append("| condition | " + " | ".join(SNAPSHOT_STAGES) + " |")
        lines.append("|" + "---|" * (len(SNAPSHOT_STAGES) + 1))
        for cond in MACRO_COLUMNS:
            cells = [
                "yes"
                if d.loc[stage, cond] is True
                or (isinstance(d.loc[stage, cond], (bool, np.bool_)) and bool(d.loc[stage, cond]))
                else ("n/a" if pd.isna(d.loc[stage, cond]) else "no")
                for stage in SNAPSHOT_STAGES
            ]
            lines.append(f"| {cond} | " + " | ".join(cells) + " |")
        lines.append("")
        tl = false_confirm_timeline(frame, event)
        lines.append(f"False confirmations ({len(tl)}, events.false_confirms={int(event['false_confirms'])}):\n")
        if len(tl):
            lines.append("| low_date | low_close | confirm_date | confirm_close | broken_date | broken_close |")
            lines.append("|---|---|---|---|---|---|")
            for _, r in tl.iterrows():
                lines.append(
                    f"| {r['low_date'].date()} | {r['low_close']:,.0f} | {r['confirm_date'].date()} | "
                    f"{r['confirm_close']:,.0f} | {r['broken_date'].date()} | {r['broken_close']:,.0f} |"
                )
        else:
            lines.append("(none)")
        lines.append("")
        if bool(event["provisional"]):
            ff = first_fire_after(frame, event["bottom_date"])
            bottom_fires = {
                name
                for name in SIGNAL_NAMES
                if d.loc["bottom", f"{name}_fire"] is True
                or (
                    isinstance(d.loc["bottom", f"{name}_fire"], (bool, np.bool_))
                    and bool(d.loc["bottom", f"{name}_fire"])
                )
            }
            lines.append("Live view for the provisional episode (the 2026 question, as a case file):\n")
            lines.append(
                "| signal | firing at bottom | first fire at/after bottom | close that day | firing at last row |"
            )
            lines.append("|---|---|---|---|---|")
            last_fires = {
                name
                for name in SIGNAL_NAMES
                if signals[FIRE_COLUMNS[name]].iloc[-1] is True
                or (
                    isinstance(signals[FIRE_COLUMNS[name]].iloc[-1], (bool, np.bool_))
                    and bool(signals[FIRE_COLUMNS[name]].iloc[-1])
                )
            }
            for name in SIGNAL_NAMES:
                at_bottom = "yes" if name in bottom_fires else "no"
                when = ff.loc[name]
                if pd.isna(when):
                    when_text, close_text = "never", "-"
                else:
                    when_text = when.date().isoformat()
                    close_text = f"{float(frame['close'].loc[when]):,.0f}"
                lines.append(
                    f"| {name} | {at_bottom} | {when_text} | {close_text} | {'yes' if name in last_fires else 'no'} |"
                )
            lines.append("")
    reading = current_reading(frame)
    lines.append(f"### Current reading as of {reading['as_of'].date()} (descriptive, not a forecast)\n")
    c = reading["counts"]
    lines.append(
        f"Signals on: **{c['signals_on']} of {c['signals_total']}**; macro conditions on: "
        f"**{c['macro_on']} of {c['macro_total']}**.\n"
    )
    lines.append("| what | on | days_on | value |")
    lines.append("|---|---|---|---|")
    for name, row in reading["signals"].iterrows():
        lines.append(f"| signal {name} | {_fmt(row['on'])} | {row['days_on']} | {_fmt(row['reading'])} |")
    for cond, row in reading["macro"].iterrows():
        lines.append(f"| {cond} | {_fmt(row['on'])} | {row['days_on']} | {_fmt(row['value'])} |")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Generate the case-file tables from the frozen frame (verified first)."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None, help="write markdown tables here (default: stdout)")
    args = parser.parse_args(argv)

    digest = _verify_frame()
    frame = asof(build_frame(refresh=False), 5)
    events = find_bottoms(frame, "cycle")
    text = _render_tables(frame, events)
    header = (
        f"<!-- generated by python -m src.research.btc_bottoms.dossiers -->\n"
        f"<!-- frame sha256 {digest} | main {_git_head()} -->\n\n"
    )
    if args.out:
        args.out.write_text(header + text + "\n")
        print(f"wrote {args.out} (frame sha256 {digest})", file=sys.stderr)
    else:
        print(header + text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
