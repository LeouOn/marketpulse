# Market dashboard data provenance

Audited 2026-09-28 from the handlers in `src/api/routers/market.py`, `src/api/routers/data_quality.py`, `src/api/yahoo_client.py`, `src/api/mock_market.py`, `src/data/market_collector.py`, and `src/data/market_breadth.py`.

Classification:

| Label | Meaning |
| --- | --- |
| live | A quote or probe from an external source for that instrument |
| proxy | A different instrument standing in for the label |
| derived | Computed in this process from other fields |
| mock | Fabricated, random, or a hardcoded fallback |

`MARKETPULSE_ALLOW_MOCK` must be `1`, `true`, or `yes` before mock series are returned. That matches `src/api/market_data_collector.py`.

## What changed for DXY and gold

Verified live with yfinance on 2026-09-28, before the symbol change:

| Key | Old Yahoo symbol | Last close | What it actually is |
| --- | --- | --- | --- |
| DXY | `UUP` | 28.70 | Invesco DB USD Index Bullish ETF |
| GC | `GLD` | 377.91 | SPDR Gold Shares ETF |

Adopted after the same check (`DX=F` and the bare ticker `VIX` both 404):

| Key | Yahoo symbol | Last close | Instrument | 52-week range |
| --- | --- | --- | --- | --- |
| DXY | `DX-Y.NYB` | 101.206 | ICE US Dollar Index | 95.55 – 101.80 |
| GC | `GC=F` | 4152.10 | COMEX gold futures, Dec 26 | 3785.50 – 5586.20 |
| CL | `CL=F` | 92.93 | NYMEX WTI, Nov 26 | 54.98 – 119.48 |
| TNX | `^TNX` | 5.240 | CBOE 10-year yield | 3.947 – 5.274 |

`^TNX` and `CL=F` were already the listed instruments. The 52-week high/low on `/api/market/macro` now use the same Yahoo symbol as the price (`range_symbol`).

Each macro series also carries `symbol`, `instrument`, `is_proxy`, and `source` (`yahoo` or `mock`). `is_proxy` is false for every key in `MACRO_CATALOG` because the symbol is the instrument the key names. Gold is the futures contract, not spot and not GLD. The dollar value is the ICE index, not the UUP ETF.

## `/api/market/macro`

| Field | Source | Class | Notes |
| --- | --- | --- | --- |
| `DXY` | `DX-Y.NYB` via `YahooFinanceClient.get_macro_data` | live | Was `UUP`. Object includes price, change, change_pct, volume, timestamp, symbol, instrument, is_proxy, source. |
| `DXY.high_52w`, `low_52w`, `pct_from_52w_high`, `range_symbol` | `get_52w_range("DX-Y.NYB")` | live | Same symbol as the price. Also attached for `TNX`, `GC`, `BTC`. |
| `GC` | `GC=F` | live | Was `GLD`. Front-month COMEX future. |
| `CL` | `CL=F` | live | WTI future. The old mock key `CLF` is gone; the live key has always been `CL`. |
| `TNX` | `^TNX` | live | Yield in percent, not a bond price. 5.24 means 5.24%. |
| `BTC`, `ETH`, `SOL`, `XRP` | `*-USD` | live | Spot crypto quoted in USD. |
| `NIKKEI`, `HSI`, `SSE`, `ASX`, `FTSE`, `DAX`, `CAC`, `STOXX` | `^N225`, `^HSI`, `000001.SS`, `^AXJO`, `^FTSE`, `^GDAXI`, `^FCHI`, `^STOXX50E` | live | The cash index, not an ETF. |
| `EURUSD`, `GBPUSD`, `USDJPY`, `AUDUSD`, `USDCAD`, `USDCHF` | `*=X` | live | Yahoo FX spot. |
| `market_session` | `local_market_session()` | derived | Server local hour only. Not an exchange calendar and not a random draw. |
| `market_session_basis` | constant `local_clock` | derived | Tells the UI the session label is the clock heuristic. |
| `field_sources` | router | derived | Map of the non-quote fields. `market_session` is `derived`. |
| `economic_sentiment` | `MockMarketDataProvider._get_sentiment_indicator` | mock | Random bucket. Omitted unless `MARKETPULSE_ALLOW_MOCK` is set. Then `field_sources.economic_sentiment` is `mock`. |
| `risk_appetite` | `_get_risk_appetite` | mock | Compares drifted mock SPY/VIX to hardcoded anchors. Same opt-in rule. |
| `sector_performance` | `_get_sector_performance` | mock | Eleven sectors from `random.gauss`. Not sector ETFs. Same opt-in rule. The panel hides itself when this object is absent. |
| `source` | constant `mock` | mock | Present only on the full mock payload, when Yahoo returned nothing and mock is allowed. |

Quote sub-fields on every series: `price`, `change`, `change_pct`, `volume`, `timestamp`, `symbol`, `instrument`, `is_proxy`, `source`.

## `/api/market/dashboard`

Built in `get_dashboard_data` from `MarketPulseCollector.collect_market_internals`.

| Field | Source | Class | Notes |
| --- | --- | --- | --- |
| `timestamp` | `datetime.now()` | derived | Request time. |
| `marketBias` | sign of `spy.change` and `qqq.change` | derived | `BULLISH` / `BEARISH` / `MIXED` / `NEUTRAL`. |
| `volatilityRegime` | `MarketPulseCollector._classify_volatility` on VIX price | derived | Bands at 15 / 20 / 30. |
| `symbols.spy`, `symbols.qqq`, `symbols.vix` | Alpaca, else Yahoo `SPY`, `QQQ`, `^VIX` | live | Mock only if `src/data/market_collector.py` substitutes `mock_provider` after the APIs fail. That path sets `synthetic` and `data_source=mock`, but it does **not** consult `MARKETPULSE_ALLOW_MOCK`. See Follow-ups. |
| `symbols.*.price`, `change`, `change_pct`, `volume`, `timestamp` | the quote above | live | Yahoo quotes also include `open`, `high`, `low`, `data_age_seconds`, `request_time`. |
| `volumeFlow` | sum of SPY/QQQ/IWM volume inside the collector, or the collector's own `volume_flow` | derived | |
| `aiAnalysis` | cached `analyze_with_ai` | derived | Prose from the LLM, or null. Not a market measurement. Refreshed in the background. |
| `dataSource` | collector | derived | `alpaca`, `yahoo`, a comma list, `mock`, or `unknown`. |
| `dataQuality` | `flag_data_quality` | derived | `good` / `partial` / `poor` / `unknown`. |
| `qualityIssues` | `flag_data_quality` issues | derived | |
| `synthetic` | collector / mock provider | derived | True on the mock fallback. |
| `freshnessStatus` | `internals["freshness_status"]` | derived | Usually `unknown`. `flag_data_quality` computes `fresh` / `stale` from `spy.data_age_seconds` but `collect_market_internals` never copies that key onto the payload. |
| `dataAgeSeconds` | `spy.data_age_seconds` | derived | Present on Yahoo quotes. Missing on some Alpaca quotes, so this is often null. |
| `breadth` | same object as `/api/market/breadth` | derived | Omitted when the breadth collector returns the hardcoded mock and mock is not allowed. |
| `screener_summary.top_gainers`, `top_losers` | Redis keys `screener:gainers` / `screener:losers`, else `[]` | live | Empty when the cache is down. Not fabricated names. |

## `/api/market/internals`

Passthrough of `collect_market_internals`.

| Field | Source | Class | Notes |
| --- | --- | --- | --- |
| `spy`, `qqq`, `vix`, `iwm`, `nq=f`, `btc-usd`, `eth-usd` | Alpaca stocks, Rithmic futures, Coinbase crypto, Yahoo fallback | live | Key present only when that source returned it. VIX is `^VIX`. |
| quote fields | same as dashboard symbols | live | |
| `data_source` | collector | derived | |
| `timestamp` | collector | derived | |
| `volume_flow.total_volume_60min`, `symbols_tracked` | sum of available core symbols | derived | Added when the collector did not supply one. |
| `data_quality`, `quality_issues`, `missing_symbols` | `flag_data_quality` | derived | |
| `synthetic` | mock provider | mock | Set only on the collector's mock fallback. See Follow-ups for the missing opt-in. |

## `/api/market/breadth`

`MarketBreadthCollector` samples 10 "NYSE" ETFs (`SPY DIA IWM XLF XLE XLV XLI XLK XLY XLP`) and 8 "Nasdaq" ETFs (`QQQ ARKK XLK SOXX IBB IWF IWO IWM`). The response names the sample in `nyse_symbols` and `nasdaq_symbols`. A reading like `nyse_advancing: 9, nyse_declining: 1` is 9 of those ETFs up, not 9 NYSE issues.

| Field | Source | Class | Notes |
| --- | --- | --- | --- |
| `nyse_advancing`, `nyse_declining`, `nyse_unchanged`, `nyse_ad_ratio`, `nyse_net_ad` | sign of 1-day change on the NYSE ETF list | derived | Count cannot exceed 10 unless the hardcoded fallback fired. |
| `nasdaq_advancing`, `nasdaq_declining`, `nasdaq_unchanged`, `nasdaq_ad_ratio`, `nasdaq_net_ad` | same, Nasdaq ETF list | derived | `IWM` and `XLK` are in both lists. |
| `interpretation` (A/D) | `_interpret_ad_ratio` | derived | Thresholds on the average of the two ratios. |
| `new_highs`, `new_lows`, `hl_ratio`, `net_hl` | sample names within 2% of their own 1-year high or low | derived | Not exchange-wide 52-week highs. |
| `tick_value`, `tick_30min_avg`, `tick_4hr_avg` | upticks minus downticks, scaled toward ±1000 | derived | Both averages copy `tick_value`. This is not the NYSE TICK. |
| `nyse_vold`, `nasdaq_vold`, `total_vold` | up-volume minus down-volume on the sample | derived | Share volume of the ETFs, not exchange VOLD. |
| `mcclellan_oscillator`, `mcclellan_summation` | EMA of in-process A/D history | derived | 0 with interpretation `Insufficient data` until 39 samples exist in this process. Summation is `oscillator * 10`, not the published index. |
| `universe` | constant `etf_sample` | derived | |
| `nyse_symbols`, `nasdaq_symbols` | the lists above | derived | |
| `classification`, `source` | router | derived | `derived` / `yahoo`, or `mock` / `mock` when the counts exceed the sample. |
| `note` | router | derived | Says the counts are the ETF sample. |
| hardcoded fallback (`nyse_advancing` 1520 and the rest of `_get_mock_internals`) | `MarketBreadthCollector._get_mock_internals` | mock | Returned when the whole calculation throws. Withheld unless `MARKETPULSE_ALLOW_MOCK` is set; the response is then `success: false` and names the opt-in. |

## `/api/market/ohlc-dashboard`

Symbols requested: `SPY`, `QQQ`, `BTC`, `ETH`, `VIX`. `get_bars` maps `BTC` and `ETH` through `macro_symbols` to `BTC-USD` and `ETH-USD`. `VIX` is fetched as `^VIX` (`VIX` itself 404s).

| Field | Source | Class | Notes |
| --- | --- | --- | --- |
| `timestamp` | request time | derived | |
| `symbols.<key>` | `OHLCAnalyzer.analyze_symbol` on Yahoo bars for 4h / 1d / 7d / 30d | derived | Bars are live. The trend, strength, patterns, and signals are computed. |
| `symbols.<key>.error` | the exception string | derived | Present only when that symbol failed. |
| `market_summary.overall_trend` | vote of per-symbol `overall_trend` | derived | |
| `market_summary.trending_symbols` | symbols whose trend is bullish or bearish | derived | |
| `market_summary.patterns` | patterns across symbols, top 10 by strength | derived | |
| `market_summary.key_levels` | initialized to `{}` | derived | This handler never fills it. |

## `/api/market/data-quality`

This router is not owned by the symbol fix. Behavior below is what the code does today.

| Field | Source | Class | Notes |
| --- | --- | --- | --- |
| `timestamp` | request time | derived | Summary route. |
| `cache_status` | `YahooFinanceClient._get_cache` | live | `redis_connected` or `redis_unavailable`. |
| `scheduler_running` | literal `True` | mock | Not read from the scheduler. Always true. |
| `{symbol}.symbol` | path echo | derived | |
| `{symbol}.has_data` | `get_single_symbol_data` after `macro_symbols` remap | live | `DXY` now checks `DX-Y.NYB`. `GC` checks `GC=F`. |
| `{symbol}.last_fetch` | request time | derived | Not the bar timestamp. |
| `{symbol}.source` | literal `yahoo` | derived | Stays `yahoo` even when `has_data` is false. |
| `{symbol}.data` | `get_single_symbol_data` | live | price, change, change_pct, volume, timestamp, high, low, open. Null when Yahoo has nothing. |

## Follow-ups

UI (`marketpulse-client/`, for T8). Do not keep the old labels on the new numbers.

| Key | Current label | Recommended label | Why |
| --- | --- | --- | --- |
| `DXY` | US Dollar | US Dollar Index | The card now shows the ICE index near 100 (`DX-Y.NYB`), not the UUP ETF near 28. |
| `GC` | Gold | Gold futures | The card now shows COMEX front-month gold (`GC=F`, thousands), not GLD (hundreds) and not spot. |
| `CLF` | Crude Oil Future | drop the key, or alias it to `CL` | Live oil is `CL` / `CL=F`, already labelled Crude Oil (WTI). `CLF` was only on the mock payload. |

The sector panel reads `sector_performance`. With mock off, that object is absent and the panel stays hidden. Leave it hidden until a real sector source exists.

Breadth tiles labelled `TICK`, `A/D`, and `VOLD` are the ETF sample. A truthful label is "ETF sample" (the payload's `universe` and `note` say so). `nyse_ad_ratio` is not NYSE advance/decline.

Other code:

- `src/data/market_collector.py` still substitutes mock internals when collection fails, without `MARKETPULSE_ALLOW_MOCK`. T2a owns that file. The payload is already marked `synthetic` / `data_source=mock`.
- `src/data/market_breadth.py` `_get_mock_internals` does not set `source`. The router detects it by count. A `source` field on that dict would remove the heuristic.
- `src/api/routers/data_quality.py` hardcodes `scheduler_running: True`.
- `freshness_status` is computed in `flag_data_quality` and then dropped, so the dashboard field stays `unknown`.
- `src/research/data/yahoo.py` `MACRO_SYMBOLS` is a required copy of `YahooFinanceClient.macro_symbols`. This change updates `DXY` and `GC` there so `tests/test_research_data_yahoo.py` stays green. `YahooProvider.load_daily` still defaults to the GLD ticker; that default is separate from the `GC` key.
