"""Bottom-event labeller for the BTC bottom study (wave 1, g3).

``find_bottoms`` produces *hindsight* labels of cycle-scale and swing-scale
bottoms. Each event carries a ``confirm_date`` -- the first day the low became
identifiable -- so wave 2 can measure signal lead time honestly: a signal that
only fires at or after ``confirm_date`` is not a bottom call. Labels already
confirmed never change as more data arrives (pinned by a truncation test);
only the trailing provisional episode can still move.

Design decisions (defended, parameterised)
------------------------------------------
* **Price basis: close.** All thresholds (drawdowns, rebounds, ATHs) use the
  daily close. The intraday ``low`` on the bottom day is *reported* in
  ``bottom_intraday_low`` but never used for detection: intraday wicks are
  noise-prone and the close is the value a daily-bar strategy could act on.
* **Cycle episodes span a whole bear market.** The anchor is the running
  all-time-high close. An episode opens the first day ``close <= ATH * (1 -
  cycle_dd)`` (default 45%) and ends only when a **new ATH close** is made --
  that day is the event's ``recovered_date`` ("the episode ends at recovery
  or when a new ATH is made"; for closes the two coincide). The bottom is the
  span's minimum close. Interim bounces do NOT close the episode: in 2018 the
  February/April/June rallies all sit inside the one episode whose low is
  2018-12-15, and the 2019-2020 retracements (6.6k, 4.9k) never re-open it.
  The ``cycle_confirm`` rebound (default +30%) is used *only* to compute
  ``confirm_date`` -- when the low became identifiable -- never to close the
  episode. Consequence worth pinning: because the trigger level always sits
  above the span minimum, the cycle bottom date is invariant to ``cycle_dd``;
  the threshold only decides whether an era qualifies at all.
* **Provisional means the episode is still open.** The trailing episode is
  emitted with ``provisional=True`` when the data ends before a new ATH. Its
  bottom can still move even when ``confirm_date`` is already set (a +30%
  bounce off the running low has happened -- historically that made the low
  final, but only a new ATH makes it *certain*). Read ``provisional`` as "not
  final yet", not "not confirmed".
* **Swing episodes end at the rebound.** The anchor is the rolling max close
  over a trailing ``swing_window`` calendar rows of the daily frame (default
  90; NaN closes are skipped inside the window). Trigger at ``-swing_dd``
  (default 20%), confirm *and close* at ``+swing_confirm`` (default 15%) --
  weeks-scale lows must not wait years for a new ATH. Swings are computed by
  an independent state machine and deliberately overlap cycle episodes --
  that nesting is the feature, not a bug: wave 2 can contrast signal
  behaviour inside vs outside cycle drawdowns.
* **Ties go to the earliest date** (first occurrence of the running ATH, of
  the rolling-window high, and of the episode minimum).
* **Robustness surface.** Every threshold is a keyword argument; the default
  neighbourhood grid, :func:`grid_labels` and :func:`stability_summary` let
  wave 2 sweep a parameter neighbourhood and see how many events appear,
  disappear or shift.

Output contract: one row per bottom with columns ``horizon, peak_date,
peak_price, bottom_date, bottom_price, bottom_intraday_low, drawdown,
confirm_date, days_to_confirm, recovered_date, provisional``; ``drawdown`` is
a negative fraction, ``days_to_confirm`` counts calendar days from the bottom
to its confirmation, ``recovered_date`` is the first close strictly above the
episode peak after the bottom (NaT if never). Rows are sorted by
``bottom_date``.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Mapping, Sequence

import numpy as np
import pandas as pd

__all__ = [
    "EVENT_COLUMNS",
    "CYCLE_DEFAULTS",
    "SWING_DEFAULTS",
    "DEFAULT_GRIDS",
    "find_bottoms",
    "grid_labels",
    "stability_summary",
]

#: Exact output column order of :func:`find_bottoms`.
EVENT_COLUMNS = [
    "horizon",
    "peak_date",
    "peak_price",
    "bottom_date",
    "bottom_price",
    "bottom_intraday_low",
    "drawdown",
    "confirm_date",
    "days_to_confirm",
    "recovered_date",
    "provisional",
]

#: Central (default) parameters per horizon.
CYCLE_DEFAULTS: dict[str, float] = {"cycle_dd": 0.45, "cycle_confirm": 0.30}
SWING_DEFAULTS: dict[str, int | float] = {"swing_window": 90, "swing_dd": 0.20, "swing_confirm": 0.15}

#: Parameter names accepted per horizon by :func:`find_bottoms`.
_HORIZON_PARAMS: dict[str, tuple[str, ...]] = {
    "cycle": ("cycle_dd", "cycle_confirm"),
    "swing": ("swing_window", "swing_dd", "swing_confirm"),
}

#: Default neighbourhood grids for the wave-2 robustness sweep.
DEFAULT_GRIDS: dict[str, dict[str, list[float | int]]] = {
    "cycle": {
        "cycle_dd": [0.40, 0.45, 0.50],
        "cycle_confirm": [0.25, 0.30, 0.35],
    },
    "swing": {
        "swing_window": [60, 90, 120],
        "swing_dd": [0.15, 0.20, 0.25],
        "swing_confirm": [0.10, 0.15, 0.20],
    },
}

#: Default event-matching window (calendar days) for :func:`stability_summary`.
_DEFAULT_MATCH_DAYS = {"cycle": 30, "swing": 14}


# ---------------------------------------------------------------------------
# Input preparation and validation
# ---------------------------------------------------------------------------


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _prepare(df: pd.DataFrame) -> pd.Series:
    """Return the sorted calendar-grid close series, validating the input.

    Accepts any frame with a ``DatetimeIndex`` and a ``close`` column; rows
    with a NaN close are kept in the grid (they still delimit calendar days)
    but never act as anchor, minimum, trigger or confirmation.
    """
    _require(isinstance(df, pd.DataFrame), "df must be a pandas DataFrame")
    _require(isinstance(df.index, pd.DatetimeIndex), "df must be indexed by a DatetimeIndex")
    _require("close" in df.columns, "df must have a 'close' column")
    closes = df["close"].astype(float).sort_index()
    _require(not closes.index.has_duplicates, "duplicate timestamps in the index; labels would be ambiguous")
    return closes


def _validate_params(horizon: str, params: Mapping[str, float | int]) -> None:
    """Range-check horizon parameters (0 < dd < 1, rebound > 0, window >= 1)."""
    if horizon == "cycle":
        _require(0.0 < float(params["cycle_dd"]) < 1.0, "cycle_dd must be in (0, 1)")
        _require(float(params["cycle_confirm"]) > 0.0, "cycle_confirm must be > 0")
    else:
        window = params["swing_window"]
        _require(float(window) == int(window) and int(window) >= 1, "swing_window must be an integer >= 1")
        _require(0.0 < float(params["swing_dd"]) < 1.0, "swing_dd must be in (0, 1)")
        _require(float(params["swing_confirm"]) > 0.0, "swing_confirm must be > 0")


# ---------------------------------------------------------------------------
# Episode state machine (shared by both horizons)
# ---------------------------------------------------------------------------


def _episode_rows(
    dates: pd.DatetimeIndex,
    closes: np.ndarray,
    anchors: np.ndarray,
    anchor_date_of: Callable[[int], pd.Timestamp],
    drawdown: float,
    rebound: float,
    ends_at_new_high: bool,
) -> list[dict]:
    """Run the trigger/resolve state machine over valid-close days.

    An episode opens when ``close <= anchor * (1 - drawdown)``. Resolution is
    horizon-specific: cycle episodes (``ends_at_new_high=True``) resolve the
    day the close exceeds the anchor ATH -- the recovery that closes a bear
    market -- and the anchor is frozen at the peak for as long as the episode
    is open; swing episodes resolve the first day ``close >= episode_min *
    (1 + rebound)``. ``confirm_date`` is NOT computed here: for cycles the
    bounce that identifies the low must not close the episode, so
    confirmation is derived post hoc in :func:`_finalize` uniformly for both
    horizons (for swings the post-hoc date equals the resolution day by
    construction, since the running minimum only falls inside an open
    episode). A still-open episode at data end is emitted as provisional.
    """
    events: list[dict] = []
    active = False
    peak_price = 0.0
    peak_date: pd.Timestamp | None = None
    min_price = np.inf
    min_date: pd.Timestamp | None = None
    for i in range(closes.size):
        close = closes[i]
        if not active:
            if close <= anchors[i] * (1.0 - drawdown):
                active = True
                peak_price = float(anchors[i])
                peak_date = anchor_date_of(i)
                min_price = float(close)
                min_date = dates[i]
        else:
            if close < min_price:
                min_price = float(close)
                min_date = dates[i]
            # New-ATH resolution must compare against the *frozen* episode
            # peak, not anchors[i]: the cummax anchor includes today's close,
            # so `close > anchors[i]` could never fire.
            resolved = close > peak_price if ends_at_new_high else close >= min_price * (1.0 + rebound)
            if resolved:
                events.append(
                    {
                        "peak_date": peak_date,
                        "peak_price": peak_price,
                        "bottom_date": min_date,
                        "bottom_price": min_price,
                        "provisional": False,
                    }
                )
                active = False
    if active:
        events.append(
            {
                "peak_date": peak_date,
                "peak_price": peak_price,
                "bottom_date": min_date,
                "bottom_price": min_price,
                "provisional": True,
            }
        )
    return events


def _cycle_rows(closes: pd.Series, drawdown: float) -> list[dict]:
    """Cycle episodes anchored to the running all-time-high close."""
    ath = closes.cummax()
    # cummax changes value only on strict new highs: those days carry the
    # first-occurrence date of the current anchor, forward-filled afterwards.
    new_high = ath.ne(ath.shift(1)) & closes.notna()
    anchor_dates = pd.Series(closes.index, index=closes.index).where(new_high).ffill()
    valid = closes.notna().to_numpy()
    return _episode_rows(
        dates=closes.index[valid],
        closes=closes.to_numpy()[valid],
        anchors=ath.to_numpy()[valid],
        anchor_date_of=lambda i: anchor_dates.iloc[np.flatnonzero(valid)[i]],
        drawdown=drawdown,
        rebound=0.0,
        ends_at_new_high=True,
    )


def _swing_rows(closes: pd.Series, window: int, drawdown: float, rebound: float) -> list[dict]:
    """Swing episodes anchored to the trailing-window high close."""
    rolling_max = closes.rolling(window, min_periods=1).max()
    valid = closes.notna().to_numpy()
    valid_pos = np.flatnonzero(valid)
    values = closes.to_numpy()
    maxima = rolling_max.to_numpy()

    def anchor_date_of(i: int) -> pd.Timestamp:
        # First occurrence of the window's max inside the trailing window.
        # rolling().max() returns one of the window's values verbatim, so the
        # equality test is exact.
        pos = valid_pos[i]
        start = max(0, pos - window + 1)
        anchor = maxima[pos]
        for j in range(start, pos + 1):
            if values[j] == anchor:
                return closes.index[j]
        return closes.index[pos]  # unreachable for float data; defensive

    return _episode_rows(
        dates=closes.index[valid],
        closes=values[valid],
        anchors=maxima[valid],
        anchor_date_of=anchor_date_of,
        drawdown=drawdown,
        rebound=rebound,
        ends_at_new_high=False,
    )


# ---------------------------------------------------------------------------
# Output assembly
# ---------------------------------------------------------------------------


def _empty_output() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "horizon": pd.Series(dtype=object),
            "peak_date": pd.Series(dtype="datetime64[ns]"),
            "peak_price": pd.Series(dtype=float),
            "bottom_date": pd.Series(dtype="datetime64[ns]"),
            "bottom_price": pd.Series(dtype=float),
            "bottom_intraday_low": pd.Series(dtype=float),
            "drawdown": pd.Series(dtype=float),
            "confirm_date": pd.Series(dtype="datetime64[ns]"),
            "days_to_confirm": pd.Series(dtype="Int64"),
            "recovered_date": pd.Series(dtype="datetime64[ns]"),
            "provisional": pd.Series(dtype=bool),
        }
    )


def _finalize(
    rows: list[dict], horizon: str, closes: pd.Series, lows: pd.Series | None, rebound: float
) -> pd.DataFrame:
    if not rows:
        return _empty_output()
    out = pd.DataFrame(rows)
    out["horizon"] = horizon
    out["bottom_intraday_low"] = lows.reindex(out["bottom_date"]).to_numpy(dtype=float) if lows is not None else np.nan
    out["drawdown"] = out["bottom_price"] / out["peak_price"] - 1.0
    # Confirmation (post hoc, uniformly for both horizons): first valid close
    # at >= bottom * (1 + rebound) strictly after the bottom day. For swings
    # this is exactly the resolution day; for cycles it is the identifiability
    # bounce inside a possibly still-open episode.
    values = closes.to_numpy()
    confirms: list[pd.Timestamp | None] = []
    recovered: list[pd.Timestamp | None] = []
    for bottom, low_price, peak in zip(out["bottom_date"], out["bottom_price"], out["peak_price"], strict=True):
        after = closes.index > bottom
        tail_mask = after & (values >= low_price * (1.0 + rebound))
        confirms.append(closes.index[tail_mask][0] if tail_mask.any() else None)
        rec_mask = after & (values > peak)
        recovered.append(closes.index[rec_mask][0] if rec_mask.any() else None)
    out["confirm_date"] = pd.to_datetime(confirms) if any(c is not None for c in confirms) else pd.NaT
    out["recovered_date"] = pd.to_datetime(recovered) if any(r is not None for r in recovered) else pd.NaT
    out["days_to_confirm"] = pd.array(
        [
            (conf - bot).days if conf is not None and pd.notna(conf) else None
            for bot, conf in zip(out["bottom_date"], out["confirm_date"], strict=True)
        ],
        dtype="Int64",
    )
    out["provisional"] = out["provisional"].astype(bool)
    out = out.sort_values("bottom_date", kind="stable").reset_index(drop=True)
    return out[EVENT_COLUMNS]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def find_bottoms(
    df: pd.DataFrame,
    horizon: str,
    *,
    cycle_dd: float | None = None,
    cycle_confirm: float | None = None,
    swing_window: int | None = None,
    swing_dd: float | None = None,
    swing_confirm: float | None = None,
) -> pd.DataFrame:
    """Label cycle- or swing-scale bottoms in a daily OHLCV frame.

    Parameters override the module defaults (``CYCLE_DEFAULTS`` /
    ``SWING_DEFAULTS``); only parameters belonging to ``horizon`` may be
    supplied -- a cross-horizon keyword is rejected so a mistyped sweep cannot
    silently no-op. See the module docstring for the detection rules and their
    rationale.
    """
    _require(horizon in _HORIZON_PARAMS, f"horizon must be one of {sorted(_HORIZON_PARAMS)}, got {horizon!r}")
    supplied = {
        "cycle_dd": cycle_dd,
        "cycle_confirm": cycle_confirm,
        "swing_window": swing_window,
        "swing_dd": swing_dd,
        "swing_confirm": swing_confirm,
    }
    for name in _HORIZON_PARAMS[horizon]:
        supplied.pop(name)
    leftover = sorted(k for k, v in supplied.items() if v is not None)
    _require(not leftover, f"{leftover} are not '{horizon}' parameters")

    params: dict[str, float | int] = dict(CYCLE_DEFAULTS) if horizon == "cycle" else dict(SWING_DEFAULTS)
    for name in _HORIZON_PARAMS[horizon]:
        value = {
            "cycle_dd": cycle_dd,
            "cycle_confirm": cycle_confirm,
            "swing_window": swing_window,
            "swing_dd": swing_dd,
            "swing_confirm": swing_confirm,
        }[name]
        if value is not None:
            params[name] = value
    _validate_params(horizon, params)

    closes = _prepare(df)
    if horizon == "cycle":
        rows = _cycle_rows(closes, float(params["cycle_dd"]))
        rebound = float(params["cycle_confirm"])
    else:
        rows = _swing_rows(
            closes, int(params["swing_window"]), float(params["swing_dd"]), float(params["swing_confirm"])
        )
        rebound = float(params["swing_confirm"])
    lows = df["low"].astype(float).reindex(closes.index) if "low" in df.columns else None
    return _finalize(rows, horizon, closes, lows, rebound)


def _grid_combinations(
    horizon: str, grid: Mapping[str, Sequence[float | int]] | None
) -> tuple[list[str], list[dict[str, float | int]]]:
    """Resolve and validate a sweep grid into sorted keys and combos."""
    resolved = DEFAULT_GRIDS[horizon] if grid is None else dict(grid)
    allowed = _HORIZON_PARAMS[horizon]
    unknown = sorted(set(resolved) - set(allowed))
    _require(not unknown, f"grid keys {unknown} are not '{horizon}' parameters")
    keys = sorted(resolved)
    combos = [dict(zip(keys, values, strict=True)) for values in itertools.product(*(resolved[k] for k in keys))]
    return keys, combos


def grid_labels(
    df: pd.DataFrame, horizon: str, grid: Mapping[str, Sequence[float | int]] | None = None
) -> pd.DataFrame:
    """Label bottoms for every parameter combination in ``grid`` (long form).

    Returns one row per (combination, event) with the combination's parameter
    values attached as extra columns, so wave 2 can group and compare label
    sets across the neighbourhood. ``grid=None`` uses :data:`DEFAULT_GRIDS`.
    """
    keys, combos = _grid_combinations(horizon, grid)
    chunks = [find_bottoms(df, horizon, **combo).assign(**combo) for combo in combos]
    non_empty = [chunk for chunk in chunks if len(chunk)]
    if not non_empty:
        return _empty_output().assign(**{k: pd.Series(dtype=float) for k in keys})
    out = pd.concat(non_empty, ignore_index=True)
    param_order = keys + EVENT_COLUMNS
    return out[param_order]


def _match_events(
    baseline: pd.DataFrame, combo: pd.DataFrame, match_days: int
) -> tuple[list[tuple[int, int]], int, int]:
    """Greedy nearest-date matching of combo events onto baseline events.

    Baseline events are taken in date order; each claims the unmatched combo
    event with the nearest bottom date within ``match_days``. Returns
    (matched index pairs, appeared count, disappeared count). Greedy matching
    is adequate for neighbourhood sweeps where events move by days, not by
    episodes; it is documented rather than optimal.
    """
    used: set[int] = set()
    pairs: list[tuple[int, int]] = []
    for bi, bdate in enumerate(baseline["bottom_date"]):
        best_j, best_gap = -1, match_days + 1
        for cj, cdate in enumerate(combo["bottom_date"]):
            if cj in used:
                continue
            gap = abs((cdate - bdate).days)
            if gap <= match_days and gap < best_gap:
                best_j, best_gap = cj, gap
        if best_j >= 0:
            used.add(best_j)
            pairs.append((bi, best_j))
    appeared = len(combo) - len(pairs)
    disappeared = len(baseline) - len(pairs)
    return pairs, appeared, disappeared


def stability_summary(
    df: pd.DataFrame,
    horizon: str,
    grid: Mapping[str, Sequence[float | int]] | None = None,
    baseline: Mapping[str, float | int] | None = None,
    match_days: int | None = None,
) -> pd.DataFrame:
    """Summarise how the label set moves across a parameter neighbourhood.

    For each grid combination: ``matched`` / ``appeared`` / ``disappeared``
    count events relative to the baseline label set (matched by nearest
    bottom date within ``match_days``, default 30 days for cycle and 14 for
    swing), ``shifted`` counts matched events whose bottom date moved, and
    ``max_shift_days`` is the largest such move. The baseline defaults to the
    module defaults and is matched against itself when it appears in the grid.
    """
    keys, combos = _grid_combinations(horizon, grid)
    base_params = dict(CYCLE_DEFAULTS) if horizon == "cycle" else dict(SWING_DEFAULTS)
    if baseline is not None:
        unknown = sorted(set(baseline) - set(_HORIZON_PARAMS[horizon]))
        _require(not unknown, f"baseline keys {unknown} are not '{horizon}' parameters")
        base_params.update(baseline)
    _validate_params(horizon, base_params)
    window = _DEFAULT_MATCH_DAYS[horizon] if match_days is None else int(match_days)
    _require(window > 0, "match_days must be > 0")

    base_events = find_bottoms(df, horizon, **base_params)
    records: list[dict] = []
    for combo in combos:
        combo_events = find_bottoms(df, horizon, **combo)
        pairs, appeared, disappeared = _match_events(base_events, combo_events, window)
        shifts = [
            abs((combo_events["bottom_date"].iloc[cj] - base_events["bottom_date"].iloc[bi]).days) for bi, cj in pairs
        ]
        record: dict[str, float | int] = dict(combo)
        record.update(
            {
                "n_baseline": len(base_events),
                "n_combo": len(combo_events),
                "matched": len(pairs),
                "appeared": appeared,
                "disappeared": disappeared,
                "shifted": sum(1 for s in shifts if s > 0),
                "max_shift_days": max(shifts) if shifts else 0,
            }
        )
        records.append(record)
    return pd.DataFrame(records)
