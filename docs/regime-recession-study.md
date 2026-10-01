# RECESSION label against NBER dates

Measured 2026-10-01 with `scripts/recession_label_study.py`. The classifier is unchanged.

The question was whether `RECESSION` being the dominant regime on about 20% of days since 1990 is a real over-run of the NBER recession dates (about 8% of the same span, about 36 of about 440 months), and which part of the rule causes it. Both figures are real. The rule was left as it is: the extra days are the Sahm flag tracking unemployment after the NBER trough, plus one industrial-production stretch in 2019. Shortening the flag to match the NBER months would be fitting those dates.

## How it was measured

Factors are loaded from 1979-01-04 through 2026-10-01, which is 1990-01-01 minus `RulesBasedClassifier.LOOKBACK_DAYS` (4015). That is the same pad the regime endpoints and the CLI use. The tape is `generate_regime_tape(factor_df, include_scores=True)`.

The scored sample is every day from 1990-01-01 through the last NBER print that has a value. `USRECD` (daily, 7-day) is the NBER series. It matches `USREC` (monthly) in all 464 overlapping months. `USRECD` runs through 2026-09-29, so two later tape days are not scored. Unemployment and the IPMAN proxy are present on every scored day. On every Sahm-on day the `RECESSION` score is exactly 1.0.

This is agreement with the final NBER dates, on today's vintage of `UNRATE`. It is not a real-time hit rate. NBER announces peaks and troughs long after the fact. Sahm is a concurrent labor-market rule, so it lags the start and it stays on while unemployment is elevated.

`USREC` / `USRECD` start the month after the peak ("the period following the peak through the trough"). `USRECM` includes the peak month. Since 1990 that adds exactly four months: 1990-07, 2001-03, 2007-12, 2020-02 (40 months instead of 36). The tables below use `USRECD`.

## Headline

13,421 scored days, 1990-01-01 through 2026-09-29.

| | share of days |
|---|---:|
| NBER recession (`USRECD` = 1) | 8.16% |
| `RECESSION` dominant | 20.57% |
| Sahm flag on | 18.37% |
| IPMAN-fallback score > 0.5 | 7.91% |

Dominant-regime mix on those days: `RISK_ON` 73.94%, `RECESSION` 20.57%, `INFLATION_ACCEL` 4.03%, `REAL_YIELD_SHOCK` 1.20%, `DEFLATION_SCARE` 0.26%.

Monthly, which is the unit NBER actually dates: 440 months, NBER on in 8.18% (36 months), the label dominant on a majority of days in 20.68% (91 months). Same conclusion as the daily count.

## Agreement

A day is a positive when that predictor is on. Truth is `USRECD`.

| predictor | share | precision | recall | F1 | tp | fp | fn |
|---|---:|---:|---:|---:|---:|---:|---:|
| `RECESSION` dominant | 20.57% | 0.327 | 0.826 | 0.469 | 904 | 1857 | 191 |
| Sahm flag alone | 18.37% | 0.357 | 0.805 | 0.495 | 881 | 1585 | 214 |
| IPMAN-fallback score > 0.5 | 7.91% | 0.313 | 0.303 | 0.308 | 332 | 729 | 763 |
| fallback > 0.5 and Sahm off | 2.27% | 0.102 | 0.028 | 0.044 | 31 | 274 | 1064 |

The last row is the branch the classifier actually uses. When Sahm is on, the score is forced to 1.0 and the fallback is ignored. The column is named `ism_pmi`; the series behind it is `IPMAN`, industrial production in manufacturing. FRED no longer carries the ISM PMI survey.

Monthly majority-of-days label against `USREC`: precision 0.330, recall 0.833, F1 0.472 (30 hit months, 61 false-positive months, 6 missed months).

Sahm alone has a slightly higher F1 than the dominant label. The fallback, on the days it is actually consulted, barely matches NBER (precision 0.10, recall 0.03).

## Episodes in `USRECD`

| NBER (from the series) | days | label turns on | onset | overhang | share of episode labeled | Sahm share of those on-days |
|---|---:|---|---:|---:|---:|---:|
| 1990-08-01 .. 1991-03-31 | 243 | 1990-10-01 | +61d | 580d | 74.90% | 1.00 |
| 2001-04-01 .. 2001-11-30 | 244 | 2001-07-01 | +91d | 304d | 62.70% | 1.00 |
| 2008-01-01 .. 2009-06-30 | 547 | 2008-02-01 | +31d | 335d | 94.33% | 1.00 |
| 2020-03-01 .. 2020-04-30 | 61 | 2020-03-01 | +0d | 304d | 86.89% | 0.57 |

Onset is the first day of the `RECESSION`-dominant spell minus the NBER start. Positive means the label lagged. Overhang is how many days that spell continues after the NBER end. None of the tails were still running at the sample end.

The six missed months are the onset lags: August–September 1990, April–June 2001, and January 2008. March 2020 was labeled. Sahm was off on every missed day. Eight of those days had a fallback score above 0.5 and still lost to another regime.

Unemployment around the same episodes (the monthly rate the factor frame fed the classifier):

| episode | U at start | U at end | U peak | peak month | Sahm on | Sahm off |
|---|---:|---:|---:|---|---|---|
| 1990-08 .. 1991-03 | 5.7 | 6.8 | 7.8 | 1992-06 | 1990-10 | 1992-10 |
| 2001-04 .. 2001-11 | 4.4 | 5.5 | 6.3 | 2003-06 | 2001-07 | 2002-09 |
| 2008-01 .. 2009-06 | 5.0 | 9.5 | 10.0 | 2009-10 | 2008-02 | 2010-05 |
| 2020-03 .. 2020-04 | 4.4 | 14.8 | 14.8 | 2020-04 | 2020-04 | 2021-02 |

The post-trough label days, split at the unemployment peak (the peak month still counts as "rising"; "after" starts the next month):

| NBER end | tail days | while unemployment was still rising | after the unemployment peak |
|---|---:|---:|---:|
| 1991-03-31 | 580 | 457 | 123 |
| 2001-11-30 | 304 | 304 | 0 |
| 2009-06-30 | 335 | 123 | 212 |
| 2020-04-30 | 304 | 0 | 304 |

The 2001 tail ended in September 2002, nine months before unemployment peaked in June 2003. The 1990 and 2008 tails outlast the peak by about four and seven months, which is the 12-month window rolling forward. The 2020 peak is the trough month itself (the spike was the recession), so the whole 304-day tail is after the peak: unemployment fell from 14.8 and the 3-month average stayed more than 0.5pp above the low in its window until February 2021.

## False-positive runs

Nine runs, 1,857 days. No isolated run was shorter than 14 days.

| start | end | days | Sahm | fallback | what it is | median fallback |
|---|---|---:|---:|---:|---|---:|
| 1991-04-01 | 1992-10-31 | 580 | 580 | 0 | overhang after 1990-91 | |
| 2001-12-01 | 2002-09-30 | 304 | 304 | 0 | overhang after 2001 | |
| 2003-08-01 | 2003-08-31 | 31 | 31 | 0 | isolated Sahm month | |
| 2009-07-01 | 2010-05-31 | 335 | 335 | 0 | overhang after 2008-09 | |
| 2019-04-01 | 2019-05-31 | 61 | 0 | 61 | IPMAN fallback | 0.57 |
| 2019-07-01 | 2019-07-31 | 31 | 0 | 31 | IPMAN fallback | 0.68 |
| 2019-09-01 | 2020-02-27 | 180 | 0 | 180 | IPMAN fallback | 0.71 |
| 2020-05-01 | 2021-02-28 | 304 | 304 | 0 | overhang after 2020 | |
| 2024-08-01 | 2024-08-31 | 31 | 31 | 0 | isolated Sahm month | |

Of the 2,761 days the label is dominant, 2,466 are Sahm and 295 are the fallback. Of the 1,857 false-positive days, 1,585 are Sahm and 272 are the fallback. The fallback's 23 hit days are what made March 2020 on time: during the two NBER months of 2020, only 57% of the labeled days were Sahm (Sahm turns on in April).

There is no third component. A `RECESSION` score has to clear 0.5 before it can beat `RISK_ON`, because `RISK_ON` is `1 - max(other scores)` and a tie goes to the earlier column. Every dominant day is either Sahm (score 1.0) or a fallback score above 0.5 that also beat the other stress regimes.

## Sahm against the published FRED rule

The code computes, on monthly `UNRATE`,

```
3-month average − minimum of that average over a 12-observation window that includes the current month
```

and flags a month at ≥ 0.50. That is `MacroFactorProvider._compute_sahm`. The value rebuilt from the daily forward-filled frame matches the value rebuilt from raw monthly `UNRATE` within 0.07pp (max absolute gap 0.0667), and the two produce the same flag disagreements against FRED.

`SAHMCURRENT` is the same rule on the current vintage, with the minimum taken over the previous 12 averages excluding the current month. Rounded to FRED's published 0.01, that version's flag matches `SAHMCURRENT` in every month since 1990 (correlation 0.9988). The largest level gap is September 2021, where the code's non-negative clip is 0 and FRED prints −0.40. Negatives are below the 0.50 flag and do not move it.

The code's shorter window, rounded the same way, differs from `SAHMCURRENT` in 5 of 440 months. In each of those months the published indicator is on and the code is off:

| month | code | SAHMCURRENT |
|---|---:|---:|
| 2002-10 | 0.43 | 0.63 |
| 2002-11 | 0.27 | 0.50 |
| 2021-03 | 0.00 | 2.40 |
| 2024-07 | 0.47 | 0.50 |
| 2024-09 | 0.43 | 0.53 |

March 2021 is the cliff: the previous-12 window still contains the pre-COVID low (FRED 2.40), and the code's window, which includes the current month, has already let that low roll off (0). Every month the code flags, `SAHMCURRENT` flags too. Moving to the published window would add flagged months, including July and September 2024, and the share of days labeled `RECESSION` would go up.

`SAHMREALTIME` uses the unemployment rate as it was first printed. Ten months since 1990 disagree at the 0.01 flag, some in each direction (the code, on current vintage, turns on in October 1990 and February–March 2008 while the real-time indicator is still under 0.50). That gap is the vintage, which the comparison was supposed to show.

## Verdict

The label does spend about 20% of days as the dominant regime, and NBER recession days are about 8%. Precision is 0.33 and recall is 0.83.

About 1,523 of the 1,857 false-positive days are one uninterrupted Sahm spell after each of the four troughs. 884 of those are months in which unemployment was still rising after the trough (the 1990 peak was 15 months later, the 2001 peak 19 months later, the 2008 peak 4 months later). 639 are after that peak, almost half of them the 2020 spike, whose peak and trough are the same month. Another 62 days are two isolated Sahm months (August 2003 and August 2024). The remaining 272 days are the IPMAN fallback from April 2019 through February 2020, median score 0.57 to 0.71, which is the 2019 manufacturing slowdown and not an NBER recession.

That split is the rule working as written:

- The post-trough Sahm spell follows the labor market. Unemployment peaked 15, 19, and 4 months after the 1990, 2001, and 2008 troughs. The label stays a statement about unemployment.
- The published Sahm window is one month longer than the code, and the code is the quieter of the two. Adopting the published window adds months.
- The IPMAN fallback is a weak match to NBER dates, and it is what turned the label on for March 2020, the month before Sahm. It accounts for 272 of 13,421 days, about two percentage points of the 20.57%. A higher `_TH_REC_ISM` aimed at 2019 and March 2020 would be fit to those two episodes. The real-yield change was kept only where a neighbourhood of thresholds passed, with negative controls, and the acceptance episodes held. This fallback fails that test: the stretch it would remove is one slowdown, and the day-share would still be about 18%.

`regimes.py` and `factors.py` are unchanged.

## Checks

On this branch, with the classifier untouched:

- `RUN_LIVE_TESTS=1 pytest tests/test_research_macro_regimes.py -k "backrun or tape" -p no:cacheprovider`: 11 passed in 8.94s. That is the 8 live acceptance episodes (GFC `RECESSION` in the top 2, COVID deflation, inflation, both real-yield shocks, both risk-on years, 2013 taper, October 2023), the live regime-tape test, and two offline tape-shape tests the name filter also matches.
- Clean-room `env -i HOME=$HOME PATH=$PATH $PY -m pytest tests -q -p no:cacheprovider`: 1106 passed, 34 skipped, in 114s.
- `uvx ruff@0.16.9 check src tests` and `uvx ruff@0.16.9 format --check src tests`: both clean (267 files already formatted).

## Reproduce

From the repo root, with `FRED_API_KEY` available the usual way (`src.core.keys`):

```bash
python scripts/recession_label_study.py
```

The script prints the tables and writes nothing under tracked paths. The factor frame is cached in `/tmp/marketpulse-t12-factor-cache`.
