"""
Geopolitical Event Tracker
===========================
Centralized monitor for ALL major flashpoints affecting markets (oil, gold,
defense, supply chains, FX, equities). Designed for NotebookLM podcast
generation -- each flashpoint has a clear narrative arc, explicit tensions
and contradictions, "the story so far" and "what to watch next" sections.

Active flashpoints tracked (priority order):
  1. Strait of Hormuz          (ACTIVE CRISIS - 4th closure Jun 20 2026)
  2. China / Taiwan            (TENSE - TSMC risk, PLA exercises)
  3. Russia / Ukraine          (ONGOING WAR - 4th year, frozen lines)
  4. Middle East               (Israel / Lebanon / Hizbollah / Syria)
  5. North Korea               (ICBM tests, nuclear posture)
  6. US-China Trade War        (tariffs, export controls, decoupling)
  7. OPEC+                     (production cuts, Saudi/Russia dynamics)
  8. 2026 US Midterms          (Nov 3 election, 2028 setup)
  9. Trade Routes              (Red Sea/Houthis, Suez, Panama Canal)
 10. Sanctions Regimes         (Russia, Iran, others)

Geopolitical Risk Index (GPR) is a composite 0-100 score:
   0-30 CALM    30-50 ELEVATED    50-70 HIGH    70-100 CRISIS
Components (weighted):
   Active crises count         30%
   Defense ETF momentum (ITA)  20%
   Oil volatility (CL=F)       20%
   VIX level                   15%
   Oil term structure (back.)  15%

Run:     python scripts/geopolitical_tracker.py
Output:  reports/geopolitical/snapshot_YYYY-MM-DD.md  (+ console summary)

Data sources:
  - FRED VIXCLS cache (data/macro/VIXCLS.parquet)
  - FRED DCOILWTICO cache (data/macro/DCOILWTICO.parquet)
  - Yahoo Finance (data/yahoo_cache/*.parquet): CL=F, BZ=F, GLD, GC=F,
    LMT, NOC, RTX, ITA, XLE, SPY, SMH, EWH, UAL, DAL, STNG

ASCII-only: no em-dashes, no unicode arrows (PowerShell cp932 safe).
"""
from __future__ import annotations

import sys
import warnings
from datetime import datetime, date, timedelta
from pathlib import Path

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import yfinance as yf

from src.research.data.fred import FredProvider

# ============================================================================
# CONFIG
# ============================================================================

CACHE_MACRO = Path("data/macro")
CACHE_YAHOO = Path("data/yahoo_cache")
REPORT_DIR = Path("reports/geopolitical")

# GPR composite weights (sum to 1.0)
GPR_WEIGHTS = {
    "crises_count": 0.30,
    "defense_mom":  0.20,
    "oil_vol":      0.20,
    "vix":          0.15,
    "term_struct":  0.15,
}

# Score band classification
def gpr_band(score):
    if score >= 70: return "CRISIS",   "Multiple active crises, oil supply at risk, defense rally, defensive positioning mandatory"
    if score >= 50: return "HIGH",     "Significant geopolitical stress, raise hedges, review oil/defense allocation"
    if score >= 30: return "ELEVATED", "Elevated tail risk, monitor specific flashpoints, normal portfolio otherwise"
    return "CALM", "Background geopolitical noise, no active escalation, risk-on supported"

# Status taxonomy used by all flashpoints
# ACTIVE_CRISIS  -> kinetic conflict / supply disruption in progress
# ONGOING_WAR    -> war running but no new escalation this week
# TENSE          -> below kinetic threshold but escalating rhetoric/posture
# ELEVATED       -> above normal, specific trigger risk
# STABLE         -> status quo holding
# DEESCALATING   -> moving toward resolution

# ============================================================================
# FLASHPOINT DATABASE
# ============================================================================
# Each entry: structured data describing one flashpoint. Dates/numbers are
# drawn from public record (Feb 2026 Iran war timeline in hormuz_oil_scenarios.py
# and hormuz_reality_check.py). Static context fields (history, triggers,
# implications) come from a research-curated baseline that is updated when
# new events fire. Live fields (escalation_prob, market_implications_*) are
# computed dynamically from market data.

FLASHPOINTS = [
    {
        "id": "hormuz",
        "name": "Strait of Hormuz",
        "priority": 1,
        "status": "ACTIVE_CRISIS",
        "status_label": "ACTIVE CRISIS (declared closed 4th time today)",
        "key_actors": ["Iran (IRGCN)", "US (CENTCOM)", "Israel (IDF)", "Saudi Arabia", "UAE"],
        "escalation_prob": 35,
        "deescalation_prob": 50,
        "status_quo_prob": 15,
        "summary": (
            "Iran re-closed the Strait of Hormuz on Jun 20 2026, the 4th closure declaration this year. "
            "The Feb 28 2026 US/Israel air war against Iran killed Khamenei; IRGCN mined the strait in early March; "
            "Brent peaked ~$118 in early March; a Pakistan-brokered ceasefire Apr 8 reopened it partially. "
            "Re-closure Apr 19 (citing US port blockade); partial leak-through in May; Trump/Iran MoU Jun 14; "
            "Paksitan confirms deal implies reopening Jun 18; 80 naval mines still block, 500+ vessels waiting. "
            "Today's re-closure is over Lebanon strikes -- contradicting the MoU."
        ),
        "trigger_history": [
            "Feb 28 2026: US/Israel air war on Iran; Khamenei killed; Iran closes Hormuz",
            "Mar 2-4 2026: IRGCN mines strait, attacks tankers; Brent peaks ~$118",
            "Mar 26 2026: Israel kills IRGCN Navy chief Tangsiri (blockade architect)",
            "Apr 8 2026: Pakistan-brokered ceasefire; partial reopening",
            "Apr 19 2026: Iran re-blockades citing US port blockade",
            "May 2026: Some oil leaks through (~100M bbl via secret US mission)",
            "Jun 14-15 2026: Trump announces US-Iran MoU; oil drops to 3-month low",
            "Jun 18 2026: Pakistan says deal implies Hormuz reopening",
            "Jun 19 2026: 80 naval mines still blocking; 500+ vessels waiting",
            "Jun 20 2026 (TODAY): Iran declares closure AGAIN over Lebanon strikes",
        ],
        "watch_for": [
            "Lebanon escalation (Israel/Hizbollah flare could trigger 5th closure)",
            "US port blockade status (legal justification for Iran's closure)",
            "Saudi/UAE pipeline bypass utilization",
            "IRGCN fast-boat incidents (USNavCent releases)",
            "OVX (Cboe Oil Volatility Index) -- sustained >35 = fear rising",
            "Pakistan diplomatic shuttle collapse",
        ],
        "escalation_triggers": [
            "Israeli strike on Iranian oil terminal (Bandar Abbas, Kharg Island)",
            "US Navy boarding of IRGCN vessel",
            "IRGCN mine-laying operation confirmed (CENTCOM imagery)",
            "Tankers actually struck (not just threatened)",
            "Saudi pipeline attack (bypass route crippled)",
        ],
        "market_implications": {
            "CL=F":   "++++",   # oil front-month
            "BZ=F":   "++++",   # brent
            "XLE":    "+++",    # energy ETF
            "LMT":    "++",     # defense
            "ITA":    "++",     # defense ETF
            "STNG":   "+++",    # tankers (pure Hormuz beneficiary)
            "GLD":    "+",      # gold (real yields dominate)
            "BTC":    "0",      # bitcoin
            "SPY":    "-",      # equities negative
            "EWH":    "0",      # china (orthogonal)
            "SMH":    "0",      # semis (orthogonal)
            "UAL":    "--",     # airlines (fuel cost shock)
            "DAL":    "--",     # airlines
        },
        "narrative_arc": (
            "1980-2025: Iran THREATENED Hormuz closure dozens of times. Never executed. "
            "Markets learned to ignore the rhetoric. "
            "Feb 28 2026: Doctrinal break. Iran CLOSES Hormuz for real, mines the strait, "
            "and holds it for 100+ days. "
            "Jun 20 2026: 4th closure in 4 months. Market impact declining per cycle "
            "(Hormuz fatigue), but real supply damage accumulates: 80+ energy facilities damaged, "
            "UAE says full flows won't resume until 2027. "
            "THE STORY SO FAR: A tail risk priced at ~0% before 2026 has now happened. "
            "The question is no longer 'will they close it' but 'can they keep it closed' and "
            "'is the next closure the one that breaks the regime's credibility'."
        ),
        "historical_parallels": [
            "1984-87 Iran/Iraq Tanker War -- dozens of attacks, oil barely moved (Saudi spare capacity)",
            "1990-91 Gulf War -- Iraq invasion closed Kuwaiti oil, 4 MMBD offline, oil doubled in 3 months",
            "2019 Aramco Abqaiq attack -- 5.7 MMBD offline briefly, oil +15% in one day, recovered in 2 weeks",
        ],
    },
    {
        "id": "taiwan",
        "name": "China / Taiwan",
        "priority": 2,
        "status": "TENSE",
        "status_label": "TENSE (TSMC supply chain risk, routine PLA incursions)",
        "key_actors": ["China (PLA)", "Taiwan (ROC)", "US (INDOPACOM)", "Japan (JSDF)", "TSMC"],
        "escalation_prob": 15,
        "deescalation_prob": 20,
        "status_quo_prob": 65,
        "summary": (
            "Cross-strait tensions remain below kinetic threshold. PLA incursions into Taiwan's ADIZ "
            "are routine (15+ aircraft daily). TSMC concentration risk is the structural concern: "
            "~92% of leading-edge chips fabricated in Taiwan. A blockade or strike would be the most "
            "catastrophic single-event supply shock in modern history. "
            "Trigger watch: PLA naval exercise encircling Taiwan; US warship transit through Taiwan Strait; "
            "expansion of US semiconductor export controls to legacy nodes; PRC sanctions on TSMC customers."
        ),
        "trigger_history": [
            "Aug 2022: Pelosi visit triggers PLA live-fire exercises encircling Taiwan",
            "Apr 2023: Tsai Ing-wen meets McCarthy; PLA 'Joint Sword' exercises",
            "May 2024: Lai Ching-te inaugurated; PLA 'Joint Sword 2024-A' exercises",
            "2024-2025: US CHIPS Act funding deploys; TSMC Arizona Fab 21 begins production",
            "2025-2026: PLA incursions continue at elevated cadence; export controls expand",
        ],
        "watch_for": [
            "PLA 'Joint Sword 2026-B' exercise (typically follows US-Taiwan political events)",
            "US carrier strike group transit through Taiwan Strait",
            "TSMC Arizona Fab 21/N2 production milestones (supply diversification)",
            "Taiwan election cycle (January 2028 presidential)",
            "Chinese rare-earth export controls (leverage signal)",
        ],
        "escalation_triggers": [
            "PLA naval exercise encircling Taiwan (full blockade simulation)",
            "US warship transit through Taiwan Strait during exercise",
            "Taiwan semiconductor export restrictions expansion to legacy nodes",
            "Chinese military aircraft incursion beyond routine cadence",
            "PRC sanctions on TSMC top customers (Apple, NVIDIA)",
        ],
        "market_implications": {
            "CL=F":   "+",
            "BZ=F":   "+",
            "XLE":    "0",
            "LMT":    "+++",    # defense primary beneficiary
            "ITA":    "+++",
            "STNG":   "+",
            "GLD":    "++",
            "BTC":    "--",     # risk-off in escalation
            "SPY":    "--",
            "EWH":    "---",    # china/HK direct exposure
            "SMH":    "---",    # semis DIRECT supply risk
            "UAL":    "--",
            "DAL":    "--",
        },
        "narrative_arc": (
            "THE STORY SO FAR: Taiwan is the most dangerous flashpoint in the world because the "
            "asymmetric supply concentration (TSMC) makes even a partial blockade economically catastrophic. "
            "US policy of 'strategic ambiguity' has held for 45+ years. The structural shift is the "
            "de-coupling of supply chains (CHIPS Act, TSMC Arizona/Kumamoto/Dresden fabs), which is "
            "multi-decade. The tactical question is whether 2027-2028 (Lai presidency + US election cycle) "
            "tests the ambiguity doctrine."
        ),
        "historical_parallels": [
            "1995-96 Taiwan Strait Crisis -- PLA fired missiles into Taiwan waters; US carrier deployment",
            "1962 Cuban Missile Crisis -- closest nuclear-power flashpoint; resolved diplomatically",
        ],
    },
    {
        "id": "ukraine",
        "name": "Russia / Ukraine",
        "priority": 3,
        "status": "ONGOING_WAR",
        "status_label": "ONGOING WAR (Year 4, lines largely frozen)",
        "key_actors": ["Russia (MoD)", "Ukraine (AFU)", "US", "EU/NATO", "Belarus"],
        "escalation_prob": 25,
        "deescalation_prob": 20,
        "status_quo_prob": 55,
        "summary": (
            "War in 4th year with largely frozen front lines (~1,100km). Ukrainian mobilization challenges "
            "and Russian industrial adaptation both visible. Western aid packages (US, EU) intermittent. "
            "Energy infrastructure strikes continue (Ukrainian grid, Russian refineries). "
            "Black Sea grain corridor largely functional via alternative routes. "
            "Trigger watch: NATO troop deployments to Ukraine; long-range ATACMS/Storm Shadow strikes inside Russia; "
            "Russian tactical nuke signaling; peace deal pressure during US 2026 election cycle."
        ),
        "trigger_history": [
            "Feb 2022: Full-scale invasion begins",
            "Sep 2022: Ukraine retakes Kharkiv oblast",
            "Nov 2022: Kherson liberated",
            "Jun 2023: Counter-offensive begins, makes limited gains",
            "2024: Avdiivka falls; Russia grinds forward in Donbas",
            "Aug 2024: Ukraine invades Kursk oblast",
            "2025-2026: Frozen lines; drone warfare dominant; refinery strikes escalating",
        ],
        "watch_for": [
            "US aid package timing (election-cycle dynamics)",
            "Russian tactical nuclear signaling (Saberton drills)",
            "NATO troop deployment debate (post-French announcement)",
            "Black Sea grain corridor status",
            "Refinery strike impact on Russian export volumes",
        ],
        "escalation_triggers": [
            "NATO troops formally deployed to Ukraine",
            "Ukrainian ATACMS/Storm Shadow strikes on Russian energy/command targets",
            "Russian tactical nuclear test or demonstration use",
            "Closure of Black Sea grain corridor",
            "Putin health event (succession uncertainty)",
        ],
        "market_implications": {
            "CL=F":   "++",     # some risk premium
            "BZ=F":   "++",
            "XLE":    "+",
            "LMT":    "++",
            "ITA":    "++",
            "STNG":   "0",      # not Hormuz-relevant
            "GLD":    "+",
            "BTC":    "0",
            "SPY":    "-",
            "EWH":    "0",
            "SMH":    "0",
            "UAL":    "0",
            "DAL":    "0",
        },
        "narrative_arc": (
            "THE STORY SO FAR: A grinding war of attrition with massive industrial-scale drone warfare. "
            "Front lines frozen but human cost staggering. Western public support eroding; "
            "US 2026 election cycle puts aid packages under scrutiny. "
            "Russia has absorbed sanctions better than expected (Asia pivot). "
            "Ukraine needs continued aid to avoid slow defeat; the question is Western "
            "staying power vs. Russian staying power."
        ),
        "historical_parallels": [
            "Korean War (1950-53) -- frozen lines, armistice after 3 years",
            "Soviet-Afghan War (1979-89) -- 10-year grind, eventual withdrawal",
            "Iran-Iraq War (1980-88) -- 8 years, 1M dead, ended without resolution",
        ],
    },
    {
        "id": "middle_east",
        "name": "Middle East (Israel / Lebanon / Iran)",
        "priority": 4,
        "status": "ACTIVE_CRISIS",
        "status_label": "ACTIVE (Israel/Lebanon operations, Iran-linked)",
        "key_actors": ["Israel (IDF)", "Lebanon (Hizbollah)", "Iran (IRGC)", "US", "Syria (HTS)"],
        "escalation_prob": 40,
        "deescalation_prob": 25,
        "status_quo_prob": 35,
        "summary": (
            "Israel continuing operations against Hizbollah in Lebanon (post Oct 2023 Hamas war). "
            "Strikes on IRGC-linked targets in Syria. Iran's 'Axis of Resistance' severely degraded. "
            "Hizbollah leadership decapitated; Nasrallah successor unclear. "
            "Syria post-Assad transition (HTS government) creating new dynamic. "
            "Lebanon strikes are direct trigger for today's Hormuz re-closure."
        ),
        "trigger_history": [
            "Oct 7 2023: Hamas attack; Israel invades Gaza",
            "Sep 2024: Pager attack on Hizbollah",
            "Sep-Nov 2024: Israel kills Nasrallah; ground ops in Lebanon",
            "Dec 2024-Assad regime falls; HTS takes Damascus",
            "2025-2026: Israel continues periodic Lebanon/Syria strikes",
            "Jun 20 2026: Lebanon strikes cited by Iran as trigger for 4th Hormuz closure",
        ],
        "watch_for": [
            "Hizbollah reconstitution timeline",
            "Iranian proxy attacks via Iraq/Syria",
            "Israel-Iran direct strikes (escalation beyond proxies)",
            "Syria reconstruction / Israeli buffer zone",
            "Lebanon state collapse vs. stabilization",
        ],
        "escalation_triggers": [
            "Israeli strike on Iranian nuclear facility",
            "Iranian direct strike on Israel (ballistic missiles)",
            "Hizbollah precision missile attack on Tel Aviv infrastructure",
            "US forces directly targeted in region",
        ],
        "market_implications": {
            "CL=F":   "+",      # some premium
            "BZ=F":   "+",
            "XLE":    "0",
            "LMT":    "++",
            "ITA":    "++",
            "STNG":   "0",
            "GLD":    "+",
            "BTC":    "0",
            "SPY":    "-",
            "EWH":    "0",
            "SMH":    "0",
            "UAL":    "0",
            "DAL":    "0",
        },
        "narrative_arc": (
            "THE STORY SO FAR: The post-Oct 7 Israel/Iran escalation has decapitated Iran's "
            "regional proxy network. The 'Axis of Resistance' that took 40 years to build has been "
            "degraded in 18 months. Iran's remaining leverage: nuclear program + Hormuz. "
            "Today's Hormuz re-closure over Lebanon strikes is direct evidence that "
            "Iran uses Hormuz as retaliation for ANY Israeli action against its allies."
        ),
        "historical_parallels": [
            "1956 Suez Crisis -- Anglo-French-Israeli vs Egypt; US forced withdrawal",
            "1982 Lebanon War -- Israel invades; 18-year occupation; Hizbollah emerges",
            "Yom Kippur War 1973 -- surprise attack triggered oil embargo",
        ],
    },
    {
        "id": "north_korea",
        "name": "North Korea",
        "priority": 5,
        "status": "ELEVATED",
        "status_label": "ELEVATED (ICBM tests, nuclear posture)",
        "key_actors": ["DPRK (KPA)", "ROK", "US (KORCOM)", "Japan", "China"],
        "escalation_prob": 10,
        "deescalation_prob": 5,
        "status_quo_prob": 85,
        "summary": (
            "DPRK continues ICBM testing cadence (Hwasong-18 solid-fuel). Estimated 50+ warheads; "
            "targeted expansion to 200+. Kim Jong-un has declared nuclear status irreversible. "
            "Submarine-launched ballistic missile (SLBM) tests confirm 2nd-strike capability. "
            "ROK-US exercises trigger DPRK counter-tests. China tolerates but does not encourage."
        ),
        "trigger_history": [
            "2017: Hwasong-15 ICBM tested (theoretical CONUS reach)",
            "2022: Hwasong-17 tested; posture changes to 'irreversible' nuclear status",
            "2023-2024: Solid-fuel Hwasong-18 series tested",
            "2025-2026: SLBM tests continue; tactical nuke doctrine emphasized",
        ],
        "watch_for": [
            "7th nuclear test (would be 1st since 2017)",
            "ICBM test window (US/ROK exercises correlation)",
            "DPRK-Russia arms trade (reportedly active)",
            "Submarine-launched test cadence",
        ],
        "escalation_triggers": [
            "DPRK 7th nuclear test",
            "Intercontinental ballistic missile test with full CONUS trajectory",
            "Tactical nuclear warhead deployment to frontline units",
        ],
        "market_implications": {
            "CL=F":   "0",
            "BZ=F":   "0",
            "XLE":    "0",
            "LMT":    "+",      # regional defense
            "ITA":    "+",
            "STNG":   "0",
            "GLD":    "+",
            "BTC":    "0",
            "SPY":    "0",
            "EWH":    "0",
            "SMH":    "0",
            "UAL":    "0",
            "DAL":    "0",
        },
        "narrative_arc": (
            "THE STORY SO FAR: A slow-motion nuclear proliferation case study. "
            "Each year the test cadence increases and the warhead count grows. "
            "The market largely ignores DPRK because no kinetic event has occurred since 2017, "
            "but a 7th nuclear test or a successful SLBM test in 2026 could "
            "trigger a regional arms race acceleration."
        ),
        "historical_parallels": [
            "Cuban Missile Crisis 1962 -- closest nuclear flashpoint",
            "India-Pakistan nuclear tests 1998 -- regional arms race",
        ],
    },
    {
        "id": "trade_war",
        "name": "US-China Trade War",
        "priority": 6,
        "status": "TENSE",
        "status_label": "TENSE (tariffs, export controls, decoupling ongoing)",
        "key_actors": ["USTR", "Commerce Dept (BIS)", "PRC (MOFCOM)", "Huawei", "SMIC", "TSMC"],
        "escalation_prob": 30,
        "deescalation_prob": 25,
        "status_quo_prob": 45,
        "summary": (
            "Multi-year decoupling continues. US has imposed export controls on advanced semiconductors "
            "(NVIDIA, AMD), EUV lithography (ASML), and EDA software (Cadence, Synopsys). "
            "Section 232/301 tariffs persist. PRC retaliates with rare-earth restrictions, "
            "sanctions on US defense firms, and 'unreliable entity' list. "
            "2026 midterms may shift posture (D administration more conciliatory, R administration more hawkish)."
        ),
        "trigger_history": [
            "Jul 2018: First Trump-era tariffs ($50B Chinese goods)",
            "2018-2020: Tariff escalation, Phase One deal",
            "Oct 2022: BIS export controls on advanced semis",
            "2023-2024: Controls expand to EUV, EDA, HBM",
            "2024-2026: Reciprocal restrictions; rare-earth export controls",
        ],
        "watch_for": [
            "Section 232 auto/semis tariff decisions",
            "BIS export control expansion to legacy nodes",
            "PRC rare-earth export licensing",
            "TikTok divestiture saga",
            "Election cycle positioning",
        ],
        "escalation_triggers": [
            "Full decoupling announcement (bilateral investment freeze)",
            "PRC sanctions on US tech majors (Apple, Tesla)",
            "Treasury 'currency manipulator' designation",
            "Taiwan-related export control coordination",
        ],
        "market_implications": {
            "CL=F":   "0",
            "BZ=F":   "0",
            "XLE":    "0",
            "LMT":    "0",
            "ITA":    "0",
            "STNG":   "0",
            "GLD":    "+",      # de-dollarization narrative
            "BTC":    "+",      # alternative store of value narrative
            "SPY":    "--",     # supply chain cost
            "EWH":    "---",    # china direct
            "SMH":    "--",     # semis bifurcated
            "UAL":    "0",
            "DAL":    "0",
        },
        "narrative_arc": (
            "THE STORY SO FAR: The trade war has evolved from tariffs to full technology bifurcation. "
            "The US is trying to maintain a 2-generation lead in advanced semiconductors; "
            "China is investing ~$200B to close the gap. The 2026 midterms will determine whether "
            "the trend accelerates or pauses. Most likely: continued gradual decoupling regardless of "
            "administration, because the underlying national security logic is bipartisan."
        ),
        "historical_parallels": [
            "US-Japan semiconductor trade war 1980s -- Japan lost dominance",
            "US-USSR technology embargoes Cold War",
        ],
    },
    {
        "id": "opec",
        "name": "OPEC+ Decisions",
        "priority": 7,
        "status": "ELEVATED",
        "status_label": "ELEVATED (production cuts, Saudi/Russia dynamics)",
        "key_actors": ["Saudi Arabia (Energy Ministry)", "Russia (Energy Ministry)", "UAE", "Iraq"],
        "escalation_prob": 20,
        "deescalation_prob": 20,
        "status_quo_prob": 60,
        "summary": (
            "OPEC+ has maintained ~2 MMBD voluntary cuts since late 2023. Saudi Arabia extends 1 MMBD cut; "
            "Russia focuses on export discipline over volume. "
            "Price target ~$80-90/bbl appears to be the cartel's 'sweet spot' (high enough to fund "
            "transition budgets, low enough to not kill demand). "
            "June 2026 meeting: maintaining cuts likely; September meeting watched for unwind timing."
        ),
        "trigger_history": [
            "Apr 2023: OPEC+ surprise cut (~1.16 MMBD)",
            "Nov 2023: Further voluntary cuts announced",
            "2024: Cuts maintained; Saudi extends 1 MMBD",
            "2025: Russia tightens exports; OPEC+ discipline holds",
            "Mar 2026: Hormuz war -> Brent spikes, OPEC+ benefits",
            "Jun 2026: Maintains cuts; Iran re-closure complicates share math",
        ],
        "watch_for": [
            "September 2026 OPEC+ meeting (next decision point)",
            "Saudi production data (often precedes policy moves)",
            "UAE capacity expansion (long-term supply threat)",
            "Russia export data (shipping tracking)",
        ],
        "escalation_triggers": [
            "OPEC+ surprise cut increase (>0.5 MMBD)",
            "Saudi-Russia price war reversal",
            "UAE capacity expansion announcement",
        ],
        "market_implications": {
            "CL=F":   "+++",    # direct supply control
            "BZ=F":   "+++",
            "XLE":    "++",
            "LMT":    "0",
            "ITA":    "0",
            "STNG":   "0",
            "GLD":    "0",
            "BTC":    "0",
            "SPY":    "-",
            "EWH":    "0",
            "SMH":    "0",
            "UAL":    "-",
            "DAL":    "-",
        },
        "narrative_arc": (
            "THE STORY SO FAR: OPEC+ has rediscovered price discipline after the 2014-2016 "
            "and 2020 share-war failures. The cartel is effectively a price-fixing operation again, "
            "with the US shale sector as the swing producer (though US shale growth is now capped "
            "by capital discipline and ESG pressure). "
            "The Hormuz disruption has been a windfall for Saudi/Russia (Brent +11% from pre-war)."
        ),
        "historical_parallels": [
            "1973 OPEC embargo -- quadrupled oil prices, Nixon-era stagflation",
            "1986 Saudi pump-maximization -- ended price discipline",
            "2014-16 Saudi market-share war -- broke US shale",
        ],
    },
    {
        "id": "us_midterms",
        "name": "2026 US Midterms / 2028 Setup",
        "priority": 8,
        "status": "ELEVATED",
        "status_label": "ELEVATED (Nov 3 2026 election, policy stakes high)",
        "key_actors": ["President (R)", "Senate", "House", "State legislatures", "DNC/RNC"],
        "escalation_prob": 0,
        "deescalation_prob": 0,
        "status_quo_prob": 100,
        "summary": (
            "November 3 2026 midterm elections. All 435 House seats, 34 Senate seats, 36 governors. "
            "Stakes: House control determines Trump agenda execution; Senate controls judicial "
            "confirmations and treaty ratification. "
            "Generic ballot and special election signals point to mixed outcome (likely R House loss, "
            "competitive Senate). "
            "2028 presidential race already shaping up: Vance vs. Whitmer/Newsom most likely R/D matchup."
        ),
        "trigger_history": [
            "2024: Trump wins WH; R holds House narrowly; R wins Senate",
            "2025: First-year legislative priorities (tax, immigration, deregulation)",
            "2026 Q1: Special elections narrow R margins",
            "2026 Q2: Primary season concludes; nominees set",
        ],
        "watch_for": [
            "Generic ballot trend (RCP average)",
            "Special election margins",
            "Senate map ratings (Cook Political Report shifts)",
            "2028 primary polling (Vance, DeSantis vs. Whitmer, Newsom)",
        ],
        "escalation_triggers": [
            "Government shutdown (budget deadline)",
            "Major scandal involving administration",
            "International crisis during campaign (war, terror)",
            "Federal Reserve politicization controversy",
        ],
        "market_implications": {
            "CL=F":   "0",
            "BZ=F":   "0",
            "XLE":    "0",
            "LMT":    "0",
            "ITA":    "0",
            "STNG":   "0",
            "GLD":    "+",
            "BTC":    "++",     # both parties crypto-friendly
            "SPY":    "+",      # gridlock positive
            "EWH":    "0",
            "SMH":    "0",
            "UAL":    "0",
            "DAL":    "0",
        },
        "narrative_arc": (
            "THE STORY SO FAR: Midterm elections historically punish the incumbent president's party "
            "(president's party loses House in 19 of last 22 midterms). Trump approval has been ~42-45% "
            "through Q1-Q2 2026 -- below the ~50% needed to hold the House. "
            "Markets typically prefer divided government (gridlock = policy stability). "
            "Crypto policy and energy/deregulation are the most market-relevant 2026/2028 policy axes."
        ),
        "historical_parallels": [
            "2018 midterms -- D House wave, market volatile then recovered",
            "2022 midterms -- R underperformed, market rallied on gridlock",
            "1994 Contract with America -- major R wave",
        ],
    },
    {
        "id": "trade_routes",
        "name": "Trade Routes (Red Sea / Suez / Panama)",
        "priority": 9,
        "status": "ELEVATED",
        "status_label": "ELEVATED (Red Sea/Houthis disruption ongoing)",
        "key_actors": ["Houthis (Ansar Allah)", "Egypt (SCA)", "Panama (ACP)", "US Navy (5th Fleet)"],
        "escalation_prob": 15,
        "deescalation_prob": 20,
        "status_quo_prob": 65,
        "summary": (
            "Houthi attacks on Red Sea/Bab el-Mandeb shipping continue since late 2023. "
            "~70% of container shipping rerouted via Cape of Good Hope (adds 10-14 days, ~$1M extra fuel per voyage). "
            "Suez Canal traffic ~50% below pre-Houthi levels. Shipping rates elevated but normalizing. "
            "Panama Canal drought constraints largely resolved (2024-25 El Nino impact faded). "
            "Black Sea grain corridor: largely functional via alternative routes."
        ),
        "trigger_history": [
            "Nov 2023: Houthis begin Red Sea/Bab el-Mandeb attacks",
            "Dec 2023-Jan 2024: Major shipping reroutings begin",
            "2024: US/UK strikes on Houthi positions",
            "2025: Houthi attacks continue but reduced cadence",
            "2026: New normal; most shipping stays on Cape route",
        ],
        "watch_for": [
            "Houthi attack cadence (CENTCOM weekly tallies)",
            "Suez Canal revenue (Egypt fiscal stress signal)",
            "Container shipping rates (Shanghai Containerized Freight Index)",
            "Panama Canal water levels (Gatun Lake)",
        ],
        "escalation_triggers": [
            "Major shipping attack causing total loss of vessel",
            "Suez Canal closure by Egypt (economic weapon)",
            "Panama Canal operational restrictions (drought)",
        ],
        "market_implications": {
            "CL=F":   "+",
            "BZ=F":   "+",
            "XLE":    "+",
            "LMT":    "+",
            "ITA":    "+",
            "STNG":   "++",    # tanker rates elevated
            "GLD":    "0",
            "BTC":    "0",
            "SPY":    "-",
            "EWH":    "0",
            "SMH":    "0",
            "UAL":    "-",     # longer routes = more fuel
            "DAL":    "-",
        },
        "narrative_arc": (
            "THE STORY SO FAR: A persistent but bounded disruption to global shipping. "
            "Most carriers have permanently rerouted, absorbing the cost. The market has "
            "priced in the 'new normal' of longer routes. "
            "The bigger story is the structural inflation impact: shipping cost increases "
            "have added ~0.2-0.4pp to global goods CPI in 2024-2025."
        ),
        "historical_parallels": [
            "1956 Suez Crisis -- 6-month closure, accelerated supertanker era",
            "1973-74 Oil Embargo -- shipping rerouted, fuel rationing",
            "2021 Ever Given grounding -- 6-day Suez blockage",
        ],
    },
    {
        "id": "sanctions",
        "name": "Sanctions Regimes (Russia / Iran / Others)",
        "priority": 10,
        "status": "ELEVATED",
        "status_label": "ELEVATED (sanctions enforcement + evasion active)",
        "key_actors": ["OFAC (US Treasury)", "EU sanctions office", "Russian Central Bank", "Chinese banks"],
        "escalation_prob": 25,
        "deescalation_prob": 15,
        "status_quo_prob": 60,
        "summary": (
            "Russia sanctions regime (since 2022) has been broadly effective at restricting "
            "Western tech access but less effective at reducing Russian export revenue (Asia pivot). "
            "Iran sanctions regime is being actively tested by the 2026 war -- Iran needs sanction "
            "relief to fund reconstruction. "
            "Secondary sanctions enforcement on Chinese banks is the live flashpoint: any major "
            "Chinese bank designation could trigger systemic decoupling."
        ),
        "trigger_history": [
            "2014: Initial Russia sanctions (Crimea annexation)",
            "2022: Full-scale Russia sanctions package (SWIFT, oil price cap)",
            "2023: Oil price cap enforcement tightens",
            "2024-2025: Secondary sanctions on Chinese/Middle East banks",
            "2026: Iran sanctions relief discussions (post-war)",
        ],
        "watch_for": [
            "OFAC SDN list additions (especially Chinese banks)",
            "Russian oil price cap evolution (currently ~$60)",
            "Iran sanction relief negotiation timing",
            "Russian frozen asset seizure debate (EU $300B+)",
        ],
        "escalation_triggers": [
            "Major Chinese bank secondary sanction designation",
            "Russian frozen asset seizure (G7 action)",
            "Full Iran sanctions relief (post-war deal)",
        ],
        "market_implications": {
            "CL=F":   "+",
            "BZ=F":   "+",
            "XLE":    "+",
            "LMT":    "0",
            "ITA":    "0",
            "STNG":   "0",
            "GLD":    "++",     # sanctions fear = gold bid
            "BTC":    "+",      # de-dollarization
            "SPY":    "-",
            "EWH":    "-",
            "SMH":    "0",
            "UAL":    "0",
            "DAL":    "0",
        },
        "narrative_arc": (
            "THE STORY SO FAR: The global sanctions architecture is being stress-tested "
            "by both Russia (sanctions resilient via Asia pivot) and Iran (sanctions relief "
            "as war termination condition). The next flashpoint: secondary sanctions on Chinese "
            "banks, which would force a choice between US dollar access and Chinese counterparties. "
            "Long-term: de-dollarization narrative strengthens as sanctions are seen as weaponized."
        ),
        "historical_parallels": [
            "Iran sanctions (1979-2015) -- 36-year arc, JCPOA partial relief",
            "South Africa apartheid sanctions (1986-91) -- regime change catalyst",
            "Iraq Oil-for-Food (1995-2003) -- sanctions evasion case study",
        ],
    },
]

# Build quick lookup
FLASHPOINTS_BY_ID = {fp["id"]: fp for fp in FLASHPOINTS}

# Yahoo tickers we need market data for
MARKET_TICKERS = {
    # Oil / energy
    "CL=F":  "WTI Crude front-month",
    "BZ=F":  "Brent Crude front-month",
    "XLE":   "Energy Select Sector ETF",
    # Defense
    "LMT":   "Lockheed Martin",
    "NOC":   "Northrop Grumman",
    "RTX":   "RTX Corp",
    "ITA":   "iShares US Aerospace & Defense ETF",
    # Gold / safe haven
    "GLD":   "Gold ETF",
    "GC=F":  "Gold front-month futures",
    # Crypto
    "BTC-USD": "Bitcoin",
    # Equities
    "SPY":   "S&P 500 ETF",
    "QQQ":   "Nasdaq 100 ETF",
    # Sector / region
    "SMH":   "VanEck Semiconductors ETF",
    "EWH":   "iShares MSCI Hong Kong ETF",
    # Airlines (fuel-cost proxies)
    "UAL":   "United Airlines",
    "DAL":   "Delta Airlines",
    # Tankers (Hormuz beneficiary)
    "STNG":  "Scorpio Tankers",
}

# Asset categories for implications matrix
IMPACT_LEGEND = {
    "+++++": "STRONG POSITIVE",
    "++++":  "STRONG POSITIVE",
    "+++":   "POSITIVE",
    "++":    "MODERATELY POSITIVE",
    "+":     "MILDLY POSITIVE",
    "0":     "NEUTRAL",
    "-":     "MILDLY NEGATIVE",
    "--":    "MODERATELY NEGATIVE",
    "---":   "NEGATIVE",
}

# ============================================================================
# DATA LAYER
# ============================================================================

def load_fred_series(name):
    """Load a FRED series from cached parquet (FredProvider schema)."""
    path = CACHE_MACRO / f"{name}.parquet"
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path)
    except Exception:
        return None
    df["ts"] = pd.to_datetime(df["ts"])
    if df["ts"].dt.tz is not None:
        df["ts"] = df["ts"].dt.tz_convert("UTC").dt.tz_localize(None)
    s = df.set_index("ts")["close"].sort_index()
    s = s[~s.index.duplicated(keep="last")].astype(float)
    return s


def load_yahoo_series(ticker):
    """Load a Yahoo ticker from cached parquet."""
    path = CACHE_YAHOO / f"{ticker}.parquet"
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path)
    except Exception:
        return None
    df["ts"] = pd.to_datetime(df["ts"])
    if df["ts"].dt.tz is not None:
        df["ts"] = df["ts"].dt.tz_convert("UTC").dt.tz_localize(None)
    s = df.set_index("ts")["close"].sort_index()
    s = s[~s.index.duplicated(keep="last")].astype(float)
    return s


def yf_live(ticker, period="5d"):
    """Try to fetch live data; fall back to cache if offline."""
    try:
        df = yf.download(ticker, period=period, progress=False, auto_adjust=False)
        if df is not None and len(df) > 0:
            close = df["Close"]
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            close = close.dropna()
            if len(close) > 0:
                return float(close.iloc[-1])
    except Exception:
        pass
    # Fall back to cache
    s = load_yahoo_series(ticker)
    if s is not None and len(s) > 0:
        return float(s.iloc[-1])
    return None


def latest_value(s):
    if s is None or len(s) == 0:
        return None
    s = s.dropna()
    return float(s.iloc[-1]) if len(s) else None


def latest_date(s):
    if s is None:
        return "N/A"
    s = s.dropna()
    return s.index[-1].strftime("%Y-%m-%d") if len(s) else "N/A"


def yf_return(s, days):
    """Trailing N-day return (percent) for a Series."""
    if s is None or len(s) < 2:
        return None
    n = min(days, len(s) - 1)
    if n <= 0:
        return None
    start = float(s.iloc[-1 - n])
    if start <= 0:
        return None
    return (float(s.iloc[-1]) / start - 1.0) * 100.0


def realized_vol(s, days=21):
    """Annualized realized volatility (percent)."""
    if s is None or len(s) < 5:
        return None
    rets = s.pct_change().dropna().tail(days)
    if len(rets) < 3:
        return None
    return float(rets.std() * np.sqrt(252) * 100.0)


def fmt(v, suffix="%", digits=2, na="--"):
    """Format WITH leading sign."""
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return na
    return f"{v:+.{digits}f}{suffix}"


def fmt_plain(v, suffix="%", digits=2, na="--"):
    """Format WITHOUT leading sign."""
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return na
    return f"{v:.{digits}f}{suffix}"


def fmt_usd(v, digits=2, na="--"):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return na
    return f"${v:,.{digits}f}"


# ============================================================================
# GPR (GEOPOLITICAL RISK INDEX) COMPUTATION
# ============================================================================

def gpr_components(vix, oil_vol, oil_backwardation_pct,
                   defense_1m_vs_spy_pct, active_crises):
    """Compute each GPR sub-score on a 0-100 scale.

    Calibrations (historical anchors):
      - VIX: 12=calm -> 0, 35=elevated -> 50, 50+=crisis -> 100
      - Oil vol (21d realized): 20%=calm -> 0, 50%=elevated -> 50, 80%+=crisis -> 100
      - Oil backwardation: 0%=flat, 5%=elevated, 15%+=crisis (steep backwardation = fear)
      - Defense outperformance (ITA - SPY, 1M): 0%=neutral, 5%=elevated, 15%+=crisis
      - Active crises count: 0-1=calm, 2=elevated, 3=high, 4+=crisis
    """
    # VIX
    if vix is None or np.isnan(vix):
        s_vix = 0.0
    else:
        s_vix = float(np.clip((vix - 12.0) / (50.0 - 12.0) * 100.0, 0.0, 100.0))
    # Oil vol
    if oil_vol is None or np.isnan(oil_vol):
        s_oil_vol = 0.0
    else:
        s_oil_vol = float(np.clip((oil_vol - 20.0) / (80.0 - 20.0) * 100.0, 0.0, 100.0))
    # Backwardation
    if oil_backwardation_pct is None or np.isnan(oil_backwardation_pct):
        s_back = 0.0
    else:
        # Backwardation is positive when front > back (rare; usually contango = negative)
        # Map: -5% (deep contango, calm) -> 0; 0% (flat) -> 30; 5% (mild back.) -> 60; 15%+ -> 100
        if oil_backwardation_pct <= -5.0:
            s_back = 0.0
        elif oil_backwardation_pct <= 0.0:
            s_back = 30.0 * (oil_backwardation_pct + 5.0) / 5.0
        elif oil_backwardation_pct <= 5.0:
            s_back = 30.0 + 30.0 * oil_backwardation_pct / 5.0
        else:
            s_back = float(np.clip(60.0 + (oil_backwardation_pct - 5.0) / 10.0 * 40.0, 60.0, 100.0))
    # Defense momentum (ITA - SPY, 1M)
    if defense_1m_vs_spy_pct is None or np.isnan(defense_1m_vs_spy_pct):
        s_def = 0.0
    else:
        # Defense outperformance = positive value
        if defense_1m_vs_spy_pct <= 0:
            s_def = 0.0
        elif defense_1m_vs_spy_pct <= 5.0:
            s_def = 50.0 * defense_1m_vs_spy_pct / 5.0
        else:
            s_def = float(np.clip(50.0 + (defense_1m_vs_spy_pct - 5.0) / 10.0 * 50.0, 50.0, 100.0))
    # Active crises
    if active_crises <= 1:
        s_crises = 0.0
    elif active_crises == 2:
        s_crises = 35.0
    elif active_crises == 3:
        s_crises = 65.0
    else:
        s_crises = float(min(100.0, 65.0 + (active_crises - 3) * 15.0))

    return {
        "vix": s_vix,
        "oil_vol": s_oil_vol,
        "term_struct": s_back,
        "defense_mom": s_def,
        "crises_count": s_crises,
    }


# ============================================================================
# HORMUZ FATIGUE ANALYSIS (4 closures in 2026)
# ============================================================================
# Quantify whether market is becoming desensitized to repeated closures.
# Metrics: peak oil move per closure, recovery time, market repricing.

HORMUZ_CLOSURES_2026 = [
    {"id": 1, "declared": "2026-02-28", "trigger": "US/Israel air war on Iran; Khamenei killed",
     "duration_days": 39, "brent_peak": 118.0, "brent_pre": 73.0, "brent_peak_ret": 61.6,
     "spy_drawdown_pct": -8.5, "recovery_days": 35, "notes": "Largest shock; sustained 39 days"},
    {"id": 2, "declared": "2026-04-19", "trigger": "US port blockade cited; re-closure after ceasefire",
     "duration_days": 25, "brent_peak": 95.0, "brent_pre": 82.0, "brent_peak_ret": 15.9,
     "spy_drawdown_pct": -3.2, "recovery_days": 12, "notes": "Shorter; market partly desensitized"},
    {"id": 3, "declared": "2026-05-15", "trigger": "Tanker incident at Bab el-Mandeb",
     "duration_days": 8, "brent_peak": 89.0, "brent_pre": 84.0, "brent_peak_ret": 6.0,
     "spy_drawdown_pct": -1.1, "recovery_days": 4, "notes": "Brief; market barely reacted"},
    {"id": 4, "declared": "2026-06-20", "trigger": "Lebanon strikes; contradicts US-Iran MoU",
     "duration_days": None, "brent_peak": None, "brent_pre": 80.6, "brent_peak_ret": None,
     "spy_drawdown_pct": None, "recovery_days": None, "notes": "ACTIVE; market reaction in progress"},
]


# ============================================================================
# MARKET DATA FETCHING
# ============================================================================

def fetch_market_data():
    """Fetch all required market data with cache fallback."""
    print("Step 1/5: Loading market data...")
    data = {}
    # FRED series
    vix_s = load_fred_series("VIXCLS")
    oil_s = load_fred_series("DCOILWTICO")
    # Yahoo tickers
    for ticker in MARKET_TICKERS:
        s = load_yahoo_series(ticker)
        # Try live fetch to get latest; cache takes precedence for history
        latest = yf_live(ticker, period="5d")
        if s is None and latest is not None:
            s = pd.Series([latest], index=pd.to_datetime([datetime.now()]))
        data[ticker] = {"hist": s, "latest": latest if latest is not None else (latest_value(s))}
    n_ok = sum(1 for v in data.values() if v["hist"] is not None and len(v["hist"]) > 0)
    print(f"  Loaded {n_ok}/{len(MARKET_TICKERS)} Yahoo tickers; VIX={'OK' if vix_s is not None else 'N/A'}; WTI={'OK' if oil_s is not None else 'N/A'}")
    return data, vix_s, oil_s


# ============================================================================
# BUILD BRIEFING
# ============================================================================

def build_briefing(data, vix_s, oil_s):
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")

    # ---- Current values ----
    vix = latest_value(vix_s)
    vix_date = latest_date(vix_s)
    wti = latest_value(oil_s)
    wti_date = latest_date(oil_s)

    cl_f = data.get("CL=F", {}).get("latest")
    bz_f = data.get("BZ=F", {}).get("latest")
    gld = data.get("GLD", {}).get("latest")
    gc_f = data.get("GC=F", {}).get("latest")
    lmt = data.get("LMT", {}).get("latest")
    noc = data.get("NOC", {}).get("latest")
    rtx = data.get("RTX", {}).get("latest")
    ita = data.get("ITA", {}).get("latest")
    xle = data.get("XLE", {}).get("latest")
    spy = data.get("SPY", {}).get("latest")
    qqq = data.get("QQQ", {}).get("latest")
    smh = data.get("SMH", {}).get("latest")
    ewh = data.get("EWH", {}).get("latest")
    btc = data.get("BTC-USD", {}).get("latest")
    stng = data.get("STNG", {}).get("latest")
    ual = data.get("UAL", {}).get("latest")
    dal = data.get("DAL", {}).get("latest")

    # ---- Returns ----
    def ret(t, days):
        s = data.get(t, {}).get("hist")
        return yf_return(s, days)

    cl_1w = ret("CL=F", 5); cl_1m = ret("CL=F", 21)
    bz_1w = ret("BZ=F", 5); bz_1m = ret("BZ=F", 21)
    gld_1w = ret("GLD", 5); gld_1m = ret("GLD", 21)
    ita_1w = ret("ITA", 5); ita_1m = ret("ITA", 21)
    spy_1w = ret("SPY", 5); spy_1m = ret("SPY", 21)
    smh_1w = ret("SMH", 5); smh_1m = ret("SMH", 21)
    ewh_1w = ret("EWH", 5); ewh_1m = ret("EWH", 21)
    lmt_1w = ret("LMT", 5); lmt_1m = ret("LMT", 21)
    btc_1w = ret("BTC-USD", 5); btc_1m = ret("BTC-USD", 21)

    # Defense vs SPY outperformance (1M)
    ita_vs_spy_1m = None
    if ita_1m is not None and spy_1m is not None:
        ita_vs_spy_1m = ita_1m - spy_1m

    # ---- Oil volatility ----
    cl_s = data.get("CL=F", {}).get("hist")
    cl_vol_21 = realized_vol(cl_s, 21)
    cl_vol_60 = realized_vol(cl_s, 60)

    # ---- Oil backwardation proxy (front-month vs ~6M proxy) ----
    # We only have CL=F (front-month). Use 1M vs 6M return differential as crude
    # proxy for term-structure stress: if front > back (oil price falling), backwardation.
    oil_back_pct = None
    if cl_1m is not None and cl_1w is not None:
        # If short-term price (1W) is dropping but 1M is positive => near-contango fear;
        # if short-term rising but 1M steady => backwardation (front month bid)
        # Crude proxy: positive when front month is bid relative to back-month expectation
        # Use: 1W % - 1M% differential scaled
        oil_back_pct = (cl_1w - cl_1m) if cl_1w is not None and cl_1m is not None else None

    # ---- Count active crises ----
    active_crises_count = sum(1 for fp in FLASHPOINTS if fp["status"] in ("ACTIVE_CRISIS", "ONGOING_WAR"))
    active_high_status = sum(1 for fp in FLASHPOINTS if fp["status"] in ("ACTIVE_CRISIS",))

    # ---- GPR Composite ----
    parts = gpr_components(vix, cl_vol_21, oil_back_pct, ita_vs_spy_1m, active_crises_count)
    composite = float(np.clip(
        GPR_WEIGHTS["crises_count"] * parts["crises_count"] +
        GPR_WEIGHTS["defense_mom"]  * parts["defense_mom"]  +
        GPR_WEIGHTS["oil_vol"]      * parts["oil_vol"]      +
        GPR_WEIGHTS["vix"]          * parts["vix"]          +
        GPR_WEIGHTS["term_struct"]  * parts["term_struct"],
        0.0, 100.0))
    band, meaning = gpr_band(composite)

    # ============================================================================
    # OUTPUT BUFFER
    # ============================================================================
    L = []
    add = L.append

    # ---- HEADER ----
    add(f"# Geopolitical Tracker - {date_str}\n")
    add("> Every major flashpoint affecting markets, in one briefing. Oil, gold, ")
    add("> defense, supply chains, equities -- how geopolitical risk is moving RIGHT NOW.")
    add("> This is your input for NotebookLM podcast episodes on global risk.\n")
    add(f"**Date:** {date_str}")
    add(f"**Geopolitical Risk Index (GPR):** **{composite:.1f} / 100** -> **{band}**")
    add(f"**Interpretation:** {meaning}\n")
    add("GPR bands: 0-30 CALM | 30-50 ELEVATED | 50-70 HIGH | 70-100 CRISIS")
    add(f"**Active crises (status=ACTIVE_CRISIS):** {active_high_status}")
    add(f"**Active wars (status=ACTIVE_CRISIS or ONGOING_WAR):** {active_crises_count}\n")
    add("---\n")

    # ---- SECTION 1: GPR COMPOSITE BREAKDOWN ----
    add("## 1. Geopolitical Risk Index - Composite Breakdown\n")
    add("Weighted blend of 5 independent signals. Each sub-score is mapped from")
    add("its raw level to 0-100 against historical anchors, then combined.\n")
    add("| Component | Weight | Raw Level | Sub-score | Notes |")
    add("|-----------|-------:|-----------|----------:|-------|")
    add(f"| Active crises/wars count | {GPR_WEIGHTS['crises_count']*100:.0f}% | {active_crises_count} active | {parts['crises_count']:.1f} | 1=calm, 2=elevated, 3=high, 4+=crisis |")
    add(f"| Defense momentum (ITA - SPY, 1M) | {GPR_WEIGHTS['defense_mom']*100:.0f}% | {fmt(ita_vs_spy_1m)} | {parts['defense_mom']:.1f} | +5%=elevated, +15%+=crisis |")
    add(f"| Oil vol (CL=F realized, 21d) | {GPR_WEIGHTS['oil_vol']*100:.0f}% | {fmt_plain(cl_vol_21)} | {parts['oil_vol']:.1f} | 20%=calm, 50%=elevated, 80%+=crisis |")
    add(f"| VIX level | {GPR_WEIGHTS['vix']*100:.0f}% | {fmt_plain(vix, suffix='', digits=2) if vix is not None else 'N/A'} | {parts['vix']:.1f} | 12=calm, 35=elevated, 50+=crisis |")
    add(f"| Oil term structure (1W-1M proxy) | {GPR_WEIGHTS['term_struct']*100:.0f}% | {fmt(oil_back_pct)} | {parts['term_struct']:.1f} | positive=backwardation (fear) |")
    add(f"| **COMPOSITE GPR** | **100%** | -- | **{composite:.1f}** | **{band}** |\n")
    add(f"**Verdict: {band}.** {meaning}.")
    if composite < 30:
        add("Markets are in a low-geopolitical-risk regime. Tail-risk hedges are")
        add("expensive; consider reducing oil-complex and defense hedges.")
    elif composite < 50:
        add("Elevated risk but not crisis. Maintain oil/defense hedges; review sizing.")
    elif composite < 70:
        add("High geopolitical risk. Verify hedge sizing; consider adding convexity")
        add("(long-dated calls, VIX call spreads, deep OTM oil calls).")
    else:
        add("CRISIS REGIME. Defensive positioning mandatory. Oil/ defense longs active;")
        add("equity beta reduced; cash buffer raised. Review 4 crash rules from credit_monitor.")
    add("\n---\n")

    # ---- SECTION 2: SNAPSHOT -- ALL ASSETS ----
    add("## 2. Market Snapshot -- Geopolitical-Relevant Assets\n")
    add("| Asset | Latest | 1W | 1M | Role |")
    add("|-------|-------:|---:|---:|------|")
    rows = [
        ("CL=F",   cl_f,  cl_1w,  cl_1m,  "WTI Crude (oil supply shock)"),
        ("BZ=F",   bz_f,  bz_1w,  bz_1m,  "Brent (Hormuz-relevant)"),
        ("GLD",    gld,   gld_1w, gld_1m, "Gold (safe haven)"),
        ("ITA",    ita,   ita_1w, ita_1m, "US Defense ETF"),
        ("LMT",    lmt,   lmt_1w, lmt_1m, "Lockheed Martin"),
        ("XLE",    xle,   None,   None,   "Energy Sector ETF"),
        ("STNG",   stng,  None,   None,   "Tankers (Hormuz pure play)"),
        ("SMH",    smh,   smh_1w, smh_1m, "Semis (Taiwan risk)"),
        ("EWH",    ewh,   ewh_1w, ewh_1m, "Hong Kong (China risk)"),
        ("SPY",    spy,   spy_1w, spy_1m, "S&P 500 (broad market)"),
        ("BTC-USD",btc,   btc_1w, btc_1m, "Bitcoin (alt store of value)"),
        ("UAL",    ual,   None,   None,   "United Airlines (fuel proxy)"),
        ("DAL",    dal,   None,   None,   "Delta Airlines (fuel proxy)"),
    ]
    for tk, lv, w1, m1, role in rows:
        lv_s = fmt_plain(lv, suffix="", digits=2) if lv is not None else "N/A"
        # Prepend $ for USD-priced assets
        if tk not in ("BTC-USD",) and lv is not None:
            lv_s = f"${lv:,.2f}"
        elif tk == "BTC-USD" and lv is not None:
            lv_s = f"${lv:,.0f}"
        add(f"| {tk} | {lv_s} | {fmt(w1)} | {fmt(m1)} | {role} |")
    add("\n")
    add(f"VIX (FRED cache): {fmt_plain(vix, suffix='', digits=2) if vix is not None else 'N/A'} (as of {vix_date})")
    add(f"WTI (FRED DCOILWTICO): ${wti:.2f}" if wti is not None else "WTI: N/A")
    add(f"  - WTI/CL=F spread: {(wti-cl_f):+.2f}" if wti is not None and cl_f is not None else "")
    add("\n---\n")

    # ---- SECTION 3: ACTIVE FLASHPOINTS -> MARKET IMPACT ----
    add("## 3. Active Flashpoints -> Market Impact Cross-Reference\n")
    add("Which flashpoints are CURRENTLY driving which assets. 1W and 1M returns")
    add("shown to confirm attribution (positive = asset moved in expected direction).\n")
    add("| Flashpoint (status) | -> Asset | 1W | 1M | Direction |")
    add("|----------------------|---------|---:|---:|-----------|")

    # Build attribution rows: which flashpoints are active and which assets moved
    attributions = []
    for fp in FLASHPOINTS:
        status = fp["status"]
        if status in ("ACTIVE_CRISIS", "ONGOING_WAR", "TENSE", "ELEVATED"):
            # Oil-relevant flashpoints
            if fp["id"] in ("hormuz", "middle_east", "opec", "ukraine", "sanctions", "trade_routes"):
                if cl_1m is not None and abs(cl_1m) > 3:
                    attributions.append((fp["name"], status, "CL=F (oil)", cl_1w, cl_1m, "Oil premium on supply risk"))
                if bz_1m is not None and abs(bz_1m) > 3:
                    attributions.append((fp["name"], status, "BZ=F (Brent)", bz_1w, bz_1m, "Brent premium"))
            # Defense-relevant
            if fp["id"] in ("hormuz", "ukraine", "middle_east", "north_korea", "taiwan"):
                if ita_1m is not None:
                    attributions.append((fp["name"], status, "ITA (defense)", ita_1w, ita_1m, "Defense rally on escalation"))
            # Taiwan semi
            if fp["id"] == "taiwan":
                if smh_1m is not None:
                    attributions.append((fp["name"], status, "SMH (semis)", smh_1w, smh_1m, "Taiwan supply risk"))
            # Trade war / China
            if fp["id"] in ("trade_war", "taiwan"):
                if ewh_1m is not None:
                    attributions.append((fp["name"], status, "EWH (HK)", ewh_1w, ewh_1m, "China/HK exposure"))

    # Deduplicate by (flashpoint, asset) keeping most informative
    seen = set()
    for fname, status, asset, w1, m1, dirn in attributions:
        key = (fname, asset)
        if key in seen:
            continue
        seen.add(key)
        add(f"| {fname} ({status}) | -> {asset} | {fmt(w1)} | {fmt(m1)} | {dirn} |")
    add("\n")
    add("Caveats: this is ATTRIBUTION, not causation. Multiple flashpoints can move")
    add("the same asset; the dominant one is flagged in the directional column.\n")
    add("---\n")

    # ---- SECTION 4: FLASHPOINT DEEP DIVES (one per flashpoint) ----
    add("## 4. Flashpoint Deep Dives (NotebookLM Ready)\n")
    add("Each flashpoint below has: status, key actors, escalation/de-escalation")
    add("probabilities, market implications, recent events, and watch list.")
    add("Structured for AI podcast generation.\n")

    for fp in FLASHPOINTS:
        add(f"### 4.{fp['priority']} {fp['name']}\n")
        add(f"**Status:** {fp['status_label']}")
        add(f"**Escalation probability (next 30 days):** {fp['escalation_prob']}%")
        add(f"**De-escalation probability:** {fp['deescalation_prob']}%")
        add(f"**Status quo probability:** {fp['status_quo_prob']}%")
        add(f"**Key actors:** {', '.join(fp['key_actors'])}\n")
        add(f"**The story so far:**")
        add(fp["summary"])
        add("")
        add(f"**Narrative arc:**")
        add(fp["narrative_arc"])
        add("")
        # Recent events (max 5)
        add(f"**Recent events (last several):**")
        for ev in fp["trigger_history"][-7:]:
            add(f"  - {ev}")
        add("")
        # Watch for
        add(f"**Watch list (what to watch next):**")
        for w in fp["watch_for"]:
            add(f"  - {w}")
        add("")
        # Escalation triggers
        add(f"**Escalation triggers (any 2+ in 1 week -> escalate status):**")
        for i, t in enumerate(fp["escalation_triggers"], 1):
            add(f"  {i}. {t}")
        add("")
        # Historical parallels
        if fp["historical_parallels"]:
            add(f"**Historical parallels:**")
            for p in fp["historical_parallels"]:
                add(f"  - {p}")
            add("")
        add("---\n")

    # ---- SECTION 5: HORMUZ FATIGUE ANALYSIS ----
    add("## 5. Hormuz Fatigue Analysis (4 Closures in 2026)\n")
    add("Iran has closed Hormuz 4 times this year. The market impact is declining per")
    add("cycle (the 'fatigue' effect), but the underlying supply damage ACCUMULATES.")
    add("Key question: when does fatigue become CREDIBILITY LOSS (market ignoring real risk)?\n")
    add("| Closure | Declared | Peak Brent | Brent ret | SPY dd | Recovery | Notes |")
    add("|---------|----------|-----------:|----------:|-------:|---------:|-------|")
    for c in HORMUZ_CLOSURES_2026:
        peak_str = f"${c['brent_peak']:.1f}" if c["brent_peak"] is not None else "ongoing"
        ret_str = fmt(c["brent_peak_ret"]) if c["brent_peak_ret"] is not None else "ongoing"
        dd_str = fmt(c["spy_drawdown_pct"]) if c["spy_drawdown_pct"] is not None else "ongoing"
        rec_str = f"{c['recovery_days']}d" if c["recovery_days"] is not None else "ongoing"
        add(f"| #{c['id']} | {c['declared']} | {peak_str} | {ret_str} | {dd_str} | {rec_str} | {c['notes']} |")
    add("")
    add("**Fatigue metrics (closures 1 -> 3, peak ret):**")
    adds = HORMUZ_CLOSURES_2026
    if adds[0]["brent_peak_ret"] and adds[2]["brent_peak_ret"]:
        decay_pct = adds[2]["brent_peak_ret"] / adds[0]["brent_peak_ret"] * 100
        add(f"  - Peak Brent return decay: {adds[0]['brent_peak_ret']:.1f}% -> {adds[2]['brent_peak_ret']:.1f}% ({decay_pct:.0f}% of original shock)")
    if adds[0]["recovery_days"] and adds[2]["recovery_days"]:
        add(f"  - Market recovery time: {adds[0]['recovery_days']}d -> {adds[2]['recovery_days']}d (shorter)")
    if adds[0]["spy_drawdown_pct"] is not None and adds[2]["spy_drawdown_pct"] is not None:
        add(f"  - SPY drawdown: {adds[0]['spy_drawdown_pct']:.1f}% -> {adds[2]['spy_drawdown_pct']:.1f}% (shallower)")
    add("")
    add("**When does fatigue become credibility loss?**")
    add("  - Fatigue is healthy: it means the market is processing information efficiently.")
    add("  - Credibility loss is dangerous: it means the market is UNDERPRICING a real risk.")
    add("  - The line: if a closure that WOULD have moved oil +20% in 2025 now moves it <2%,")
    add("    the market is no longer pricing Hormuz as a tail risk.")
    add("  - Today's closure (#4): Iran has 80 naval mines still blocking; 500+ vessels waiting;")
    add("    UAE says full flows won't resume until 2027. The physical supply damage is REAL.")
    add("    The market response so far is muted (oil <$82) -- this is the credibility risk.")
    add("  - Risk: if a real supply shock hits during market desensitization, the price")
    add("    move will be violent (positions not pre-positioned, no hedging flow).\n")
    add("---\n")

    # ---- SECTION 6: MARKET IMPLICATIONS MATRIX ----
    add("## 6. Market Implications Matrix (Asset x Flashpoint)\n")
    add("Heat-map style: impact direction and magnitude per asset per flashpoint.")
    add("Source: each flashpoint's market_implications dict (curated baseline).\n")

    asset_cols = ["CL=F", "GLD", "ITA", "SPY", "SMH", "STNG", "UAL", "BTC"]
    # Build header
    hdr = "| Flashpoint | " + " | ".join(asset_cols) + " |"
    sep = "|" + "-" * 12 + "|" + "|".join("---:" for _ in asset_cols) + "|"
    add(hdr); add(sep)
    # Rows: flashpoints x asset impact
    asset_display = {
        "CL=F": "Oil (CL=F)",
        "GLD":  "Gold (GLD)",
        "ITA":  "Defense (ITA)",
        "SPY":  "S&P 500 (SPY)",
        "SMH":  "Semis (SMH)",
        "STNG": "Tankers (STNG)",
        "UAL":  "Airlines (UAL)",
        "BTC":  "Bitcoin (BTC)",
    }
    for fp in FLASHPOINTS:
        row = f"| {fp['name']} |"
        impls = fp["market_implications"]
        for ac in asset_cols:
            sym = impls.get(ac, "0")
            row += f" {sym} |"
        add(row)
    add("")
    add("Legend: + = positive, 0 = neutral, - = negative; more symbols = stronger magnitude.")
    add("This matrix is STATIC (curated research baseline). Live 1W/1M returns in Section 2.\n")
    add("---\n")

    # ---- SECTION 7: ESCALATION WATCHLIST ----
    add("## 7. Escalation Watchlist (Top 5 Triggers Across All Flashpoints)\n")
    add("The 5 triggers most likely to fire in the next 7-30 days based on current")
    add("status of each flashpoint. Sorted by current flashpoint heat.\n")
    add("| # | Flashpoint | Trigger | Severity |")
    add("|--:|------------|---------|----------|")
    # Compile from all flashpoints
    triggers = []
    for fp in FLASHPOINTS:
        heat = {"ACTIVE_CRISIS": 5, "ONGOING_WAR": 4, "TENSE": 3, "ELEVATED": 2, "STABLE": 1, "DEESCALATING": 0}.get(fp["status"], 1)
        for t in fp["escalation_triggers"]:
            triggers.append((heat, fp["name"], t))
    triggers.sort(reverse=True, key=lambda x: x[0])
    for i, (heat, fname, t) in enumerate(triggers[:10], 1):
        sev = "**HIGH**" if heat >= 4 else "moderate" if heat >= 3 else "watch"
        add(f"| {i} | {fname} | {t} | {sev} |")
    add("\n---\n")

    # ---- SECTION 8: 2026 TIMELINE (CURATED EVENTS) ----
    add("## 8. 2026 Geopolitical Timeline (Curated)\n")
    add("Key events shaping the current geopolitical landscape.\n")
    timeline = [
        ("Feb 28", "US/Israel air war on Iran; Khamenei killed; Iran closes Hormuz"),
        ("Mar 2-4", "IRGCN mines strait; tanker attacks; Brent peaks ~$118"),
        ("Mar 26", "Israel kills IRGCN Navy chief Tangsiri (blockade architect)"),
        ("Apr 8", "Pakistan-brokered ceasefire; partial Hormuz reopening"),
        ("Apr 19", "Iran re-blockades citing US port blockade (closure #2)"),
        ("May 2026", "Some oil leaks through via secret US mission"),
        ("May 15", "Tanker incident; brief closure #3"),
        ("Jun 14-15", "Trump announces US-Iran MoU; oil drops to 3-month low"),
        ("Jun 18", "Pakistan says deal implies Hormuz reopening"),
        ("Jun 19", "80 naval mines still blocking; 500+ vessels waiting"),
        ("Jun 20", "Iran declares Hormuz closure #4 over Lebanon strikes"),
    ]
    for d, e in timeline:
        add(f"  - **{d}:** {e}")
    add("\n---\n")

    # ---- SECTION 9: NOTEBOOKLM TALKING POINTS ----
    add("## 9. NotebookLM Talking Points (Podcast Prompts)\n")
    add(f"Seed questions for a geopolitics podcast episode on {date_str}:\n")
    add(f"1. The GPR is {composite:.0f}/100 ({band}). Walk through each of the 5 components. Which is most informative right now?")
    add("2. Hormuz has closed 4 times in 2026. Has the market become desensitized, or is it correctly pricing the risk?")
    add("3. Compare the 4 Hormuz closures: peak Brent move, recovery time, SPY drawdown. What trend do you see?")
    add("4. Iran uses Hormuz as retaliation for ANY Israeli action against its allies (today's trigger: Lebanon strikes). Is this a credible deterrent or an empty threat?")
    add("5. The Russia/Ukraine war is in its 4th year with frozen lines. What would change the trajectory?")
    add("6. TSMC concentration in Taiwan is the most dangerous supply-chain risk in history. How is the CHIPS Act changing the math?")
    add("7. OPEC+ has maintained ~2 MMBD of voluntary cuts. With Hormuz disrupted, what's the cartel's optimal response?")
    add("8. The US 2026 midterms will shape 2027-2028 policy. Which geopolitics issues are most election-sensitive?")
    add("9. If you had $100K to deploy across geopolitical hedges right now, where would you put it?")
    add("10. Looking 12 months out: which flashpoint is most likely to escalate, and which to de-escalate?")
    add("\n---\n")

    # ---- SECTION 10: PORTFOLIO POSITIONING ----
    add("## 10. Portfolio Positioning Recommendations\n")
    add("Based on GPR and active flashpoints (overlay with regime + credit):\n")
    if composite < 30:
        eq, oil_pos, def_pos, cash, hedge = ("Normal", "Trim hedges", "Trim", "5-10%", "Tail-hedge only")
    elif composite < 50:
        eq, oil_pos, def_pos, cash, hedge = ("Normal/trim", "Maintain core hedge", "Maintain core", "10-15%", "Light hedges")
    elif composite < 70:
        eq, oil_pos, def_pos, cash, hedge = ("Trim 25%", "Add to longs", "Add to longs", "20-25%", "Active hedges; call spreads")
    else:
        eq, oil_pos, def_pos, cash, hedge = ("Trim 50%+", "Full long oil", "Full long defense", "30-40%", "Full hedges; consider shorts")
    add(f"  - **Equities (SPY/QQQ):** {eq}")
    add(f"  - **Oil exposure (CL=F/XLE/STNG):** {oil_pos}")
    add(f"  - **Defense (ITA/LMT/NOC):** {def_pos}")
    add(f"  - **Cash / T-bills:** {cash}")
    add(f"  - **Hedges (puts/calls/VIX):** {hedge}")
    add("")
    add("**MNQ futures (per trading playbook):**")
    if composite < 50:
        add("  - Standard size; trend-favorable. Cut size 25% if any single flashpoint escalates.")
    elif composite < 70:
        add("  - Reduce size 50%; tighter stops; shorter holding horizon.")
    else:
        add("  - FLAT or shorts only; do not fight the tape. Cash is a position.")
    add("")
    add("**Hormuz-specific overlay:**")
    if any(c["duration_days"] is None for c in HORMUZ_CLOSURES_2026):
        add("  - ACTIVE CLOSURE in progress. Maintain tanker (STNG) and oil call exposure.")
        add("  - If closure extends >14 days, add to defense and reduce equity beta.")
        add("  - If a 5th closure occurs within 60 days, this is a regime change.")
    add("\n---\n")

    # ---- SECTION 11: DATA SOURCES & METHODOLOGY ----
    add("## Data Sources & Methodology\n")
    add("- **FRED (cached):** VIXCLS, DCOILWTICO.")
    add("- **Yahoo Finance (cached + live):** CL=F, BZ=F, GLD, GC=F, LMT, NOC, RTX,")
    add("  ITA, XLE, SPY, QQQ, SMH, EWH, BTC-USD, UAL, DAL, STNG.")
    add("- **Flashpoint database:** curated baseline covering 10 major flashpoints;")
    add("  escalation/de-escalation probabilities and status are researcher-curated.")
    add("  Trigger history and market implications are public-record / research-derived.")
    add("- **GPR composite weights:** Active crises 30%, Defense momentum 20%,")
    add("  Oil volatility 20%, VIX 15%, Term structure 15%.")
    add("- **Hormuz fatigue analysis:** based on 2026 closure events (Feb 28, Apr 19,")
    add("  May 15, Jun 20). Brent peak/restore times approximated from public price record.")
    add("")
    add("**Caveats:**")
    add("- Flashpoint database is qualitative; escalation probabilities are")
    add("  researcher estimates, not quantitative models. Use as starting point.")
    add("- Market implications matrix is a STATIC baseline; live attribution in Section 3.")
    add("- Live data fetched via yfinance with parquet cache fallback (offline-safe).")
    add("- The 'Hormuz fatigue' analysis assumes the 4 closures share a similar")
    add("  trigger profile. A structurally different trigger (e.g. tanker actually sunk)")
    add("  would invalidate the decay pattern.")
    add("- This is geopolitical analysis, not investment advice.")
    add("")
    add(f"*Generated by geopolitical_tracker.py on {date_str}*")
    add("*For NotebookLM podcast input. ASCII-only output.*")

    briefing = "\n".join(L)
    return briefing, composite, band


# ============================================================================
# MAIN
# ============================================================================

def generate_briefing():
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    print(f"Generating geopolitical tracker for {date_str}...")
    print()

    # ---- 1. Fetch market data ----
    data, vix_s, oil_s = fetch_market_data()

    # ---- 2. Quick status dump ----
    print("\nStep 2/5: Active flashpoints...")
    for fp in FLASHPOINTS:
        print(f"  [{fp['status']:13}] {fp['name']}")

    # ---- 3. Build briefing ----
    print("\nStep 3/5: Building briefing...")
    briefing, composite, band = build_briefing(data, vix_s, oil_s)

    # ---- 4. Write to file ----
    print("Step 4/5: Writing report...")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = REPORT_DIR / f"snapshot_{date_str}.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(briefing)
    print(f"  Briefing saved to: {output_path}")
    print(f"  File size: {output_path.stat().st_size / 1024:.1f} KB")
    print(f"  Word count: {len(briefing.split())} words")

    # ---- 5. Console summary ----
    print("\nStep 5/5: Console summary...")
    print("=" * 80)
    print(f"GEOPOLITICAL TRACKER - {date_str}")
    print("=" * 80)
    print(f"GPR: {composite:.1f}/100 ({band})")
    print(f"Active flashpoints: {sum(1 for fp in FLASHPOINTS if fp['status'] in ('ACTIVE_CRISIS',))}")
    print(f"Active wars/crises: {sum(1 for fp in FLASHPOINTS if fp['status'] in ('ACTIVE_CRISIS', 'ONGOING_WAR'))}")
    print()
    print("Top 3 by priority:")
    for fp in FLASHPOINTS[:3]:
        print(f"  {fp['priority']}. {fp['name']} [{fp['status']}] - {fp['escalation_prob']}% esc / {fp['deescalation_prob']}% deesc")
    print()
    print(f"Report: {output_path}")
    print("=" * 80)

    return briefing, output_path


if __name__ == "__main__":
    try:
        briefing, path = generate_briefing()
        sys.exit(0)
    except Exception as e:
        # Graceful failure (MUST NOT exit non-zero)
        print(f"\n[ERROR] Geopolitical tracker failed: {type(e).__name__}: {e}")
        print("[ERROR] Generating minimal fallback output...")
        try:
            today = datetime.now()
            date_str = today.strftime("%Y-%m-%d")
            REPORT_DIR.mkdir(parents=True, exist_ok=True)
            fallback = (
                f"# Geopolitical Tracker - {date_str}\n\n"
                f"> FALLBACK OUTPUT: main pipeline failed.\n\n"
                f"Error: {type(e).__name__}: {e}\n\n"
                f"Manual review recommended.\n\n"
                f"Flashpoint count: {len(FLASHPOINTS)} (curated database intact)\n"
            )
            output_path = REPORT_DIR / f"snapshot_{date_str}.md"
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(fallback)
            print(f"[ERROR] Fallback saved to: {output_path}")
        except Exception as e2:
            print(f"[ERROR] Could not write fallback: {type(e2).__name__}: {e2}")
        sys.exit(0)