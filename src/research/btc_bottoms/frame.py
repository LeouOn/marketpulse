"""Point-in-time daily BTC + macro analysis frame (BTC bottom study, wave 1).

One row per UTC calendar day, a sorted unique tz-naive ``DatetimeIndex`` named
``ts`` (midnight of the bar's day). ``build_frame(refresh)`` assembles the
frame from the fetchers in :mod:`fetch_fred` / :mod:`fetch_onchain` plus the
repo's existing BTC / FGI loaders, caches it at
``data/cache/btc_bottoms/frame.parquet`` and returns it.

Honesty rules this module enforces (see the shared contract)
------------------------------------------------------------

* **Point-in-time.** Row D holds only what was published by the END of day D.
  Daily FRED market series dated D are treated as available on D+1
  (conservative, per the contract), so their index is shifted +1 calendar day.
  A Friday-dated value therefore legitimately appears on Saturday's row, and
  Monday's row stays NaN unless something was published Sunday -- that is the
  documented consequence of a *calendar* (not business-day) shift.
* **No synthetic data.** The on-chain columns come only from the verified
  keyless Coin Metrics *community* API. ``on_chain.fetch_mvrv`` and
  ``data/cache/btc/mvrv.csv`` are synthetic and are never read here.
* **Missing stays NaN** for daily series (no forward fill). The two weekly
  FRED series are forward-filled onto the daily grid *only* with a companion
  ``_age`` column stating how many days old the shown observation is.

Lag table (every non-derived column; ``LAG_TABLE`` is the machine-readable twin)
-------------------------------------------------------------------------------

===================== ============================== ========= ======== ======== =====================================================
column                source                         series    freq     shift    fill / notes
===================== ============================== ========= ======== ======== =====================================================
open..volume          yahoo                          BTC-USD   daily   0        UTC day-D candle closes at end of day D
fgi_value             alternative.me                 FGI       daily   0        value for day D published during day D
dgs10                 FRED                           DGS10     daily   +1       unrevised market close; no ffill
dfii10                FRED                           DFII10    daily   +1       unrevised market close; no ffill
t10yie                FRED                           T10YIE    daily   +1       unrevised market close; no ffill
dgs2                  FRED                           DGS2      daily   +1       unrevised market close; no ffill
vix                   FRED                           VIXCLS    daily   +1       unrevised market close; no ffill
hy_oas                FRED                           BAMLH0A0HYM2 daily  +1       unrevised market close; no ffill; starts 2023-10-04
baa10y                FRED                           BAA10Y    daily   +1       Moody's Baa - 10y since 1986; long-history credit stress
dxy                   FRED                           DTWEXBGS  daily   +5       first visible ~D+3, posting irregular; no ffill
rrp_onday             FRED                           RRPONTSYD daily   +1       overnight reverse repo, $bn; no ffill
walcl                 FRED                           WALCL     weekly  +2       Wednesday obs, released ~Thu; ffill + ``_age``
wtregen               FRED                           WTREGEN   weekly  +2       Treasury General Account; ffill + ``_age``
spx                   yahoo                          ^GSPC     daily   0        NYSE close of day D
gold                  yahoo                          GC=F      daily   0        COMEX front-month close of day D
dxy_ice               yahoo                          DX-Y.NYB  daily   0        ICE dollar index close of day D
mvrv                  Coin Metrics community         CapMVRVCur daily  +1       daily value as of 00:00 UTC boundary; +1 is conservative
mcap_usd              Coin Metrics community         CapMrktCurUSD daily +1     market cap, same convention as mvrv
funding_rate          Kraken Futures (public)        PF_XBTUSD hourly 0        hourly relative rates SUMMED per UTC day
close_chg_21d/63d     derived from close             --        daily   --       pct change over trailing 21/63 days (causal)
dfii10_chg_21d/63d    derived from dfii10            --        daily   --       diff over trailing 21/63 days (causal)
mvrv_z                derived                        --        daily   --       (mcap - mcap/mvrv) / expanding std(mcap), min 365 d
net_liquidity         derived                        --        daily   --       walcl - wtregen - 1000 x rrp_onday ($mn)
===================== ============================== ========= ======== ======== =====================================================

The MVRV Z-score is the classic (market cap - realized cap) / std(market cap)
with realized cap reconstructed as ``mcap_usd / mvrv``; the expanding window
makes it strictly causal. Funding coverage starts ~2025-10 (Kraken public API
serves one year); Binance/Bybit are geo-blocked from this host and the OKX
public history only reaches ~3 months back, so Kraken's hourly PF_XBTUSD is
the deepest keyless source available. All fetchers degrade to NaN columns on
failure or missing keys -- absence is reported, never fabricated.

Source realities measured on 2026-10-03 (live build):

* **BTC daily starts 2014-09-17.** Yahoo now serves BTC-USD daily history as
  a rolling ~12-year window (a request for 2010-07-16 returns bars from
  2014-09-17; the repo's tracked seed and ``YAHOO_BTC_EARLIEST`` already
  reflect this -- the tranche-1 docstring claiming 2010-07-16 is stale).
  Pre-2014 bottoms are therefore outside this frame; 2015/2018/2022/2026
  are covered.
* **``hy_oas`` starts 2023-10-04**: FRED serves BAMLH0A0HYM2 only from that
  date (ICE BofA licensing cutoff on FRED's side).
* **``dxy`` (DTWEXBGS) first becomes visible ~3 days after its observation date**
  (FRED vintage check, daily vintages 2026-09-19 .. 2026-10-02: the obs dated
  2026-09-25 first appeared on vintage 2026-09-28; the lead's independent
  sample measured 3-4). FRED's posting is also irregular -- no new DTWEXBGS
  observation was visible for a full week in that sample -- so the column uses
  **shift +5** (max observed first-visibility 4 plus one day of margin).
  ``dxy_ice`` (yahoo DX-Y.NYB) is the fresher dollar column. Same vintage
  check: DGS10/DFII10/DGS2/BAA10Y lag 1 on weekdays (weekend ramp to 3 is
  FRED's Monday ingestion of Friday's already-public Treasury print),
  T10YIE/BAMLH0A0HYM2/VIXCLS/RRPONTSYD lag 0 on weekdays, WALCL/WTREGEN
  Wednesday observations become visible Thursday (lag 1; the +2 shift keeps
  one day of margin).
* **Coin Metrics restates its most recent days** (values can shift by ~1 ulp
  or more within the tail). The +1 shift protects point-in-time placement,
  not against restatements of already-placed rows; treat the last ~5 days of
  on-chain columns as provisional.
* **Yahoo occasionally holes the newest complete day** (2026-10-02 was absent
  at build time): the frame calendar then ends one day earlier -- honest,
  never patched with partial data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import pandas as pd
from loguru import logger

from src.research.data._paths import cache_dir

__all__ = [
    "FRAME_COLUMNS",
    "DERIVED_COLUMNS",
    "ASOF_COLUMNS",
    "LAG_TABLE",
    "LagSpec",
    "FrameSources",
    "build_frame",
    "asof",
    "coverage_report",
    "main",
]


@dataclass(frozen=True)
class LagSpec:
    """Publication convention of one frame column.

    ``shift_days`` is how many calendar days a value dated D is delayed before
    entering the frame (0 = same-day availability). ``ffill`` marks weekly
    series forward-filled onto the daily grid (always with an ``_age``
    companion column).
    """

    column: str
    source: str
    series: str
    freq: str
    shift_days: int
    ffill: bool = False
    note: str = ""


_BTC_COLS = ["open", "high", "low", "close", "volume"]

LAG_TABLE: dict[str, LagSpec] = {
    **{
        col: LagSpec(col, "yahoo", "BTC-USD", "daily", 0, note="UTC day-D candle closes at end of day D")
        for col in _BTC_COLS
    },
    "fgi_value": LagSpec(
        "fgi_value", "alternative.me", "FGI", "daily", 0, note="value for day D published during day D"
    ),
    "dgs10": LagSpec("dgs10", "FRED", "DGS10", "daily", 1, note="10y nominal; unrevised market close"),
    "dfii10": LagSpec("dfii10", "FRED", "DFII10", "daily", 1, note="10y real; unrevised market close"),
    "t10yie": LagSpec("t10yie", "FRED", "T10YIE", "daily", 1, note="10y breakeven; unrevised market close"),
    "dgs2": LagSpec("dgs2", "FRED", "DGS2", "daily", 1, note="2y nominal; unrevised market close"),
    "vix": LagSpec("vix", "FRED", "VIXCLS", "daily", 1, note="CBOE VIX close; unrevised"),
    "hy_oas": LagSpec(
        "hy_oas",
        "FRED",
        "BAMLH0A0HYM2",
        "daily",
        1,
        note="ICE BofA HY OAS; FRED serves it only from 2023-10-04 (licence cutoff)",
    ),
    "baa10y": LagSpec(
        "baa10y", "FRED", "BAA10Y", "daily", 1, note="Moody's Baa - 10y spread since 1986; long-history credit stress"
    ),
    "dxy": LagSpec(
        "dxy",
        "FRED",
        "DTWEXBGS",
        "daily",
        5,
        note="first visible ~D+3 on FRED (vintages 2026-09-19..10-02), posting irregular; +5 = max observed 4 + 1 margin",
    ),
    "rrp_onday": LagSpec("rrp_onday", "FRED", "RRPONTSYD", "daily", 1, note="overnight reverse repo, $bn"),
    "walcl": LagSpec(
        "walcl", "FRED", "WALCL", "weekly", 2, True, "Fed balance sheet, $bn; Wed obs, released ~Thu; ffill + _age"
    ),
    "wtregen": LagSpec(
        "wtregen", "FRED", "WTREGEN", "weekly", 2, True, "Treasury General Account, $bn; Wed obs; ffill + _age"
    ),
    "spx": LagSpec("spx", "yahoo", "^GSPC", "daily", 0, note="NYSE close of day D"),
    "gold": LagSpec("gold", "yahoo", "GC=F", "daily", 0, note="COMEX front-month close of day D"),
    "dxy_ice": LagSpec("dxy_ice", "yahoo", "DX-Y.NYB", "daily", 0, note="ICE dollar index close of day D"),
    "mvrv": LagSpec(
        "mvrv",
        "Coin Metrics community",
        "CapMVRVCur",
        "daily",
        1,
        note="value as of 00:00 UTC boundary; +1 conservative",
    ),
    "mcap_usd": LagSpec(
        "mcap_usd", "Coin Metrics community", "CapMrktCurUSD", "daily", 1, note="market cap, same convention as mvrv"
    ),
    "funding_rate": LagSpec(
        "funding_rate",
        "Kraken Futures public",
        "PF_XBTUSD",
        "hourly",
        0,
        note="hourly relative rates summed per UTC day; ~1y depth",
    ),
}

DERIVED_COLUMNS: list[str] = [
    "mvrv_z",
    "net_liquidity",
    "close_chg_21d",
    "close_chg_63d",
    "dfii10_chg_21d",
    "dfii10_chg_63d",
]

FRAME_COLUMNS: list[str] = [
    *_BTC_COLS,
    "fgi_value",
    "dgs10",
    "dfii10",
    "t10yie",
    "dgs2",
    "vix",
    "hy_oas",
    "baa10y",
    "dxy",
    "rrp_onday",
    "walcl",
    "walcl_age",
    "wtregen",
    "wtregen_age",
    "spx",
    "gold",
    "dxy_ice",
    "mvrv",
    "mcap_usd",
    "funding_rate",
    *DERIVED_COLUMNS,
]

#: Daily macro/on-chain/funding columns an as-of view may carry forward
#: (never the BTC or FGI columns; the weekly columns already carry their own
#: ``_age`` staleness companions after their +2 shift).
ASOF_COLUMNS: list[str] = [
    "dgs10",
    "dfii10",
    "t10yie",
    "dgs2",
    "vix",
    "hy_oas",
    "baa10y",
    "dxy",
    "rrp_onday",
    "spx",
    "gold",
    "dxy_ice",
    "mvrv",
    "mcap_usd",
    "funding_rate",
]

FRAME_CACHE_NAME = "btc_bottoms/frame.parquet"


# ---------------------------------------------------------------------------
# Source seams (real fetchers; tests inject fakes)
# ---------------------------------------------------------------------------


@dataclass
class FrameSources:
    """Fetchers the frame is assembled from. Every seam returns raw,
    *unshifted* series indexed by publication/observation date; frame.py owns
    every lag decision so the lag table is honoured in exactly one place."""

    btc_daily: Callable[[], pd.DataFrame]
    fgi: Callable[[], pd.DataFrame]
    fred_daily: Callable[[], dict[str, pd.Series]]
    fred_weekly: Callable[[], dict[str, pd.Series]]
    yahoo_risk: Callable[[], dict[str, pd.Series]]
    onchain: Callable[[], dict[str, pd.Series]]
    funding: Callable[[], pd.Series]
    today: Callable[[], pd.Timestamp] = field(
        default_factory=lambda: lambda: pd.Timestamp.now("UTC").tz_convert(None).normalize()
    )


def _real_sources(force: bool) -> FrameSources:
    from src.research.data import load_daily
    from src.research.data.fear_greed import fetch_fear_greed

    from . import fetch_fred, fetch_onchain

    def _btc() -> pd.DataFrame:
        df = load_daily(force_refresh=force)
        return df[["ts", *_BTC_COLS]]

    def _fgi() -> pd.DataFrame:
        return fetch_fear_greed(force=force)[["ts", "fgi_value"]]

    def _fred_daily() -> dict[str, pd.Series]:
        out: dict[str, pd.Series] = {}
        for col, sid in fetch_fred.SERIES_DAILY.items():
            s = fetch_fred.fetch_series(sid, refresh=force)
            if s is not None and not s.empty:
                out[col] = s.rename(col)
        return out

    def _fred_weekly() -> dict[str, pd.Series]:
        out: dict[str, pd.Series] = {}
        for col, sid in fetch_fred.SERIES_WEEKLY.items():
            s = fetch_fred.fetch_series(sid, refresh=force)
            if s is not None and not s.empty:
                out[col] = s.rename(col)
        return out

    def _yahoo_risk() -> dict[str, pd.Series]:
        from src.research.data.yahoo import YahooProvider

        provider = YahooProvider()
        out: dict[str, pd.Series] = {}
        for col, ticker in {"spx": "^GSPC", "gold": "GC=F", "dxy_ice": "DX-Y.NYB"}.items():
            try:
                df = provider.fetch(ticker, "2005-01-01", "2030-01-01")
            except Exception as exc:  # honest absence, never a crash
                logger.warning(f"[btc_bottoms] yahoo {ticker} unavailable: {exc}")
                continue
            if df.empty:
                continue
            s = df.set_index("ts")["close"].rename(col)
            if s.index.tz is not None:
                s.index = s.index.tz_convert(None)
            out[col] = s
        return out

    def _onchain() -> dict[str, pd.Series]:
        return fetch_onchain.fetch_coinmetrics(refresh=force)

    def _funding() -> pd.Series:
        return fetch_onchain.fetch_kraken_funding(refresh=force)

    return FrameSources(
        btc_daily=_btc,
        fgi=_fgi,
        fred_daily=_fred_daily,
        fred_weekly=_fred_weekly,
        yahoo_risk=_yahoo_risk,
        onchain=_onchain,
        funding=_funding,
    )


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def _shift(series: pd.Series, days: int) -> pd.Series:
    """Delay a publication-dated series so value dated D enters at row D+days."""
    if series.empty:
        return series
    s = series.dropna().sort_index()
    s.index = s.index + pd.Timedelta(days=days)
    return s


def _attach_plain(df: pd.DataFrame, col: str, series: pd.Series, shift: int) -> None:
    """Attach a no-ffill daily series: missing publication days stay NaN."""
    if series.empty:
        df[col] = float("nan")
        return
    df[col] = _shift(series, shift).reindex(df.index)


def _attach_weekly(df: pd.DataFrame, col: str, series: pd.Series, shift: int) -> None:
    """Attach a weekly series: shift, ffill onto the calendar, track age.

    ``_age`` counts calendar days between the row date and the *observation*
    date of the value shown (so it includes the release lag).
    """
    if series.empty:
        df[col] = float("nan")
        df[f"{col}_age"] = float("nan")
        return
    raw = series.dropna().sort_index()
    delayed = raw.copy()
    delayed.index = raw.index + pd.Timedelta(days=shift)
    obs = pd.Series(raw.index, index=delayed.index)  # placement day -> obs day
    df[col] = delayed.reindex(df.index, method="ffill")
    obs_cal = obs.reindex(df.index, method="ffill")
    df[f"{col}_age"] = (df.index - obs_cal).dt.days.astype(float)
    df.loc[df[col].isna(), f"{col}_age"] = float("nan")


def _derive(df: pd.DataFrame) -> None:
    """Causal derived columns (inputs are already point-in-time shifted).

    ``close_chg_*`` / ``dfii10_chg_*`` are literal calendar-day differences
    on the frame; rows whose D-21/D-63 counterpart is NaN (no publication
    within the lag) stay NaN -- never back-filled.
    """
    df["close_chg_21d"] = df["close"].pct_change(21, fill_method=None)
    df["close_chg_63d"] = df["close"].pct_change(63, fill_method=None)
    df["dfii10_chg_21d"] = df["dfii10"].diff(21)
    df["dfii10_chg_63d"] = df["dfii10"].diff(63)
    # Net liquidity ($mn): Fed balance sheet - Treasury General Account -
    # overnight reverse repo. WALCL/WTREGEN are $mn, RRPONTSYD is $bn (x1000).
    df["net_liquidity"] = df["walcl"] - df["wtregen"] - 1_000.0 * df["rrp_onday"]


def _mvrv_z_full(mvrv_raw: pd.Series, mcap_raw: pd.Series, shift: int) -> pd.Series:
    """Classic MVRV Z-score on the FULL shifted history.

    Computed before the calendar reindex so the expanding std window sees
    all pre-frame history (a frame starting mid-history would otherwise
    wrongly report NaN). realized cap = mcap / mvrv; expanding window is
    strictly causal.
    """
    mvrv = _shift(mvrv_raw, shift)
    mcap = _shift(mcap_raw, shift)
    realized = mcap / mvrv
    expanding_std = mcap.expanding(min_periods=365).std()
    return ((mcap - realized) / expanding_std).rename("mvrv_z")


def _assemble(sources: FrameSources) -> pd.DataFrame:
    # Evaluate "today" BEFORE fetching so a run straddling UTC midnight cannot
    # admit a partial bar (fetch at 23:59:55, cutoff evaluated post-midnight).
    today = pd.Timestamp(sources.today()).normalize()
    btc = sources.btc_daily().copy()
    btc["ts"] = pd.to_datetime(btc["ts"]).dt.normalize()
    btc = btc[btc["ts"] < today]  # only complete UTC days

    if btc.empty:
        raise ValueError("BTC daily source is empty: no calendar to build the frame on")

    cal = pd.date_range(btc["ts"].min(), btc["ts"].max(), freq="D", name="ts")
    df = pd.DataFrame(index=cal)
    for col in _BTC_COLS:
        df[col] = btc.set_index("ts")[col].reindex(cal).astype(float)

    fgi = sources.fgi()
    if not fgi.empty:
        s = fgi.set_index(pd.to_datetime(fgi["ts"]).dt.normalize())["fgi_value"]
        _attach_plain(df, "fgi_value", s, LAG_TABLE["fgi_value"].shift_days)
    else:
        df["fgi_value"] = float("nan")

    for col, s in sources.fred_daily().items():
        _attach_plain(df, col, s, LAG_TABLE[col].shift_days)
    for col in ("dgs10", "dfii10", "t10yie", "dgs2", "vix", "hy_oas", "baa10y", "dxy", "rrp_onday", "fgi_value"):
        if col not in df.columns:
            df[col] = float("nan")

    for col, s in sources.fred_weekly().items():
        _attach_weekly(df, col, s, LAG_TABLE[col].shift_days)
    for col in ("walcl", "wtregen"):
        if col not in df.columns:
            df[col] = float("nan")
            df[f"{col}_age"] = float("nan")

    for col, s in sources.yahoo_risk().items():
        _attach_plain(df, col, s, LAG_TABLE[col].shift_days)
    for col in ("spx", "gold", "dxy_ice"):
        if col not in df.columns:
            df[col] = float("nan")

    oc = sources.onchain()
    for col in ("mvrv", "mcap_usd"):
        s = oc.get(col)
        _attach_plain(df, col, s if s is not None else pd.Series(dtype=float), LAG_TABLE[col].shift_days)

    mvrv_raw = oc.get("mvrv", pd.Series(dtype=float))
    mcap_raw = oc.get("mcap_usd", pd.Series(dtype=float))
    z = _mvrv_z_full(mvrv_raw, mcap_raw, LAG_TABLE["mvrv"].shift_days)
    df["mvrv_z"] = z.reindex(df.index) if not z.empty else float("nan")

    funding = sources.funding()
    _attach_plain(
        df,
        "funding_rate",
        funding if funding is not None else pd.Series(dtype=float),
        LAG_TABLE["funding_rate"].shift_days,
    )

    _derive(df)

    df = df[FRAME_COLUMNS].astype(float)
    return df


def build_frame(refresh: bool = False, *, sources: FrameSources | None = None) -> pd.DataFrame:
    """Return the point-in-time daily BTC + macro frame.

    Args:
        refresh: Rebuild from the fetchers (forcing their refresh too) and
            overwrite the parquet cache. With ``False`` an existing cache is
            served as-is.
        sources: Injection seam for offline tests. Defaults to the real
            fetchers (yahoo BTC, alternative.me FGI, FRED, yahoo risk assets,
            Coin Metrics community, Kraken funding).

    Raises:
        ValueError: If the BTC source is empty (no calendar to build on).
    """
    from pathlib import Path

    cache_path: Path = cache_dir("btc_bottoms") / "frame.parquet"
    if not refresh and cache_path.exists():
        try:
            cached = pd.read_parquet(cache_path)
            if list(cached.columns) == FRAME_COLUMNS:
                return cached
            logger.warning("[btc_bottoms] frame cache schema mismatch; rebuilding")
        except Exception as exc:
            logger.warning(f"[btc_bottoms] frame cache unreadable ({exc}); rebuilding")

    if sources is None:
        sources = _real_sources(force=refresh)
    df = _assemble(sources)

    tmp = cache_path.with_suffix(".parquet.tmp")
    df.to_parquet(tmp)
    tmp.replace(cache_path)
    logger.info(f"[btc_bottoms] frame built: {len(df)} rows, {df.index.min().date()} -> {df.index.max().date()}")
    return df


# ---------------------------------------------------------------------------
# As-of view (causal convenience over the sparse daily macro columns)
# ---------------------------------------------------------------------------


def asof(frame: pd.DataFrame, max_stale_days: int = 5) -> pd.DataFrame:
    """Return a copy carrying :data:`ASOF_COLUMNS` forward up to ``max_stale_days``.

    Sunday/Monday rows of the daily macro columns are NaN by construction
    (calendar-shifted business-day publications; correct, but every consumer
    would otherwise re-derive an as-of rule). This pure function forward-fills
    each as-of column from its most recent placement and adds ``<col>_age`` =
    calendar days since that placement entered the frame (0 on the placement
    row). Values older than ``max_stale_days`` stay NaN -- it never bridges a
    longer gap -- and the BTC/FGI/weekly columns are never touched.

    Causal by construction (prefix-invariant): each output row depends only on
    placements at or before it.
    """
    out = frame.copy()
    idx = frame.index
    placement_dates = pd.Series(idx, index=idx)
    for col in ASOF_COLUMNS:
        if col not in frame.columns:
            continue
        s = frame[col]
        placed = s.notna()
        dates = placement_dates.where(placed).ffill()
        age = (idx - dates).dt.days.astype(float)
        filled = s.ffill()
        ok = filled.notna() & (age <= max_stale_days)
        out[col] = filled.where(ok)
        out[f"{col}_age"] = age.where(ok)
    return out


# ---------------------------------------------------------------------------
# Reporting / CLI
# ---------------------------------------------------------------------------


def coverage_report(df: pd.DataFrame) -> pd.DataFrame:
    """Per-column coverage: first/last valid date, non-NaN count and share."""
    rows = []
    for col in df.columns:
        s = df[col]
        valid = s.notna()
        rows.append(
            {
                "first_valid": s.index[valid][0] if valid.any() else pd.NaT,
                "last_valid": s.index[valid][-1] if valid.any() else pd.NaT,
                "non_nan": int(valid.sum()),
                "pct_non_nan": 100.0 * valid.mean(),
            }
        )
    return pd.DataFrame(rows, index=pd.Index(df.columns, name="column"))


def lag_table_frame() -> pd.DataFrame:
    """LAG_TABLE as a printable DataFrame."""
    return pd.DataFrame(
        [
            {
                "column": spec.column,
                "source": spec.source,
                "series": spec.series,
                "freq": spec.freq,
                "shift_days": spec.shift_days,
                "ffill": spec.ffill,
                "note": spec.note,
            }
            for spec in LAG_TABLE.values()
        ]
    ).set_index("column")


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m src.research.btc_bottoms.frame [--refresh]``."""
    import argparse

    parser = argparse.ArgumentParser(description="Build the point-in-time BTC + macro frame")
    parser.add_argument("--refresh", action="store_true", help="force fetcher refresh before rebuilding")
    args = parser.parse_args(argv)

    df = build_frame(refresh=args.refresh)
    print(f"frame: {len(df)} rows, {df.index.min().date()} -> {df.index.max().date()}")
    print()
    print(coverage_report(df).to_string())
    print()
    print(lag_table_frame().to_string())
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
