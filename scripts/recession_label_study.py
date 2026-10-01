"""Measure the RECESSION regime label against NBER recession dates.

Read-only. Prints the Part 1 tables and writes nothing under tracked paths.
The factor frame is cached under /tmp/marketpulse-t12-factor-cache so a rerun
does not rewrite data/cache or the tracked data/macro seeds.

The headline window is 1990-01-01 through today, scored only on days the NBER
series itself has a value. Factors are loaded from that start minus
RulesBasedClassifier.LOOKBACK_DAYS, then the tape is sliced, matching the
regime endpoint and the CLI.

This is agreement with the final NBER dates on current-vintage unemployment,
not a real-time hit rate. Sahm is a concurrent labor-market rule, so a lag
at the start and a tail after the trough are expected properties of the
indicator, not automatically bugs.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from fredapi import Fred
from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.research.data._fred_key import get_fred_api_key  # noqa: E402
from src.research.macro.factors import MacroFactorProvider  # noqa: E402
from src.research.macro.regimes import (  # noqa: E402
    _SL_REC_ISM,
    _TH_REC_ISM,
    RulesBasedClassifier,
    generate_regime_tape,
)

# Headline window from the task. Context starts once every trailing window
# the classifier uses is full, so a spell that begins just before 1990 is
# not cut in half and is not scored on a truncated z-score.
EVAL_START = date(1990, 1, 1)
CONTEXT_START = date(1989, 6, 1)
CACHE_DIR = Path("/tmp/marketpulse-t12-factor-cache")
SERIES_CANDIDATES = ("USREC", "USRECD", "USRECM", "SAHMCURRENT", "SAHMREALTIME")


def _section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def _pct(n: float, d: float) -> str:
    if d == 0:
        return "n/a"
    return f"{100.0 * n / d:6.2f}%"


def _f(x: float) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "  n/a"
    return f"{x:7.3f}"


def _d(ts: pd.Timestamp | None) -> str:
    if ts is None or pd.isna(ts):
        return "-"
    return pd.Timestamp(ts).date().isoformat()


def boolean_runs(mask: pd.Series) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Inclusive (start, end) of each contiguous True run. Index must be sorted."""
    m = mask.astype(bool)
    if m.empty or not bool(m.any()):
        return []
    group_id = m.ne(m.shift(fill_value=False)).cumsum()
    runs: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    for _, grp in m.groupby(group_id, sort=True):
        if bool(grp.iloc[0]):
            runs.append((pd.Timestamp(grp.index[0]), pd.Timestamp(grp.index[-1])))
    return runs


def binary_counts(pred: pd.Series, truth: pd.Series) -> dict[str, float]:
    p = pred.astype(bool)
    t = truth.astype(bool)
    tp = int((p & t).sum())
    fp = int((p & ~t).sum())
    fn = int((~p & t).sum())
    tn = int((~p & ~t).sum())
    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    recall = tp / (tp + fn) if (tp + fn) else float("nan")
    if np.isnan(precision) or np.isnan(recall) or (precision + recall) == 0:
        f1 = float("nan")
    else:
        f1 = 2 * precision * recall / (precision + recall)
    return {
        "n": float(len(p)),
        "share": float(p.mean()) if len(p) else float("nan"),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": float(tp),
        "fp": float(fp),
        "fn": float(fn),
        "tn": float(tn),
    }


def _month_start(series: pd.Series) -> pd.Series:
    out = series.copy()
    out.index = pd.to_datetime(out.index).to_period("M").to_timestamp()
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out


def fetch_series_info(client: Fred) -> dict[str, pd.Series]:
    """Confirm which candidate FRED ids exist. Prints titles, never the key."""
    found: dict[str, pd.Series] = {}
    _section("FRED series check")
    for sid in SERIES_CANDIDATES:
        try:
            info = client.get_series_info(sid)
        except Exception as exc:
            print(f"  {sid:16s} UNAVAILABLE  {type(exc).__name__}")
            continue
        found[sid] = info
        title = str(info.get("title", ""))
        freq = str(info.get("frequency", ""))
        start = str(info.get("observation_start", ""))
        end = str(info.get("observation_end", ""))
        units = str(info.get("units", ""))
        print(f"  {sid:16s} {freq:10s} {start} .. {end}  {units}")
        print(f"  {'':16s} {title}")
    return found


def fetch_values(client: Fred, sid: str, start: date, end: date) -> pd.Series:
    raw = client.get_series(sid, observation_start=start.isoformat(), observation_end=end.isoformat())
    s = pd.to_numeric(raw, errors="coerce")
    s.index = pd.to_datetime(s.index).tz_localize(None)
    s = s[~s.index.duplicated(keep="last")].sort_index().dropna()
    s.name = sid
    return s


def ism_fallback(factor_df: pd.DataFrame) -> pd.Series:
    """The classifier's own ISM-proxy sigmoid, before the Sahm override."""
    clf = RulesBasedClassifier()
    z = clf._compute_zscores(factor_df)
    ism_z = clf._safe_z(z, "ism_pmi", factor_df.index)
    soft = clf._sigmoid_fillna(-ism_z, _TH_REC_ISM, _SL_REC_ISM)
    soft.name = "ism_fallback"
    return soft


def load_tape(eval_end: date) -> tuple[pd.DataFrame, pd.DataFrame, date]:
    lookback = RulesBasedClassifier.LOOKBACK_DAYS
    fetch_start = EVAL_START - timedelta(days=lookback)
    _section("Factor frame and tape")
    print(f"  LOOKBACK_DAYS     {lookback}")
    print(f"  fetch             {fetch_start.isoformat()} .. {eval_end.isoformat()}")
    print(f"  headline          {EVAL_START.isoformat()} .. {eval_end.isoformat()}")
    print(f"  cache             {CACHE_DIR} (untracked temp dir)")
    provider = MacroFactorProvider(cache_dir=CACHE_DIR)
    factor_df = provider.load_factors(fetch_start, eval_end)
    tape = generate_regime_tape(factor_df, include_scores=True)
    print(f"  factor rows       {len(factor_df)}  {factor_df.index.min().date()} .. {factor_df.index.max().date()}")
    print(f"  tape columns      {list(tape.columns)}")
    return factor_df, tape, fetch_start


def align_nber(tape_index: pd.DatetimeIndex, daily: pd.Series | None, monthly: pd.Series) -> pd.Series:
    """Put NBER on the tape's calendar. Prefer the daily series when present."""
    if daily is not None and not daily.empty:
        aligned = daily.reindex(tape_index)
        aligned.name = "nber"
        return aligned
    # Monthly dummy: the observation dated the 1st applies until the next print.
    aligned = monthly.reindex(tape_index, method="ffill")
    # Do not invent a value before the first print, and do not carry the last
    # print into the following unpublished month.
    first = monthly.index.min()
    last_month_end = monthly.index.max() + pd.offsets.MonthEnd(0)
    aligned = aligned.where((tape_index >= first) & (tape_index <= last_month_end))
    aligned.name = "nber"
    return aligned


def sahm_value_from_unrate(monthly_unrate: pd.Series) -> pd.Series:
    """Same formula as MacroFactorProvider._compute_sahm (published definition), kept as a level."""
    ma3 = monthly_unrate.rolling(3, min_periods=3).mean()
    gap = (ma3 - ma3.shift(1).rolling(12, min_periods=12).min()).clip(lower=0.0).round(2)
    gap.name = "sahm_value"
    return gap


def print_agreement(rows: list[tuple[str, dict[str, float]]]) -> None:
    header = (
        f"  {'predictor':42s} {'share':>8s} {'prec':>7s} {'recall':>7s} {'f1':>7s} {'tp':>6s} {'fp':>6s} {'fn':>6s}"
    )
    print(header)
    for name, m in rows:
        print(
            f"  {name:42s} {_pct(m['share'], 1):>8s} {_f(m['precision']):>7s} {_f(m['recall']):>7s} "
            f"{_f(m['f1']):>7s} {int(m['tp']):6d} {int(m['fp']):6d} {int(m['fn']):6d}"
        )


def episode_table(
    nber_runs: list[tuple[pd.Timestamp, pd.Timestamp]],
    label_runs: list[tuple[pd.Timestamp, pd.Timestamp]],
    scored: pd.DataFrame,
    sample_end: pd.Timestamp,
) -> None:
    print(
        f"  {'nber':23s} {'days':>5s} {'label on':>8s} {'onset':>8s} {'overhang':>10s} "
        f"{'during':>7s} {'sahm share of on-days':>22s}"
    )
    for n_start, n_end in nber_runs:
        window = scored.loc[n_start:n_end]
        n_days = len(window)
        overlapping = [r for r in label_runs if r[0] <= n_end and r[1] >= n_start]
        on_days = int(window["label"].sum()) if n_days else 0
        if not overlapping:
            print(
                f"  {_d(n_start)}..{_d(n_end)} {n_days:5d} {'no':>8s} {'never':>8s} {0:10d} "
                f"{_pct(on_days, n_days):>7s} {'-':>22s}"
            )
            continue
        spell_start, spell_end = min(overlapping, key=lambda r: r[0])
        covering_end = [r for r in overlapping if r[0] <= n_end <= r[1]]
        if covering_end:
            hold = covering_end[0]
            overhang = (hold[1] - n_end).days
            censored = hold[1] >= sample_end and bool(scored["label"].iloc[-1])
            overhang_s = f"{overhang}d*" if censored else f"{overhang}d"
        else:
            overhang_s = "0d"
        onset = (spell_start - n_start).days
        onset_s = f"{onset:+d}d"
        if spell_start <= pd.Timestamp(CONTEXT_START):
            onset_s = "censored"
        on_slice = window.loc[window["label"]]
        sahm_share = float(on_slice["sahm"].mean()) if len(on_slice) else float("nan")
        print(
            f"  {_d(n_start)}..{_d(n_end)} {n_days:5d} {_d(spell_start):>10s} {onset_s:>8s} {overhang_s:>10s} "
            f"{_pct(on_days, n_days):>7s} {sahm_share:22.2f}"
        )
    print("  onset: label-spell start minus NBER start. Negative means the label led.")
    print("  overhang: days the spell that covers the NBER end continues past it. * = still on at the sample end.")


def false_positive_table(scored: pd.DataFrame, nber_runs: list[tuple[pd.Timestamp, pd.Timestamp]]) -> None:
    fp_mask = scored["label"] & ~scored["nber"].astype(bool)
    runs = boolean_runs(fp_mask)
    print(f"  false-positive runs: {len(runs)}  days: {int(fp_mask.sum())}")
    print(f"  {'start':10s} {'end':10s} {'days':>5s} {'sahm':>6s} {'fallback':>9s} {'other':>6s}  relation")
    nber_starts = {s for s, _ in nber_runs}
    nber_ends = {e for _, e in nber_runs}
    for start, end in runs:
        sl = scored.loc[start:end]
        days = len(sl)
        sahm_days = int(sl["sahm"].sum())
        fallback_days = int((~sl["sahm"] & sl["fallback_hot"]).sum())
        other_days = days - sahm_days - fallback_days
        nxt = end + pd.Timedelta(days=1)
        prev = start - pd.Timedelta(days=1)
        if nxt in nber_starts or (nxt in scored.index and bool(scored.loc[nxt, "nber"])):
            # The run ends the day before an NBER day: a lead into a recession.
            relation = "lead into next NBER day"
        elif prev in nber_ends or (prev in scored.index and bool(scored.loc[prev, "nber"])):
            relation = "overhang after NBER"
        else:
            relation = "isolated"
        if days < 14 and relation == "isolated":
            continue
        med = float(sl.loc[~sl["sahm"], "fallback"].median()) if fallback_days else float("nan")
        med_s = f"  median fallback {med:.2f}" if fallback_days else ""
        print(f"  {_d(start)} {_d(end)} {days:5d} {sahm_days:6d} {fallback_days:9d} {other_days:6d}  {relation}{med_s}")
    short = [
        (s, e)
        for s, e in runs
        if (e - s).days + 1 < 14
        and not ((e + pd.Timedelta(days=1) in nber_starts) or (s - pd.Timedelta(days=1) in nber_ends))
    ]
    short_days = 0
    for s, e in short:
        short_days += len(scored.loc[s:e])
    print(f"  isolated runs shorter than 14 days, omitted above: {len(short)} runs, {short_days} days")


def component_split(scored: pd.DataFrame) -> None:
    label = scored["label"]
    nber = scored["nber"].astype(bool)
    sahm = scored["sahm"]
    hot = scored["fallback_hot"]

    def line(name: str, mask: pd.Series) -> None:
        n = int(mask.sum())
        if n == 0:
            print(f"  {name}: 0 days")
            return
        sub = scored.loc[mask]
        print(
            f"  {name}: {n} days | sahm {int(sub['sahm'].sum())} | "
            f"fallback-only {int((~sub['sahm'] & sub['fallback_hot']).sum())} | "
            f"neither {int((~sub['sahm'] & ~sub['fallback_hot']).sum())}"
        )

    _section("Which component is on")
    line("RECESSION dominant", label)
    line("dominant and NBER on (hits)", label & nber)
    line("dominant and NBER off (false positives)", label & ~nber)
    line("NBER on but label off (misses)", ~label & nber)
    missed = scored.loc[~label & nber]
    if len(missed):
        lost_tie = int((missed["sahm"] & (missed["score"] >= 1.0 - 1e-9)).sum())
        hot_lost = int((~missed["sahm"] & missed["fallback_hot"]).sum())
        print(f"  misses where Sahm was on but lost the argmax: {lost_tie}")
        print(f"  misses where the fallback was > 0.5 but another regime scored higher: {hot_lost}")
    # Silence unused-local warnings by referencing the aliases in the debug line.
    print(
        f"  days fallback > 0.5 while Sahm is off: {int((~sahm & hot).sum())}; "
        f"of those, RECESSION dominant: {int((~sahm & hot & label).sum())}"
    )


def unemployment_around(
    monthly_unrate: pd.Series,
    monthly_sahm: pd.Series,
    nber_runs: list[tuple[pd.Timestamp, pd.Timestamp]],
) -> None:
    _section("Unemployment around each NBER episode")
    print("  Sahm dates are the monthly flag the factor frame actually fed the classifier.")
    print(
        f"  {'nber':23s} {'u start':>8s} {'u end':>8s} {'u peak':>8s} {'peak month':>12s} {'sahm on':>10s} {'sahm off':>10s}"
    )
    for n_start, n_end in nber_runs:
        look_lo = (n_start - pd.DateOffset(months=18)).to_period("M").to_timestamp()
        look_hi = (n_end + pd.DateOffset(months=36)).to_period("M").to_timestamp()
        u = monthly_unrate.loc[look_lo:look_hi].dropna()
        flag = monthly_sahm.reindex(u.index).fillna(False).astype(bool) if len(u) else monthly_sahm.iloc[0:0]
        u_at = lambda ts: monthly_unrate.reindex([ts.to_period("M").to_timestamp()]).iloc[0]  # noqa: E731
        peak_idx = u.idxmax() if len(u) else None
        # Sahm run overlapping the episode, on the monthly index.
        runs = boolean_runs(flag)
        n_m0 = n_start.to_period("M").to_timestamp()
        n_m1 = n_end.to_period("M").to_timestamp()
        overlapping = [r for r in runs if r[0] <= n_m1 and r[1] >= n_m0]
        if overlapping:
            s_on, s_off = min(overlapping, key=lambda r: r[0])[0], max(overlapping, key=lambda r: r[1])[1]
        else:
            s_on = s_off = None
        peak_s = f"{float(u.max()):8.1f}" if peak_idx is not None else "     n/a"
        try:
            u0 = f"{float(u_at(n_start)):8.1f}"
        except (KeyError, IndexError, TypeError):
            u0 = "     n/a"
        try:
            u1 = f"{float(u_at(n_end)):8.1f}"
        except (KeyError, IndexError, TypeError):
            u1 = "     n/a"
        print(f"  {_d(n_start)}..{_d(n_end)} {u0} {u1} {peak_s} {_d(peak_idx):>12s} {_d(s_on):>10s} {_d(s_off):>10s}")


def _flag_disagreements(ours: pd.Series, fred: pd.Series, label: str) -> None:
    both = pd.concat([ours.rename("ours"), fred.rename("fred")], axis=1, join="inner").dropna()
    both = both.loc["1990-01-01":]
    if both.empty:
        print(f"  {label}: no overlap")
        return
    diff = both["ours"] - both["fred"]
    our_flag = both["ours"] >= 0.5
    fred_flag = both["fred"] >= 0.5
    disagree = our_flag != fred_flag
    print(
        f"  {label}: {len(both)} months  corr {both['ours'].corr(both['fred']):.4f}  "
        f"MAE {diff.abs().mean():.4f}  max|diff| {diff.abs().max():.4f}"
    )
    print(
        f"  {'':16s} flag>=0.5 disagreements: {int(disagree.sum())}  "
        f"ours-only {int((our_flag & ~fred_flag).sum())}  fred-only {int((~our_flag & fred_flag).sum())}"
    )
    # FRED prints SAHM* to 0.01. A value 1 ulp under 0.5 is the same published number.
    rounded_mismatch = int(((both["ours"].round(2) >= 0.5) != (both["fred"].round(2) >= 0.5)).sum())
    imax = diff.abs().idxmax()
    print(
        f"  {'':16s} flag mismatches after rounding both to 0.01: {rounded_mismatch}; "
        f"largest level gap {_d(pd.Timestamp(imax))} "
        f"ours {both.loc[imax, 'ours']:.4f} fred {both.loc[imax, 'fred']:.4f}"
    )
    for ts, row in both.loc[disagree].iterrows():
        gap = row["ours"] - row["fred"]
        if abs(gap) < 1e-6:
            continue
        print(f"    {_d(pd.Timestamp(ts))}  ours {row['ours']:.4f}  fred {row['fred']:.4f}")


def compare_published_sahm(
    monthly_unrate: pd.Series,
    published: dict[str, pd.Series],
    raw_unrate: pd.Series,
) -> None:
    """Compare the current implementation with FRED, then the former window.

    The current code takes the low over the PREVIOUS 12 three-month averages
    (``shift(1).rolling(12)``), rounded to 0.01 -- FRED's published definition.
    It used to take ``rolling(12).min()``, which includes the current average and
    so looks back only 11 months (the "former" rows below, kept so the change
    stays measurable). Everything is scored against SAHMCURRENT on the raw
    monthly UNRATE, not the daily forward-fill.
    """
    _section("Sahm implementation vs published FRED indicators")
    from_frame = _month_start(sahm_value_from_unrate(monthly_unrate).dropna())
    raw_m = _month_start(raw_unrate)
    ma3 = raw_m.rolling(3, min_periods=3).mean()
    include_current = (ma3 - ma3.rolling(12, min_periods=12).min()).clip(lower=0.0)  # the former implementation
    prior_12 = (ma3 - ma3.shift(1).rolling(12, min_periods=12).min()).clip(lower=0.0)
    # The frame's daily forward-fill must not have changed the monthly value.
    check = pd.concat(
        [from_frame.rename("frame"), _month_start(prior_12.round(2)).rename("raw")],
        axis=1,
        join="inner",
    ).dropna()
    check = check.loc["1990-01-01":]
    gap = (check["frame"] - check["raw"]).abs()
    print(f"  frame vs raw-UNRATE Sahm value, 1990..: {len(check)} months, max|diff| {gap.max():.6f}")

    current = published.get("SAHMCURRENT")
    realtime = published.get("SAHMREALTIME")
    if current is not None:
        fred_m = _month_start(current)
        _flag_disagreements(from_frame, fred_m, "current code vs SAHMCURRENT")
        _flag_disagreements(_month_start(include_current), fred_m, "former (current month included) vs SAHMCURRENT")
        _flag_disagreements(_month_start(prior_12), fred_m, "raw prior-12, unrounded vs SAHMCURRENT")
    if realtime is not None:
        _flag_disagreements(from_frame, _month_start(realtime), "current code vs SAHMREALTIME")


def overhang_versus_unemployment_peak(
    scored: pd.DataFrame,
    nber_runs: list[tuple[pd.Timestamp, pd.Timestamp]],
    monthly_unrate: pd.Series,
) -> None:
    """Split each post-trough tail into 'unemployment still rising' and 'after the peak'."""
    _section("Post-trough label days versus the unemployment peak")
    print("  Peak is the max UNRATE from the NBER start through 36 months after the end.")
    print(f"  {'nber end':10s} {'tail days':>9s} {'while u rising':>14s} {'after u peak':>13s} {'peak':>10s}")
    for _n_start, n_end in nber_runs:
        nxt = n_end + pd.Timedelta(days=1)
        if nxt not in scored.index or not bool(scored.loc[nxt, "label"]):
            print(f"  {_d(n_end)} {0:9d} {0:14d} {0:13d} {'-':>10s}")
            continue
        # Walk the contiguous label run that starts the day after the trough.
        tail = scored.loc[nxt:]
        off = tail.index[~tail["label"].astype(bool)]
        tail_end = off[0] - pd.Timedelta(days=1) if len(off) else tail.index[-1]
        sl = scored.loc[nxt:tail_end]
        look_hi = (n_end + pd.DateOffset(months=36)).to_period("M").to_timestamp()
        look_lo = _n_start.to_period("M").to_timestamp()
        u = monthly_unrate.loc[look_lo:look_hi].dropna()
        if u.empty:
            print(f"  {_d(n_end)} {len(sl):9d} {'n/a':>14s} {'n/a':>13s}")
            continue
        peak = pd.Timestamp(u.idxmax())
        # The peak month's print applies through that month, so "after the peak"
        # starts on the first day of the next month.
        after = peak + pd.offsets.MonthBegin(1)
        rising = int((sl.index < after).sum())
        past = int((sl.index >= after).sum())
        print(f"  {_d(n_end)} {len(sl):9d} {rising:14d} {past:13d} {_d(peak):>10s}")


def monthly_agreement(scored: pd.DataFrame, usrec: pd.Series) -> None:
    """A month is NBER-on from USREC. The label is on if a majority of days are."""
    _section("Monthly agreement (supplement; NBER dates months, not days)")
    usrec_m = _month_start(usrec)
    usrec_m = usrec_m.loc["1990-01-01":]
    day_share = scored["label"].resample("MS").mean()
    label_m = day_share >= 0.5
    both = pd.concat(
        [label_m.rename("label"), (usrec_m >= 0.5).rename("nber")],
        axis=1,
        join="inner",
    ).dropna()
    m = binary_counts(both["label"], both["nber"])
    print(f"  months compared: {int(m['n'])}")
    print(f"  NBER month share {_pct(both['nber'].sum(), len(both))}   label-majority share {_pct(m['share'], 1)}")
    print_agreement([("RECESSION dominant in a majority of days", m)])


def main() -> None:
    logger.remove()
    eval_end = date.today()
    client = Fred(api_key=get_fred_api_key())
    info = fetch_series_info(client)
    if "USREC" not in info:
        raise SystemExit("USREC is not available; cannot score NBER months.")

    # Pull history a bit before the context window so the first episode's lead is visible.
    hist_start = date(1988, 1, 1)
    usrec = fetch_values(client, "USREC", hist_start, eval_end)
    usrecd = fetch_values(client, "USRECD", hist_start, eval_end) if "USRECD" in info else None
    usrecm = fetch_values(client, "USRECM", hist_start, eval_end) if "USRECM" in info else None
    raw_unrate = fetch_values(client, "UNRATE", date(1978, 1, 1), eval_end)
    published: dict[str, pd.Series] = {}
    for sid in ("SAHMCURRENT", "SAHMREALTIME"):
        if sid in info:
            published[sid] = fetch_values(client, sid, date(1979, 1, 1), eval_end)

    factor_df, tape, _fetch_start = load_tape(eval_end)
    nber_full = align_nber(factor_df.index, usrecd, usrec)

    # Cross-check the daily series against the monthly one.
    _section("USREC vs USRECD")
    if usrecd is None:
        print("  USRECD unavailable. Daily NBER dates are USREC carried across each month.")
        source = "USREC expanded to days"
    else:
        daily_month = (usrecd >= 0.5).resample("MS").max()
        monthly = (_month_start(usrec) >= 0.5).astype(float)
        both = pd.concat([daily_month.rename("d"), monthly.rename("m")], axis=1, join="inner").dropna()
        mismatch = both.loc[both["d"] != both["m"]]
        print(f"  USRECD present. Months compared to USREC: {len(both)}. Mismatches: {len(mismatch)}.")
        if len(mismatch):
            print(f"  first mismatches: {list(mismatch.index[:8].strftime('%Y-%m'))}")
        source = "USRECD"
        # The daily series is the one the task allows once it is verified to exist.
    print(f"  daily NBER source: {source}")
    print(f"  USRECD last: {_d(usrecd.index.max()) if usrecd is not None else '-'}")
    print(f"  USREC  last: {_d(usrec.index.max())}")
    if usrecm is not None:
        # USRECM includes the peak month. USREC starts the month after the peak.
        # Reported so the commonly cited "peak through trough" ranges are not confused with USREC.
        recm_m = (_month_start(usrecm) >= 0.5).loc["1990-01-01":]
        rec_m = (_month_start(usrec) >= 0.5).loc["1990-01-01":]
        both_m = pd.concat([recm_m.rename("peak"), rec_m.rename("after")], axis=1, join="inner")
        only_peak = both_m.index[both_m["peak"] & ~both_m["after"]]
        print(f"  USRECM (peak month included) months on since 1990: {int(recm_m.sum())}")
        print(f"  USREC  (month after peak)     months on since 1990: {int(rec_m.sum())}")
        print(f"  months only USRECM calls recession: {[t.strftime('%Y-%m') for t in only_peak]}")

    soft = ism_fallback(factor_df)
    sahm = RulesBasedClassifier._safe_bool(factor_df, "sahm_recession")
    frame = pd.DataFrame(
        {
            "label": tape["dominant_regime"].eq("RECESSION"),
            "score": tape["score_RECESSION"],
            "sahm": sahm,
            "fallback": soft,
            "fallback_hot": soft > 0.5,
            "nber": nber_full,
        },
        index=factor_df.index,
    )
    # Sanity: the documented override. A failure here means the tape is not the rule we think it is.
    sahm_on = frame["sahm"] & frame["score"].notna()
    violations = int((sahm_on & (frame["score"] - 1.0).abs().gt(1e-9)).sum())
    print(f"  Sahm-on days whose RECESSION score is not 1.0: {violations}")

    nber_last = frame.index[frame["nber"].notna()].max()
    scored = frame.loc[EVAL_START:nber_last].dropna(subset=["nber"]).copy()
    scored["nber"] = scored["nber"] >= 0.5
    context = frame.loc[CONTEXT_START:nber_last].dropna(subset=["nber"]).copy()
    context["nber"] = context["nber"] >= 0.5

    if scored.empty:
        raise SystemExit("No days in the headline window have an NBER value.")
    for col in ("unemployment", "ism_pmi"):
        missing = float(factor_df.loc[scored.index, col].isna().mean())
        print(f"  {col} missing in the scored window: {missing:.1%}")
        if missing > 0.05:
            raise SystemExit(f"{col} is missing on more than 5% of scored days; the tape would not be the live one.")

    unscored_tail = int(frame.loc[frame.index > nber_last].shape[0]) if nber_last is not None else 0
    _section("Headline window")
    print(f"  scored days       {len(scored)}  {_d(scored.index.min())} .. {_d(scored.index.max())}")
    print(f"  tape days after the last NBER print, not scored: {unscored_tail}")
    print(f"  NBER day share    {_pct(int(scored['nber'].sum()), len(scored))}")
    print(f"  RECESSION dominant {_pct(int(scored['label'].sum()), len(scored))}")
    print(f"  Sahm flag on      {_pct(int(scored['sahm'].sum()), len(scored))}")
    print(
        f"  ISM-fallback >0.5 {_pct(int(scored['fallback_hot'].sum()), len(scored))}  (threshold {_TH_REC_ISM}, slope {_SL_REC_ISM}, input is -z of IPMAN)"
    )

    _section("Dominant-regime mix (scored days)")
    # Rebuild dominant from the tape so the mix is the classifier's, not only RECESSION.
    dom = tape.loc[scored.index, "dominant_regime"]
    mix = dom.value_counts()
    for name, count in mix.items():
        print(f"  {name:20s} {int(count):6d}  {_pct(int(count), len(dom))}")

    _section("Agreement with NBER, daily")
    rows = [
        ("RECESSION dominant", binary_counts(scored["label"], scored["nber"])),
        ("Sahm flag alone", binary_counts(scored["sahm"], scored["nber"])),
        ("ISM-fallback score > 0.5", binary_counts(scored["fallback_hot"], scored["nber"])),
        (
            "fallback > 0.5 and Sahm off",
            binary_counts(scored["fallback_hot"] & ~scored["sahm"], scored["nber"]),
        ),
    ]
    print_agreement(rows)
    print("  ISM-fallback uses IPMAN industrial production, not the ISM PMI survey.")
    print("  'fallback > 0.5 and Sahm off' is the branch the classifier actually consults.")

    # Spells on the context window so a 1990 lead that started in 1989 stays one spell.
    # Headline false positives are still counted only on `scored` (from 1990).
    label_runs = boolean_runs(context["label"])
    nber_runs = boolean_runs(scored["nber"])
    _section("NBER episodes in the scored window (from the series)")
    for a, b in nber_runs:
        print(f"  {_d(a)} .. {_d(b)}  ({len(scored.loc[a:b])} days)")

    _section("Lead and lag of the RECESSION label, per NBER episode")
    episode_table(nber_runs, label_runs, scored, pd.Timestamp(scored.index.max()))

    _section("False-positive periods (label on, NBER off)")
    false_positive_table(scored, nber_runs)
    component_split(scored)

    monthly_unrate = _month_start(factor_df["unemployment"].dropna())
    monthly_sahm = _month_start(frame["sahm"].astype(float)).ge(0.5)
    unemployment_around(monthly_unrate, monthly_sahm, nber_runs)
    overhang_versus_unemployment_peak(scored, nber_runs, monthly_unrate)
    compare_published_sahm(monthly_unrate, published, raw_unrate)
    if "USREC" in info:
        monthly_agreement(scored, usrec)

    _section("How to read this")
    print("  NBER announces peaks and troughs with a long delay. The factor frame uses today's")
    print("  vintage of UNRATE. Agreement here is with the final dates, not a real-time hit rate.")
    print("  A negative onset is the label firing before the NBER month. A positive onset is a lag.")
    print("  Days after the trough where unemployment is still elevated are what the Sahm rule does.")


if __name__ == "__main__":
    main()
