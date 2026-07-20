# Warsh's QE-without-QE Toolkit: A Deep Dive

**Date:** 2026-07-19
**Status:** Living document — updated as signals arrive
**Related:** `docs/superpowers/analysis/2026-07-15-warsh-framework-hypotheses.md`

---

## Overview

Fed Chair Kevin Warsh has six operational tools that let him provide monetary accommodation without cutting the policy rate or announcing "QE." Each tool has a specific transmission mechanism, affects a different part of the yield curve, and carries political cover language that lets Warsh maintain his hawkish narrative while functionally easing.

This document covers each tool in depth: what it does mechanically, which curve segment it affects, how to detect if Warsh is deploying it, and the historical precedent.

---

## 1. Reserves Management Purchases (RMP)

### What it does
The Fed buys short-term Treasury bills (T-bills) from primary dealers to maintain "ample reserves" in the banking system. This is technically a plumbing operation — the Fed needs reserves above a certain threshold for its interest rate framework to function. But the pace and size of purchases can be expanded well beyond what's strictly necessary.

### Curve effect
**Suppresses the short end (3M, 1Y, 2Y).** Buying T-bills creates demand for short-duration government paper, pushing short-term yields down. The effect is strongest on 3-month yields and diminishes at 2-year.

Heuristic model: per $10B/month of RMP, 3M yield drops ~2bps, 1Y drops ~1bp, 2Y drops ~0.5bps. Effect on 5Y+ is negligible.

### Current deployment
~$40B/month (established under Powell in late 2025). Warsh inherited this pace. Expanding to $60-80B/month would be a meaningful dovish signal without changing the policy rate.

### Political cover
"Technical operation to maintain ample reserves in the banking system." This language frames RMP as plumbing, not policy. No one can accuse Warsh of "doing QE" when he's "maintaining reserves."

### How to detect expansion
- **NY Fed Open Market Operations reports** — weekly T-bill purchase volumes
- **Fed balance sheet composition** — T-bill holdings increasing as % of total
- **Reserve balances** — if reserves are above ~$3.2T and RMP continues, the purchases are discretionary, not necessary

### Historical precedent
The Fed used similar operations during 2019 repo crisis (Bernanke/Powell transition) and during COVID (March 2020). In both cases, T-bill purchases were framed as technical but provided meaningful accommodation.

---

## 2. QT Pace (Balance Sheet Runoff)

### What it does
The Fed allows Treasury and MBS holdings to mature without reinvestment. This shrinks the balance sheet — currently $6.7T — at a set monthly pace. Higher pace = tighter conditions. Lower pace = easier conditions.

### Curve effect
**Affects all yields, but biggest impact on rate expectations (2Y).** QT signals tight monetary policy. When the market expects QT to continue, short-term rate expectations embed that tightening. When QT slows, the short end drops as rate cut expectations build.

Heuristic model: per $10B/month of QT, 2Y rises ~1.2bps (expectations channel). Long-end effect is smaller (~0.6bps on 10Y) because long yields are driven more by growth/inflation expectations than Fed signals.

### Current deployment
~$60B/month ($35B Treasuries + $25B MBS). This is the "standard" QT pace set in 2024.

### Political cover
"Data-dependent balance sheet normalization." Warsh can slow QT by saying "we're assessing conditions" without ever admitting he's easing.

### How to detect slowdown
- **FOMC statement language** — watch for "pace of balance sheet runoff will be assessed"
- **H.4.1 report** (weekly Fed balance sheet) — actual runoff vs. cap
- **MBS payoff rates** — if MBS runoff slows below the $25B cap, the Fed is letting prepayments dictate pace (passive easing)

### Historical precedent
Powell slowed QT in 2019 after repo market stress. The "mid-cycle adjustment" was framed as technical but provided significant accommodation. Bernanke used "Operation Twist" (selling short Treasuries, buying long) as a balance sheet tool without expanding total size.

---

## 3. Standing Repo Facility (SRF)

### What it does
The Fed offers overnight repo loans to primary dealers at a fixed rate (currently the upper bound of the funds rate range). This caps money market rates — no matter how tight liquidity gets, primary dealers can always borrow from the Fed at the SRF rate.

### Curve effect
**Reduces short-end funding stress.** When the SRF cap is high, money market rates stay anchored because dealers know they have a backstop. This indirectly caps 3M and 1Y yields by preventing funding squeezes.

Heuristic model: per $100B increase in daily SRF cap, 3M yield drops ~1bp. Effect on 2Y+ is negligible.

### Current deployment
$500B/day cap (established under Powell). Expanding to $1T/day would be a meaningful signal that Warsh is building a bigger safety net.

### Political cover
"Operational liquidity backstop to ensure market functioning." Framed as plumbing, not policy. Expanding it is "improving operational readiness."

### How to detect expansion
- **FOMC implementation notes** — SRF cap changes are announced here
- **Daily SRF usage data** — NY Fed publishes take-up daily
- **Eligible collateral expansion** — Warsh could expand what dealers can post as collateral

### Historical precedent
The SRF was created in 2021 under Powell. Before that, the Fed used ad-hoc repo operations during the 2019 and 2020 crises. Warsh expanding the SRF would institutionalize a larger backstop.

---

## 4. MBS Sales (Balance Sheet Composition Shift)

### What it does
The Fed actively sells mortgage-backed securities from its portfolio and uses the proceeds to buy Treasury securities. This doesn't change the total balance sheet size — it changes the composition. Warsh has written extensively that the Fed should hold only Treasuries, not MBS.

### Curve effect
**Slight support for 7-10Y Treasury yields.** Selling MBS puts upward pressure on mortgage rates (reducing MBS demand), but buying Treasuries with the proceeds creates demand at the 7-10Y part of the curve. Net effect: slight yield reduction at 7-10Y.

Heuristic model: per $10B/month of MBS sales, 10Y yield drops ~0.5bps (Treasury demand offsetting MBS selling pressure).

### Current deployment
$0/month (not actively selling — just letting MBS run off naturally through QT). Starting active sales would be a new Warsh initiative.

### Political cover
"Balance sheet composition optimization." Warsh frames this as improving the quality of Fed holdings, not as easing or tightening.

### How to detect initiation
- **FOMC statement** — any mention of "balance sheet composition" or "MBS holdings"
- **H.4.1 report** — MBS holdings declining faster than natural runoff
- **MBS market reaction** — mortgage spreads widening would signal Fed selling

### Historical precedent
The Fed has never actively sold MBS before. The closest parallel is "Operation Twist" (2011-2012), where the Fed sold short Treasuries and bought long Treasuries to flatten the curve. Warsh's version would sell MBS and buy Treasuries — a composition shift, not a duration shift.

---

## 5. Forward Guidance

### What it does
The Fed communicates its expected future rate path through the dot plot, threshold-based guidance ("rates will stay low until inflation reaches 2%"), and press conference language. Strong forward guidance anchors short-term rate expectations. Removing it lets the market price risk independently.

### Curve effect
**Removing guidance raises 2Y by ~8bps.** When the Fed stops promising a specific rate path, the market demands a term premium for uncertainty. 2Y is most affected because it's the tenor most sensitive to Fed rate expectations.

### Current deployment
Active (strong forward guidance with dot plot and threshold-based language). Warsh has written that forward guidance is counterproductive and wants to reduce it.

### Political cover
"Market-based rate discovery." Warsh frames removing guidance as letting markets function properly, not as tightening. The irony: removing guidance is a hawkish signal (2Y rises) but gives Warsh more flexibility to pivot later (he's not bound by promises).

### How to detect removal
- **FOMC statement** — removal of specific rate path language ("rates will remain elevated")
- **Dot plot** — reduced emphasis, fewer dots, wider dispersion, or removal entirely
- **Press conference** — Warsh emphasizes "data-dependent" and "meeting by meeting"

### Historical precedent
Greenspan famously avoided forward guidance ("if I seem unduly clear to you, you must have misunderstood what I said"). Bernanke introduced explicit guidance in 2008. Yellen refined it with thresholds. Powell maintained it. Warsh removing it would return to the Greenspan approach.

---

## 6. Bank Regulation Index

### What it does
The Fed regulates bank capital requirements, stress test severity, and lending standards. Stricter regulation (Dodd-Frank era) constrains bank lending. Relaxing regulation allows banks to lend more freely, expanding credit.

### Curve effect
**Steepens the curve.** When banks can lend more freely, credit expands, growth expectations rise, and the long end of the curve rises relative to the short end. The effect is modest but directionally important.

Heuristic model: per 0.1 increase in relaxation index (0=strict, 1=relaxed), 10Y rises ~1bp relative to 2Y. Net effect: curve steepens.

### Current deployment
Moderate (index ~0.3 — some Dodd-Frank rollback under Trump's first term, but core rules intact). Warsh has written that Dodd-Frank went "too far."

### Political cover
"Financial system efficiency" and "modernizing regulatory framework." Warsh frames deregulation as improving credit access, not as monetary easing.

### How to detect relaxation
- **Fed rulemaking agenda** — capital requirement proposals, stress test changes
- **CCAR/DFAST results** — easier scenarios, lower capital buffers
- **Supervision letters** — less stringent bank examinations
- **SLR (Supplementary Leverage Ratio) modifications** — any relief for large banks

### Historical precedent
The 2018 Dodd-Frank rollback (Economic Growth, Regulatory Relief, and Consumer Protection Act) eased rules for mid-sized banks. The 2020 SLR relief for Treasuries (expired) is another example. Warsh would push for broader relaxation.

---

## How the Tools Combine

The power of Warsh's framework is that these tools can be deployed in combination to produce significant easing without any single tool looking like "QE":

| Configuration | RMP | QT | SRF | MBS Sales | Guidance | Bank Reg | Net Effect |
|--------------|-----|-----|-----|-----------|----------|----------|------------|
| **Hawkish (A)** | $20B | $80B | $500B | $20B | Removed | Strict | Curve flattens |
| **Current** | $40B | $60B | $500B | $0 | Active | Moderate | Neutral |
| **Pantomime (B)** | $80B | $20B | $1000B | $0 | Removed | Moderate | Curve steepens |
| **Dovish (C)** | $80B | $0 | $1000B | $0 | Active | Relaxed | Curve steepens significantly |

The key insight: the dovish configuration looks very different from traditional QE (no rate cut, no balance sheet expansion) but produces a similar functional effect — curve steepening, credit expansion, and asset price support.

---

## The Detection Framework

To determine which scenario (A/B/C) is unfolding, watch these signals in priority order:

1. **Balance sheet panel recommendations** (Q3 2026) — THE disambiguation event
2. **RMP volume changes** — expansion = dovish signal
3. **QT pace adjustments** — slowdown = dovish signal
4. **FOMC language shifts** — "higher for longer" → "patient" → "data-dependent"
5. **Forward guidance changes** — dot plot de-emphasis = dovish signal
6. **SRF cap adjustments** — expansion = dovish signal

Each signal updates the hypothesis tracker probabilities. Run:
```bash
python scripts/warsh_hypothesis_tracker.py --signal "description" --scenario C --direction confirm
```

---

## The Interactive Simulator

All six tools are modeled in the interactive Streamlit dashboard:
```bash
streamlit run scripts/warsh_dashboard.py
```

Adjust the sliders, roll for market events, and watch the curve respond in real-time. The simulator uses the heuristic models described above — directionally correct but not econometrically rigorous.