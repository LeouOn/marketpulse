# BTC bottom study -- Q3: case files and the current reading

Part 3 of 3 of the pre-registered study (`docs/btc-bottom-study/00-plan.md`, section 5).
This part is **descriptive**: it shows what the signals and macro conditions actually read at
each cycle low and today. It assigns no verdicts (those labels belong to Q1's rule) and makes no
recommendation. The current reading is explicitly **not a forecast**.

- Frame: `data/cache/btc_bottoms/frame.parquet`, sha256
  `7e1107e2e653e493af552efdc516e99dd020a0855e73d3b4d1d917dc8247087e` (verified before generation;
  the generator refuses to run on any other hash).
- `main` at generation: `34af52282d3e9135d13a18dae779fb2ad160b242` (pre-registered plan commit).
- Module: `src/research/btc_bottoms/dossiers.py` (branch `feat/btc-bottoms-case-files`).
- Reproduce the tables:
  `MARKETPULSE_DATA_DIR=$PWD/data/cache python -m src.research.btc_bottoms.dossiers --out tables.md`
- Runtime: about 1 second (frame load + all five dossiers + current reading).

## Standing limits (plan section 7 -- read first)

Hindsight labels; `confirm_date` is optimistic (a +30% bounce occurred before the final low in
2018, 2022 and 2026); the 2026 low is provisional and can still move; MVRV-Z amplitude has
decayed across cycles; macro series that are revised after release are excluded; Coin Metrics
restates its latest days (treat the last 5 rows of on-chain columns as provisional); BTC prices
come from Yahoo; overlapping forward windows are not independent draws; no trading costs or
sizing are modelled. Thresholds were set after the history was known (plan section 0).

## How to read the false-confirm trap

A cycle episode "confirms" its low the first day price closes 30% above that low. The trap:
inside one episode this can happen at an *interim* low, and a later lower low breaks it. Each
table row below is one such event -- on the `confirm_date`, with price at `confirm_close`, a
holder saw exactly what a real confirmation looks like; the `broken_date` column is when the
market took out the interim low again. Counts: 2015: 0, 2018: 3, 2022: 1, 2026: 1 (so far).
The final confirmation of an episode is by definition never broken *within* the episode -- but
for the still-open 2026 episode even the current confirmation carries that same historic risk.

## Case A1: 2015-01-14 -- bear bottom, -61.1%

| stage | date | close | dd_ath | mvrv_z | fgi_value | real_yield | baa10y | net_liquidity |
|---|---|---|---|---|---|---|---|---|
| peak | 2014-09-17 | 457.33 | +0.0% | 0.46 | n/a | 0.48 | 2.30 | 4.23tn |
| bottom-90 | 2014-10-16 | 382.56 | -16.4% | 0.22 | n/a | 0.29 | 2.44 | 4.24tn |
| bottom-60 | 2014-11-15 | 376.13 | -17.8% | 0.26 | n/a | 0.43 | 2.48 | 4.28tn |
| bottom-30 | 2014-12-15 | 345.35 | -24.5% | 0.12 | n/a | 0.46 | 2.58 | 4.34tn |
| bottom-7 | 2015-01-07 | 294.34 | -35.6% | -0.13 | n/a | 0.41 | 2.52 | 4.16tn |
| bottom | 2015-01-14 | 178.10 | -61.1% | -0.40 | n/a | 0.37 | 2.55 | 4.22tn |
| confirm | 2015-01-22 | 233.41 | -49.0% | -0.36 | n/a | 0.26 | 2.59 | 4.19tn |
| last | 2026-10-02 | 84497.21 | -32.3% | 1.02 | 72.00 | 2.88 | 1.49 | 5.79tn |

| signal | peak | bottom-90 | bottom-60 | bottom-30 | bottom-7 | bottom | confirm | last |
|---|---|---|---|---|---|---|---|---|
| dd_ath | 0.00 | -0.16 | -0.18 | -0.24 | -0.36 | **-0.61** FIRE | -0.49 | -0.32 |
| days_since_ath | 0.00 | 29.00 | 59.00 | 89.00 | 112.00 | 119.00 | 127.00 | 361.00 |
| dd_90d | n/a (starts 2014-12-15) | n/a (starts 2014-12-15) | n/a (starts 2014-12-15) | -0.24 | **-0.31** FIRE | **-0.58** FIRE | **-0.45** FIRE | -0.02 |
| mayer_multiple | n/a (starts 2015-04-04) | n/a (starts 2015-04-04) | n/a (starts 2015-04-04) | n/a (starts 2015-04-04) | n/a (starts 2015-04-04) | n/a (starts 2015-04-04) | n/a (starts 2015-04-04) | 1.18 |
| close_vs_sma200w | n/a (starts 2018-07-17) | n/a (starts 2018-07-17) | n/a (starts 2018-07-17) | n/a (starts 2018-07-17) | n/a (starts 2018-07-17) | n/a (starts 2018-07-17) | n/a (starts 2018-07-17) | 1.28 |
| rsi_14 | n/a (starts 2014-10-01) | 35.25 | 50.75 | 38.73 | 41.26 | **19.61** FIRE | 42.80 | 62.92 |
| rsi_14w | n/a (starts 2014-12-28) | n/a (starts 2014-12-28) | n/a (starts 2014-12-28) | n/a (starts 2014-12-28) | **20.44** FIRE | **20.80** FIRE | **17.58** FIRE | 61.55 |
| vol_z_90 | n/a (starts 2014-12-15) | n/a (starts 2014-12-15) | n/a (starts 2014-12-15) | -0.47 | 0.40 | **5.33** FIRE | 0.68 | 1.57 |
| vol_ratio_90 | n/a (starts 2014-12-15) | n/a (starts 2014-12-15) | n/a (starts 2014-12-15) | 0.70 | 1.22 | 4.63 | 1.46 | 1.66 |
| capitulation_vol | n/a (starts 2014-09-20) | no | n/a (gap) | no | no | **yes** FIRE | no | no |
| vol_exhaustion | n/a (starts 2014-11-04) | n/a (starts 2014-11-04) | n/a (gap) | no | no | no | no | no |
| rvol_pct_2y | n/a (starts 2016-10-15) | n/a (starts 2016-10-15) | n/a (starts 2016-10-15) | n/a (starts 2016-10-15) | n/a (starts 2016-10-15) | n/a (starts 2016-10-15) | n/a (starts 2016-10-15) | 0.50 |
| rvol_compress_after_spike | n/a (starts 2016-11-16) | n/a (starts 2016-11-16) | n/a (starts 2016-11-16) | n/a (starts 2016-11-16) | n/a (starts 2016-11-16) | n/a (starts 2016-11-16) | n/a (starts 2016-11-16) | no |
| downstreak | n/a (starts 2014-09-18) | 2.00 | 3.00 | 1.00 | 0.00 | 2.00 | 0.00 | 1.00 |
| days_since_low_90 | n/a (starts 2014-12-17) | n/a (starts 2014-12-17) | n/a (starts 2014-12-17) | n/a (starts 2014-12-17) | 3.00 | 0.00 | 8.00 | **94.00** FIRE |
| fgi | n/a (starts 2018-02-01) | n/a (starts 2018-02-01) | n/a (starts 2018-02-01) | n/a (starts 2018-02-01) | n/a (starts 2018-02-01) | n/a (starts 2018-02-01) | n/a (starts 2018-02-01) | 72.00 |
| fgi_extreme_streak | n/a (starts 2018-02-01) | n/a (starts 2018-02-01) | n/a (starts 2018-02-01) | n/a (starts 2018-02-01) | n/a (starts 2018-02-01) | n/a (starts 2018-02-01) | n/a (starts 2018-02-01) | 0.00 |
| fgi_mean_30 | n/a (starts 2018-03-02) | n/a (starts 2018-03-02) | n/a (starts 2018-03-02) | n/a (starts 2018-03-02) | n/a (starts 2018-03-02) | n/a (starts 2018-03-02) | n/a (starts 2018-03-02) | 67.80 |
| washout_stabilise | n/a (starts 2014-12-17) | n/a (starts 2014-12-17) | n/a (starts 2014-12-17) | n/a (starts 2014-12-17) | no | no | no | no |

| condition | peak | bottom-90 | bottom-60 | bottom-30 | bottom-7 | bottom | confirm | last |
|---|---|---|---|---|---|---|---|---|
| M1_real_yield_easing | no | yes | no | no | yes | yes | yes | no |
| M2_dollar_easing | n/a | yes | no | no | no | no | no | no |
| M3a_vix_fade | no | no | no | no | no | no | no | no |
| M3b_credit_easing | no | no | no | no | yes | no | no | yes |
| M4_liquidity_up | n/a | n/a | n/a | yes | no | no | no | no |
| M5_valuation_low | no | no | no | no | yes | yes | yes | no |

False confirmations (0, events.false_confirms=0):

(none)


**What a person saw on that day.** The peak row is the first day of the data
(2014-09-17, censored: the true Dec-2013 high is outside the window, so the -61% is measured
from an in-window high). By 2015-01-14 price had been falling for four months; the daily RSI
printed 19.6 and the weekly 20.8, volume spiked to a 90-day z of +5.3 (the only cycle low of
the five where `capitulation_vol` fired on the day), and MVRV-Z reached -0.40. Fear & Greed did
not exist yet (series starts 2018-02), and Mayer/200-week columns need 1400 days of history.
Real yields were easing (M1 on) but credit was tightening (M3b off) and liquidity was flat-to-
down. Confirmation came just 8 days later (2015-01-22, $233) -- the fastest of the set -- and
no +30% bounce had been broken on the way in (0 false confirmations).

## Case A2: 2018-12-15 -- bear bottom, -83.4% (three traps)

| stage | date | close | dd_ath | mvrv_z | fgi_value | real_yield | baa10y | net_liquidity |
|---|---|---|---|---|---|---|---|---|
| peak | 2017-12-16 | 19497.40 | +0.0% | 8.43 | n/a | 0.47 | 1.80 | 4.30tn |
| bottom-90 | 2018-09-16 | 6517.18 | -66.6% | 0.50 | 28.00 | 0.89 | 1.88 | 3.91tn |
| bottom-60 | 2018-10-16 | 6596.11 | -66.2% | 0.49 | 24.00 | 1.03 | 1.89 | 3.85tn |
| bottom-30 | 2018-11-15 | 5648.03 | -71.0% | 0.22 | 28.00 | 1.12 | 2.09 | 3.82tn |
| bottom-7 | 2018-12-08 | 3476.11 | -82.2% | -0.45 | 11.00 | 0.96 | 2.31 | 3.74tn |
| bottom | 2018-12-15 | 3236.76 | -83.4% | -0.49 | 11.00 | 1.07 | 2.25 | 3.75tn |
| confirm | 2019-04-02 | 4879.88 | -75.0% | -0.07 | 60.00 | 0.59 | 2.24 | 3.64tn |
| last | 2026-10-02 | 84497.21 | -32.3% | 1.02 | 72.00 | 2.88 | 1.49 | 5.79tn |

| signal | peak | bottom-90 | bottom-60 | bottom-30 | bottom-7 | bottom | confirm | last |
|---|---|---|---|---|---|---|---|---|
| dd_ath | 0.00 | **-0.67** FIRE | **-0.66** FIRE | **-0.71** FIRE | **-0.82** FIRE | **-0.83** FIRE | **-0.75** FIRE | -0.32 |
| days_since_ath | 0.00 | 274.00 | 304.00 | 334.00 | 357.00 | 364.00 | **472.00** FIRE | 361.00 |
| dd_90d | 0.00 | -0.23 | -0.22 | -0.23 | **-0.48** FIRE | **-0.52** FIRE | 0.00 | -0.02 |
| mayer_multiple | 3.74 | 0.86 | 0.91 | 0.81 | **0.54** FIRE | **0.51** FIRE | 1.04 | 1.18 |
| close_vs_sma200w | n/a (starts 2018-07-17) | 2.29 | 2.22 | 1.82 | 1.10 | 1.02 | 1.41 | 1.28 |
| rsi_14 | 77.51 | 45.59 | 53.28 | **18.03** FIRE | **26.87** FIRE | **27.17** FIRE | 87.34 | 62.92 |
| rsi_14w | 87.53 | 45.27 | 44.05 | 45.03 | **32.70** FIRE | **30.37** FIRE | 42.87 | 61.55 |
| vol_z_90 | 1.90 | -1.33 | -0.33 | **3.48** FIRE | 0.63 | -0.92 | **5.39** FIRE | 1.57 |
| vol_ratio_90 | 2.81 | 0.76 | 0.94 | 1.70 | 1.16 | 0.77 | 2.80 | 1.66 |
| capitulation_vol | no | no | no | no | no | no | no | no |
| vol_exhaustion | no | no | no | no | no | no | no | no |
| rvol_pct_2y | 0.97 | **0.20** FIRE | **0.09** FIRE | **0.12** FIRE | 0.75 | 0.74 | **0.29** FIRE | 0.50 |
| rvol_compress_after_spike | no | no | no | no | no | no | no | no |
| downstreak | 0.00 | 1.00 | 1.00 | **4.00** FIRE | 0.00 | 3.00 | 0.00 | 1.00 |
| days_since_low_90 | **845.00** FIRE | **80.00** FIRE | **110.00** FIRE | 0.00 | 1.00 | 0.00 | **108.00** FIRE | **94.00** FIRE |
| fgi | n/a (starts 2018-02-01) | 28.00 | **24.00** FIRE | 28.00 | **11.00** FIRE | **11.00** FIRE | 60.00 | 72.00 |
| fgi_extreme_streak | n/a (starts 2018-02-01) | 0.00 | **6.00** FIRE | 0.00 | **19.00** FIRE | **26.00** FIRE | 0.00 | 0.00 |
| fgi_mean_30 | n/a (starts 2018-03-02) | **19.83** FIRE | 29.90 | 35.70 | **23.83** FIRE | **15.80** FIRE | 52.23 | 67.80 |
| washout_stabilise | n/a (gap) | **yes** FIRE | **yes** FIRE | no | no | no | no | no |

| condition | peak | bottom-90 | bottom-60 | bottom-30 | bottom-7 | bottom | confirm | last |
|---|---|---|---|---|---|---|---|---|
| M1_real_yield_easing | yes | no | no | no | yes | yes | yes | no |
| M2_dollar_easing | no | yes | no | no | no | no | no | no |
| M3a_vix_fade | no | no | no | no | no | no | no | no |
| M3b_credit_easing | yes | yes | no | no | no | no | yes | yes |
| M4_liquidity_up | yes | no | no | no | no | no | no | no |
| M5_valuation_low | no | no | no | no | yes | yes | yes | no |

False confirmations (3, events.false_confirms=3):

| low_date | low_close | confirm_date | confirm_close | broken_date | broken_close |
|---|---|---|---|---|---|
| 2018-02-05 | 6,955 | 2018-02-14 | 9,495 | 2018-03-30 | 6,891 |
| 2018-04-06 | 6,636 | 2018-04-20 | 8,846 | 2018-06-12 | 6,582 |
| 2018-06-28 | 5,903 | 2018-07-23 | 7,711 | 2018-11-14 | 5,738 |


**What a person saw on that day.** A year of decline with three separate
"+30% off the low" rallies that all failed (the three traps below: February, April and July
2018). On 2018-12-15 itself: -83.4% from the 2017 peak, MVRV-Z -0.49, Fear & Greed 11, RSI deep
oversold, Mayer multiple far below 1. Real yields had *risen* through the year (0.47 at the peak
to 1.07 at the low) with only the 21-day change briefly easing (M1 on at the low); credit spreads
were wide (M3b off). Confirmation took 108 days (2019-04-02, $4,880) -- the slowest of the set,
and anyone who treated the February/April/July bounces as confirmations was stopped out three
times first.

## Case B: 2021-07-20 -- deep correction, -53.1% (set B, separate)

| stage | date | close | dd_ath | mvrv_z | fgi_value | real_yield | baa10y | net_liquidity |
|---|---|---|---|---|---|---|---|---|
| peak | 2021-04-13 | 63503.46 | +0.0% | 5.00 | 74.00 | -0.64 | 1.95 | 6.67tn |
| bottom-90 | 2021-04-21 | 53906.09 | -15.1% | 4.31 | 73.00 | -0.74 | 2.00 | 6.80tn |
| bottom-60 | 2021-05-21 | 37304.69 | -41.3% | 2.18 | 19.00 | -0.78 | 2.02 | 6.71tn |
| bottom-30 | 2021-06-20 | 35698.30 | -43.8% | 1.59 | 21.00 | -0.79 | 1.85 | 6.66tn |
| bottom-7 | 2021-07-13 | 32702.03 | -48.5% | 1.36 | 20.00 | -0.95 | 1.91 | 6.57tn |
| bottom | 2021-07-20 | 29807.35 | -53.1% | 1.13 | 19.00 | -1.05 | 1.97 | 6.64tn |
| confirm | 2021-07-27 | 39406.94 | -37.9% | 1.76 | 32.00 | -1.11 | 1.94 | 6.67tn |
| last | 2026-10-02 | 84497.21 | -32.3% | 1.02 | 72.00 | 2.88 | 1.49 | 5.79tn |

| signal | peak | bottom-90 | bottom-60 | bottom-30 | bottom-7 | bottom | confirm | last |
|---|---|---|---|---|---|---|---|---|
| dd_ath | 0.00 | -0.15 | -0.41 | -0.44 | -0.49 | **-0.53** FIRE | -0.38 | -0.32 |
| days_since_ath | 0.00 | 8.00 | 38.00 | 68.00 | 91.00 | 98.00 | 105.00 | 361.00 |
| dd_90d | 0.00 | -0.15 | **-0.41** FIRE | **-0.44** FIRE | **-0.48** FIRE | **-0.49** FIRE | **-0.33** FIRE | -0.02 |
| mayer_multiple | 1.97 | 1.58 | 0.93 | 0.83 | **0.73** FIRE | **0.67** FIRE | 0.88 | 1.18 |
| close_vs_sma200w | 5.69 | 4.70 | 2.98 | 2.69 | 2.38 | 2.15 | 2.81 | 1.28 |
| rsi_14 | 67.14 | 38.73 | **29.18** FIRE | 42.51 | 42.78 | 34.05 | 69.26 | 62.92 |
| rsi_14w | 72.96 | 67.30 | 52.93 | 45.32 | 44.22 | 42.03 | 46.20 | 61.55 |
| vol_z_90 | 0.14 | -0.33 | 0.52 | -1.19 | -1.57 | -1.16 | -0.45 | 1.57 |
| vol_ratio_90 | 1.07 | 0.83 | 1.27 | 0.64 | **0.38** FIRE | **0.50** FIRE | 0.80 | 1.66 |
| capitulation_vol | no | no | no | no | no | no | no | no |
| vol_exhaustion | no | no | no | no | **yes** FIRE | **yes** FIRE | no | no |
| rvol_pct_2y | 0.40 | 0.44 | 0.93 | 0.80 | 0.72 | 0.70 | 0.47 | 0.50 |
| rvol_compress_after_spike | no | no | no | no | no | no | no | no |
| downstreak | 0.00 | 1.00 | 1.00 | 0.00 | 2.00 | 2.00 | 0.00 | 1.00 |
| days_since_low_90 | **397.00** FIRE | **405.00** FIRE | 2.00 | 12.00 | 18.00 | 0.00 | 7.00 | **94.00** FIRE |
| fgi | 74.00 | 73.00 | **19.00** FIRE | **21.00** FIRE | **20.00** FIRE | **19.00** FIRE | 32.00 | 72.00 |
| fgi_extreme_streak | 0.00 | 0.00 | **4.00** FIRE | **3.00** FIRE | **6.00** FIRE | **13.00** FIRE | 0.00 | 0.00 |
| fgi_mean_30 | 71.10 | 72.03 | 47.10 | **21.27** FIRE | **23.73** FIRE | **21.93** FIRE | **22.70** FIRE | 67.80 |
| washout_stabilise | no | no | no | no | no | no | no | no |

| condition | peak | bottom-90 | bottom-60 | bottom-30 | bottom-7 | bottom | confirm | last |
|---|---|---|---|---|---|---|---|---|
| M1_real_yield_easing | no | yes | yes | no | yes | yes | yes | no |
| M2_dollar_easing | yes | yes | yes | no | no | no | yes | no |
| M3a_vix_fade | yes | no | yes | no | no | no | yes | no |
| M3b_credit_easing | yes | yes | no | yes | no | no | no | yes |
| M4_liquidity_up | yes | yes | yes | no | no | no | yes | no |
| M5_valuation_low | no | no | no | no | no | no | no | no |

False confirmations (0, events.false_confirms=0):

(none)


**What a person saw on that day.** A mid-bull correction, not a bear market:
-53.1% in three months, then a V. At the low MVRV-Z was still +1.13 (M5 never came on in this
episode -- valuation by the classic yardstick was not "low"), Fear & Greed 19, RSI oversold,
Mayer below 0.8. The macro regime was the mirror image of 2026: real yields *negative* (-1.05%),
liquidity expanding (M4 on into May). Confirmation came in 7 days (2021-07-27) and no bounce was
broken on the way down (0 false confirmations). This is set B -- reported separately, never
pooled with the bear bottoms.

## Case A3: 2022-11-21 -- bear bottom, -76.6% (one trap)

| stage | date | close | dd_ath | mvrv_z | fgi_value | real_yield | baa10y | net_liquidity |
|---|---|---|---|---|---|---|---|---|
| peak | 2021-11-08 | 67566.83 | +0.0% | 3.19 | 75.00 | -1.09 | 1.73 | 6.94tn |
| bottom-90 | 2022-08-23 | 21528.09 | -68.1% | -0.03 | 28.00 | 0.46 | 2.24 | 6.07tn |
| bottom-60 | 2022-09-22 | 19413.55 | -71.3% | -0.20 | 22.00 | 1.13 | 2.12 | 5.92tn |
| bottom-30 | 2022-10-22 | 19208.19 | -71.6% | -0.14 | 20.00 | 1.69 | 2.36 | 5.87tn |
| bottom-7 | 2022-11-14 | 16618.20 | -75.4% | -0.31 | 24.00 | 1.43 | 2.36 | 5.95tn |
| bottom | 2022-11-21 | 15787.28 | -76.6% | -0.29 | 21.00 | 1.57 | 2.13 | 6.01tn |
| confirm | 2023-01-14 | 20976.30 | -69.0% | 0.01 | 46.00 | 1.31 | 1.95 | 5.96tn |
| last | 2026-10-02 | 84497.21 | -32.3% | 1.02 | 72.00 | 2.88 | 1.49 | 5.79tn |

| signal | peak | bottom-90 | bottom-60 | bottom-30 | bottom-7 | bottom | confirm | last |
|---|---|---|---|---|---|---|---|---|
| dd_ath | 0.00 | **-0.68** FIRE | **-0.71** FIRE | **-0.72** FIRE | **-0.75** FIRE | **-0.77** FIRE | **-0.69** FIRE | -0.32 |
| days_since_ath | 0.00 | 288.00 | 318.00 | 348.00 | **371.00** FIRE | **378.00** FIRE | **432.00** FIRE | 361.00 |
| dd_90d | 0.00 | **-0.32** FIRE | -0.21 | -0.21 | **-0.29** FIRE | **-0.29** FIRE | -0.01 | -0.02 |
| mayer_multiple | 1.48 | **0.67** FIRE | **0.67** FIRE | **0.75** FIRE | **0.72** FIRE | **0.71** FIRE | 1.07 | 1.18 |
| close_vs_sma200w | 3.96 | **0.93** FIRE | **0.83** FIRE | **0.81** FIRE | **0.69** FIRE | **0.66** FIRE | **0.86** FIRE | 1.28 |
| rsi_14 | 68.10 | 39.69 | 43.98 | 46.61 | 35.22 | 31.40 | 89.35 | 62.92 |
| rsi_14w | 67.21 | **33.69** FIRE | **33.69** FIRE | **34.45** FIRE | **31.49** FIRE | **31.39** FIRE | **35.86** FIRE | 61.55 |
| vol_z_90 | 0.82 | 0.23 | 1.32 | -1.73 | 0.76 | 0.02 | 0.57 | 1.57 |
| vol_ratio_90 | 1.15 | 1.07 | 1.35 | **0.51** FIRE | 1.33 | 1.01 | 1.38 | 1.66 |
| capitulation_vol | no | no | no | no | no | no | no | no |
| vol_exhaustion | no | no | no | **yes** FIRE | no | no | no | no |
| rvol_pct_2y | 0.41 | **0.32** FIRE | 0.55 | **0.00** FIRE | 0.76 | 0.77 | **0.08** FIRE | 0.50 |
| rvol_compress_after_spike | no | no | no | no | no | no | no | no |
| downstreak | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 2.00 | 0.00 | 1.00 |
| days_since_low_90 | **111.00** FIRE | **66.00** FIRE | 1.00 | **31.00** FIRE | 5.00 | 0.00 | **54.00** FIRE | **94.00** FIRE |
| fgi | 75.00 | 28.00 | **22.00** FIRE | **20.00** FIRE | **24.00** FIRE | **21.00** FIRE | 46.00 | 72.00 |
| fgi_extreme_streak | 0.00 | 0.00 | **4.00** FIRE | **16.00** FIRE | **5.00** FIRE | **12.00** FIRE | 0.00 | 0.00 |
| fgi_mean_30 | 74.03 | 34.70 | **24.33** FIRE | **22.30** FIRE | 27.30 | 27.33 | 28.03 | 67.80 |
| washout_stabilise | no | no | no | no | no | no | no | no |

| condition | peak | bottom-90 | bottom-60 | bottom-30 | bottom-7 | bottom | confirm | last |
|---|---|---|---|---|---|---|---|---|
| M1_real_yield_easing | yes | no | no | no | yes | no | yes | no |
| M2_dollar_easing | no | no | no | yes | yes | yes | yes | no |
| M3a_vix_fade | no | no | no | no | yes | no | no | no |
| M3b_credit_easing | yes | yes | yes | no | no | yes | yes | yes |
| M4_liquidity_up | no | yes | no | no | no | no | yes | no |
| M5_valuation_low | no | yes | yes | yes | yes | yes | no | no |

False confirmations (1, events.false_confirms=1):

| low_date | low_close | confirm_date | confirm_close | broken_date | broken_close |
|---|---|---|---|---|---|
| 2022-01-22 | 35,030 | 2022-03-27 | 46,820 | 2022-05-08 | 34,059 |


**What a person saw on that day.** One prior trap: the March 2022 bounce off
the January low ($35,030 -> $46,820, +34%) broke in May (Terra) and the market ground to a final
low of $15,787 (-76.6%). At the low: MVRV-Z -0.29, Fear & Greed 21, RSI oversold, Mayer low, and
the valuation cluster (M5) had been on since August. Real yields were 1.57% -- up ~2.7pp from
the negative levels of 2021 -- but their 21-day change had turned down (M1 on). Credit conditions
were mixed. Confirmation took 54 days (2023-01-14, $20,976).

## Case P: 2026-06-30 -- deep correction, -53.1%, PROVISIONAL (one trap)

| stage | date | close | dd_ath | mvrv_z | fgi_value | real_yield | baa10y | net_liquidity |
|---|---|---|---|---|---|---|---|---|
| peak | 2025-10-06 | 124752.53 | +0.0% | 2.49 | 71.00 | 1.80 | 1.66 | 5.76tn |
| bottom-90 | 2026-04-01 | 68078.55 | -45.4% | 0.47 | 8.00 | 2.00 | 1.79 | 5.77tn |
| bottom-60 | 2026-05-01 | 78179.00 | -37.3% | 0.74 | 26.00 | 1.94 | 1.70 | 5.71tn |
| bottom-30 | 2026-05-31 | 73579.69 | -41.0% | 0.65 | 28.00 | 2.07 | 1.57 | 5.86tn |
| bottom-7 | 2026-06-23 | 62668.02 | -49.8% | 0.35 | 23.00 | 2.28 | 1.51 | 5.85tn |
| bottom | 2026-06-30 | 58558.86 | -53.1% | 0.23 | 15.00 | 2.16 | 1.55 | 5.81tn |
| confirm | 2026-08-21 | 78335.19 | -37.2% | 0.67 | 72.00 | 2.35 | 1.64 | 5.79tn |
| last | 2026-10-02 | 84497.21 | -32.3% | 1.02 | 72.00 | 2.88 | 1.49 | 5.79tn |

| signal | peak | bottom-90 | bottom-60 | bottom-30 | bottom-7 | bottom | confirm | last |
|---|---|---|---|---|---|---|---|---|
| dd_ath | 0.00 | -0.45 | -0.37 | -0.41 | -0.50 | **-0.53** FIRE | -0.37 | -0.32 |
| days_since_ath | 0.00 | 177.00 | 207.00 | 237.00 | 260.00 | 267.00 | 319.00 | 361.00 |
| dd_90d | 0.00 | **-0.30** FIRE | -0.01 | -0.10 | -0.24 | **-0.29** FIRE | 0.00 | -0.02 |
| mayer_multiple | 1.18 | **0.75** FIRE | 0.93 | 0.93 | 0.82 | **0.78** FIRE | 1.14 | 1.18 |
| close_vs_sma200w | 2.33 | 1.15 | 1.29 | 1.19 | 1.01 | **0.94** FIRE | 1.22 | 1.28 |
| rsi_14 | 72.75 | 46.82 | 60.93 | 36.72 | 37.29 | **29.99** FIRE | 86.00 | 62.92 |
| rsi_14w | 64.17 | **31.90** FIRE | 47.32 | 42.46 | **35.53** FIRE | **32.94** FIRE | **38.80** FIRE | 61.55 |
| vol_z_90 | 0.46 | -0.42 | -0.18 | -1.59 | -0.34 | -0.03 | **3.73** FIRE | 1.57 |
| vol_ratio_90 | 1.16 | 0.83 | 0.93 | **0.49** FIRE | 0.89 | 0.99 | 2.65 | 1.66 |
| capitulation_vol | no | no | no | no | no | no | no | no |
| vol_exhaustion | no | no | no | **yes** FIRE | no | no | no | no |
| rvol_pct_2y | **0.07** FIRE | 0.58 | **0.31** FIRE | **0.02** FIRE | 0.51 | 0.56 | 0.60 | 0.50 |
| rvol_compress_after_spike | no | no | **yes** FIRE | **yes** FIRE | no | no | no | no |
| downstreak | 0.00 | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 |
| days_since_low_90 | **181.00** FIRE | **55.00** FIRE | **85.00** FIRE | **115.00** FIRE | 17.00 | 0.00 | **52.00** FIRE | **94.00** FIRE |
| fgi | 71.00 | **8.00** FIRE | 26.00 | 28.00 | **23.00** FIRE | **15.00** FIRE | 72.00 | 72.00 |
| fgi_extreme_streak | 0.00 | **14.00** FIRE | 0.00 | 0.00 | **22.00** FIRE | **29.00** FIRE | 0.00 | 0.00 |
| fgi_mean_30 | 51.20 | **14.17** FIRE | **23.43** FIRE | 34.70 | **18.70** FIRE | **15.93** FIRE | 32.20 | 67.80 |
| washout_stabilise | no | **yes** FIRE | no | no | **yes** FIRE | no | no | no |

| condition | peak | bottom-90 | bottom-60 | bottom-30 | bottom-7 | bottom | confirm | last |
|---|---|---|---|---|---|---|---|---|
| M1_real_yield_easing | no | no | yes | no | no | yes | yes | no |
| M2_dollar_easing | no | no | yes | no | no | no | yes | no |
| M3a_vix_fade | no | no | no | no | yes | yes | no | no |
| M3b_credit_easing | yes | no | yes | yes | yes | no | no | yes |
| M4_liquidity_up | no | yes | no | yes | no | yes | no | no |
| M5_valuation_low | no | no | no | no | no | no | no | no |

False confirmations (1, events.false_confirms=1):

| low_date | low_close | confirm_date | confirm_close | broken_date | broken_close |
|---|---|---|---|---|---|
| 2026-02-05 | 62,702 | 2026-05-10 | 82,139 | 2026-06-05 | 60,923 |

Live view for the provisional episode (the 2026 question, as a case file):

| signal | firing at bottom | first fire at/after bottom | close that day | firing at last row |
|---|---|---|---|---|
| dd_ath | yes | 2026-06-30 | 58,559 | no |
| days_since_ath | no | never | - | no |
| dd_90d | yes | 2026-06-30 | 58,559 | no |
| mayer_multiple | yes | 2026-06-30 | 58,559 | no |
| close_vs_sma200w | yes | 2026-06-30 | 58,559 | no |
| rsi_14 | yes | 2026-06-30 | 58,559 | no |
| rsi_14w | yes | 2026-06-30 | 58,559 | no |
| vol_z_90 | no | 2026-08-20 | 73,033 | no |
| vol_ratio_90 | no | 2026-07-04 | 63,088 | no |
| capitulation_vol | no | never | - | no |
| vol_exhaustion | no | 2026-07-04 | 63,088 | no |
| rvol_pct_2y | no | 2026-07-03 | 62,544 | no |
| rvol_compress_after_spike | no | never | - | no |
| downstreak | no | 2026-08-12 | 63,402 | no |
| days_since_low_90 | no | 2026-07-21 | 66,505 | yes |
| fgi | yes | 2026-06-30 | 58,559 | no |
| fgi_extreme_streak | yes | 2026-06-30 | 58,559 | no |
| fgi_mean_30 | yes | 2026-06-30 | 58,559 | no |
| washout_stabilise | no | 2026-07-10 | 64,127 | no |


**What a person saw on that day.** The episode the owner lived. One prior
trap: the +31% bounce off the February low confirmed on 2026-05-10 at $82,139 and broke on
2026-06-05 at $60,923, three weeks before the actual low. On 2026-06-30 itself ($58,559,
-53.1%): nine of nineteen signals were already firing -- the full "value + fear" cluster
(drawdown from ATH, 90-day drawdown, Mayer 0.78, 200-week ratio 0.94, daily RSI 30.0, weekly
RSI 32.9, Fear & Greed 15, a 29-day extreme-fear streak, 30-day mean fear 15.9). What was *not*
on: MVRV-Z stood at +0.23 (M5 off -- the classic "cheap" yardstick never triggered; see the
standing limit on MVRV-Z amplitude decay), no capitulation volume, no washout-stabilise pattern
yet. Real yields were 2.16%, up from 1.80% at the peak (M1 was on only as a 21-day dip inside a
rising trend). Confirmation came 52 days later (2026-08-21, $78,335). **The low is still
provisional**: no new all-time high has been made; the episode can still make a lower low and
the numbers above can still move.

## The current reading (as of 2026-10-02)

Descriptive reading of the last frame row. This is a description of the present, **not a forecast** and not a signal to act on.

Signals on: **1 of 19**; macro conditions on: **1 of 6**.

| what | on | days_on | value |
|---|---|---|---|
| signal dd_ath | no | 0 | -0.32 |
| signal days_since_ath | no | 0 | 361.00 |
| signal dd_90d | no | 0 | -0.02 |
| signal mayer_multiple | no | 0 | 1.18 |
| signal close_vs_sma200w | no | 0 | 1.28 |
| signal rsi_14 | no | 0 | 62.92 |
| signal rsi_14w | no | 0 | 61.55 |
| signal vol_z_90 | no | 0 | 1.57 |
| signal vol_ratio_90 | no | 0 | 1.66 |
| signal capitulation_vol | no | 0 | no |
| signal vol_exhaustion | no | 0 | no |
| signal rvol_pct_2y | no | 0 | 0.50 |
| signal rvol_compress_after_spike | no | 0 | no |
| signal downstreak | no | 0 | 1.00 |
| signal days_since_low_90 | yes | 74 | 94.00 |
| signal fgi | no | 0 | 72.00 |
| signal fgi_extreme_streak | no | 0 | 0.00 |
| signal fgi_mean_30 | no | 0 | 67.80 |
| signal washout_stabilise | no | 0 | no |
| M1_real_yield_easing | no | 0 | no |
| M2_dollar_easing | no | 0 | no |
| M3a_vix_fade | no | 0 | no |
| M3b_credit_easing | yes | 38 | yes |
| M4_liquidity_up | no | 0 | no |
| M5_valuation_low | no | 0 | no |


**Reading it plainly.** Of the 19 registry signals only `days_since_low_90` is on
(74 days): price has been rising off a 90-day low for ~11 weeks and nothing in the
bottom-detection cluster is firing -- the market is neither at a drawdown nor in fear (Fear &
Greed 72, MVRV-Z +1.02, Mayer 1.18). Of the six macro conditions only M3b (credit easing,
38 days) is on. Two things deserve attention as *context*:

- **Real yields are rising again.** The 10-year real yield closed at 2.88%, +0.62pp over the
  last 13 weeks (91 days) and +0.47pp over 9 weeks. The standing risk flag from
  `docs/agent-tasks/PICKUP.md` applies verbatim: *after 13-week real-yield surges of 50bp or
  more, the next 13 weeks of BTC were weaker (n small, overlapping), and that is the bucket we
  are in now.* M1 (real-yield easing) is off.
- **The 2026 episode is unresolved.** The June low is confirmed by the +30% rule but the episode
  has not recovered to a new high; a re-fall below $58,559 would reopen it (see the
  false-confirm table above: the May confirmation looked exactly like this one does now).


## What this part cannot tell us

Case files describe single days; they cannot say how *often* a configuration precedes a bottom
(that is Q1's job, and even there set A has n = 3). They cannot separate a 2021-style correction
from a 2022-style bear in real time -- on the day, 2021-07-20 and 2022-11-21 look similar
(oversold, fearful, Mayer low); what differed (MVRV-Z +1.13 vs -0.29, real yields -1.05% vs
+1.57%) is visible here only with hindsight about which mattered. The current reading says what
is on, not what happens next. No trading costs, sizing or execution are modelled anywhere.
