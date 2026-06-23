# NotebookLM Sources Guide: Where, What, and How Good
# -----------------------------------------------------------------------------
# PURPOSE: Reference card for building high-quality NotebookLM source packs.
#          Check this when deciding what to upload alongside our briefings.
#
# RULE: Your podcast is only as good as your sources. Garbage in, garbage out.
# =============================================================================

## SOURCE QUALITY TIERS

### TIER 1: Primary Sources (Always Trust)
Use for: Facts, official numbers, policy decisions
Upload when: Major data release, Fed meeting, geopolitical event

| Source | What to Get | URL | Free? |
|--------|-------------|-----|-------|
| **FRED (St. Louis Fed)** | Economic data, charts, API | fred.stlouisfed.org | Free |
| **BLS (Bureau of Labor Stats)** | CPI, Employment, Wages PDFs | bls.gov | Free |
| **BEA (Bureau of Econ Analysis)** | GDP, PCE, Trade PDFs | bea.gov | Free |
| **Federal Reserve** | FOMC statements, minutes, speeches | federalreserve.gov | Free |
| **EIA (Energy Information Admin)** | Oil inventories, production | eia.gov | Free |
| **SEC EDGAR** | Earnings filings, 10-K, 10-Q | sec.gov/edgar | Free |
| **BIS (Bank for Intl Settlements)** | Quarterly review, macro research | bis.org | Free |
| **IMF** | World Economic Outlook, country reports | imf.org | Free |
| **CFTC** | Commitments of Traders (positioning) | cftc.gov | Free |

### TIER 2: Major Financial Media (High Credibility)
Use for: Real-time context, market reaction, expert analysis
Upload when: You need real-world narrative to pair with our data

| Source | Strength | URL | Access |
|--------|----------|-----|--------|
| **Reuters** | Fastest, most factual. Minimal opinion. | reuters.com | Free (limited) |
| **Bloomberg** | Deepest markets coverage. Opinion section excellent. | bloomberg.com | $35/mo |
| **Financial Times** | Global perspective, excellent macro analysis | ft.com | $40/mo |
| **Wall Street Journal** | US-centric, strong Fed coverage | wsj.com | $39/mo |
| **Nikkei Asia** | Japan/Asia markets, semiconductor supply chain | asia.nikkei.com | $20/mo |
| **The Economist** | Weekly big-picture macro, excellent for context | economist.com | $25/mo |
| **Barron's** | Stock picks, market commentary | barrons.com | $5/mo |

**TIP:** You don't need all of these. Pick 1-2. Reuters (free) + The Economist ($25) 
gives you daily news + weekly deep analysis. That's enough for most source packs.

### TIER 3: Specialist Analysis (Deep Expertise)
Use for: Contrarian views, deep dives, specific asset classes
Upload when: Building a themed source pack (gold, oil, crypto, housing)

#### Macro / Strategy
| Source | Specialty | URL | Notes |
|--------|-----------|-----|-------|
| **Lyn Alden** | Fiscal dominance, monetary policy | lynalden.com | Free newsletter, excellent |
| **MacroStrategy Partnership | UK | Julian Bielski - real rates, gold | mspstrat.com | Some free |
| **Hussman Funds** | Market valuation, bubble analysis | hussmanfunds.com | Free weekly |
| **Hoisington Quarterly** | Treasury bond analysis, deflation | hoisington.com | Free quarterly |
| **Pierre-Olivier Gourinchas (IMF)** | Global macro, exchange rates | blog-imfdirect.imf.org | Free |
| **Brad Setser (CFR)** | Trade flows, dollar system | cfr.org/blog/brad-setser | Free |
| **Zoltan Pozsar (formerly CS)** | Shadow banking, dollar plumbing | Various | Search his name |
| **Alfonso Peccatiello (TFF)** | Liquidity, QT/QE, macro cycles | themacrocompass.com | Free + paid |

#### Precious Metals / Commodities
| Source | Specialty | URL |
|--------|-----------|-----|
| **Ronan Manly / BullionStar** | Physical gold/silver, LBMA | bullionstar.com/blogs |
| **Rafi Farber** | End-game inflation, monetary metals | seekingalpha.com/author |
| **Sprott** | Gold/silver mining research | sprott.com/insights |
| **GoldMoney Research** | Macro-gold analysis | research.goldmoney.com |
| **CRU Group** | Industrial metals, mining | crugroup.com |
| **Uranium Insider** | Nuclear/uranium sector | uraniuminsider.com |

#### Crypto
| Source | Specialty | URL |
|--------|-----------|-----|
| **Bankless** | Ethereum, DeFi, macro | bankless.com |
| **Glassnode Insights** | On-chain analysis | insights.glassnode.com |
| **Messari** | Crypto research, sector reports | messari.io |
| **Willy Woo** | Bitcoin on-chain, network metrics | woobull.com |

#### Geopolitics
| Source | Specialty | URL |
|--------|-----------|-----|
| **Peter Zeihan** | Demographics, geopolitics, trade | zeihan.com |
| **Eurasia Group** | Political risk assessment | eurasigroup.net |
| **War on the Rocks** | Military analysis, strategy | warontherocks.com |
| **ISW (Institute for Study of War)** | Daily Ukraine/Middle East updates | understandingwar.org |

### TIER 4: General Financial Media (Use Sparingly)
Use for: Quick headlines, NOT for source packs (too shallow)

| Source | Problem |
|--------|---------|
| CNBC | Too much noise, not enough substance |
| MarketWatch | Clickbait headlines, surface analysis |
| Seeking Alpha (general) | Quality varies wildly. Some great, most mediocre. |
| Yahoo Finance | Good for data, bad for analysis |
| Investopedia | Good for definitions, not analysis |

### TIER 5: Social Media (Ground Truth Only)
Use for: What are REAL PEOPLE feeling? (Consumer sentiment validation)

| Source | What to Extract | How |
|--------|----------------|-----|
| **Reddit r/economics** | Consumer complaints, ground-level economy | Copy top post + comments |
| **Reddit r/wallstreetbets** | Retail sentiment, positioning extremes | Copy top DD posts only |
| **Reddit r/PersonalFinance** | Real employment/housing stories | Copy relevant threads |
| **Reddit r/silverbugs** | Physical silver community sentiment | Copy weekly discussion thread |
| **Twitter/X (FinTwit)** | Fast takes, charts, real-time reactions | Screenshot or copy text |

**RULE for social media:** Only use as a CONTRARIAN indicator or ground-truth 
validation. Never use as your primary source. The wisdom of crowds is real, 
but so is the madness of crowds.

---

## SOURCE TYPES: What Format Works Best in NotebookLM

### 1. URLs (Direct Links) - BEST
NotebookLM can fetch content from URLs directly. Just paste the link.

**Best for:** Articles, blog posts, Wikipedia pages
**Tip:** Make sure the URL is to the ACTUAL ARTICLE, not a paywall landing page.
**Free articles work better than paywalled ones** (NotebookLM can't read behind paywalls).

### 2. PDF Documents - EXCELLENT
Upload government reports, research PDFs, earnings call transcripts.

**Best for:** BLS releases, Fed minutes, IMF reports, BIS papers
**Size limit:** Keep under 500KB. Large PDFs may fail or take long to process.
**Tip:** If a PDF is too large, extract just the relevant pages.

### 3. Copied Text - GOOD
Copy-paste article text directly into NotebookLM as a "pasted text" source.

**Best for:** Paywalled articles (copy the text manually), Twitter threads, 
Reddit posts, email newsletter content
**Tip:** Include the source name and date at the top of the pasted text:
```
Source: Bloomberg Opinion, June 20, 2026
Title: "Why Gold's Crisis Hedge Narrative Is Broken"
URL: [original URL]
[Copied text here]
```

### 4. YouTube Transcripts - HIDDEN GEM
You can get transcripts from YouTube videos and paste them as sources.

**How to get transcripts:**
- Method 1: On YouTube, click "..." under video -> "Show Transcript" -> copy all
- Method 2: Use a site like downsub.com oryoutubetranscript.com
- Method 3: Use a browser extension

**Best YouTube sources for transcripts:**
- Real Vision interviews (long-form macro)
- Bloomberg Markets and Finance
- Federal Reserve (official channel, Powell speeches)
- Lyn Alden, Luke Gromen, Raoul Pal interviews

### 5. Google Docs / Slides - SUPPORTED
If you have research in Google Docs, NotebookLM integrates natively.
**Best for:** Collaborative research notes, your own analysis docs.

---

## SOURCE SELECTION FRAMEWORK (30-Second Check)

Before uploading any source, ask:

```
1. IS IT SPECIFIC?
   Does it contain actual numbers, dates, and named entities?
   YES -> Good
   NO -> Skip it (too vague for AI to process meaningfully)

2. IS IT RECENT?
   Published within the last 2 weeks?
   YES -> Good for weekly briefing source packs
   NO -> Only if it's historical context (Wikipedia, prior event analysis)

3. DOES IT DISAGREE WITH OUR ANALYSIS?
   If yes -> UPLOAD IMMEDIATELY (creates podcast debate)
   If no -> Good for confirmation, but find a contrarian too

4. IS IT READABLE?
   Can NotebookLM actually access the full content?
   Free article -> YES
   Paywalled -> Only if you copy-paste the text
   Video -> Only if you get the transcript

5. IS IT CONCISE?
   Under 3,000 words? -> Good
   3,000-10,000 words? -> Acceptable but may dilute focus
   Over 10,000 words? -> Extract the key section, don't upload entire document
```

---

## SOURCE PACK RECIPES (By Topic)

### Weekly Macro Briefing Pack
```
1. reports/weekly/macro_briefing_YYYY-MM-DD.md     [Our data]
2. templates/notebooklm_discussion_guide.md          [Steering prompts]
3. Reuters article URL from this week                [Real-world context]
4. 1 contrarian: Bloomberg opinion or ZeroHedge URL  [Creates debate]
5. Wikipedia: relevant event (e.g., "2026 Iran war") [Historical depth]
```

### Fed Release Reaction Pack (CPI / Employment / FOMC)
```
1. reports/fed_releases/[release]_YYYY-MM-DD.md      [Our analysis]
2. data/fed_releases/[release].pdf                   [Original document]
3. Reuters "Factbox: Market reaction" URL             [Immediate market response]
4. 1 analyst take: Fedwatch blog or Calibrated Conf.  [Expert interpretation]
5. templates/notebooklm_discussion_guide.md          [Steering prompts]
```

### Precious Metals Deep Dive Pack
```
1. reports/research/precious_metals_YYYY-MM-DD.md     [Our analysis]
2. Ronan Manly / BullionStar latest post URL          [Physical market expert]
3. Wilshire Phoenix or Sprott research PDF            [Institutional metals]
4. Reddit r/silverbugs weekly thread (copy text)      [Retail sentiment]
5. templates/notebooklm_discussion_guide.md          [Steering prompts]
```

### Trade Thesis Pack (MNQ / Oil / Silver)
```
1. reports/trades/[asset]_thesis_YYYY-MM-DD.md        [Our setup]
2. mnq_sizing_dashboard output (copy text)            [Position sizing]
3. regime_trend_analysis output (copy text)           [Trend danger score]
4. YouTube transcript: 1 trader interview             [Human perspective]
5. templates/notebooklm_discussion_guide.md          [Steering prompts]
```

### Geopolitical Crisis Pack (Hormuz / War / Sanctions)
```
1. reports/research/hormuz_YYYY-MM-DD.md              [Our analysis]
2. ISW daily update URL                                [Military analysis]
3. Reuters energy section URL                          [Market reaction]
4. Wikipedia: relevant conflict article                [Historical context]
5. Eurasia Group risk assessment URL                   [Political risk expert]
```

---

## FREE SOURCES THAT PUNCH ABOVE THEIR WEIGHT

You don't need to spend $100+/month on Bloomberg + FT + WSJ. These free 
sources are genuinely excellent:

| Source | Why It's Great | URL |
|--------|---------------|-----|
| **FRED** | Every US economic statistic, free, downloadable | fred.stlouisfed.org |
| **Reuters (free tier)** | 10 articles/month free, top-tier journalism | reuters.com |
| **Lyn Alden newsletter** | Best free macro analysis on the internet | lynalden.com |
| **The Macro Compass** | Alfonso Peccatiello, free weekly macro | themacrocompass.com |
| **Hussman Funds weekly** | John Hussman, market valuation analysis | hussmanfunds.com |
| **Wikipedia** | Historical context, event timelines | en.wikipedia.org |
| **ISW (Institute for Study of War)** | Daily military/geopolitical updates | understandingwar.org |
| **BIS Quarterly Review** | Global banking, macro research | bis.org |
| **IMF Blog** | Global macro, country analysis | blog-imfdirect.imf.org |
| **Brad Setser blog** | Trade flows, dollar system analysis | cfr.org/blog/brad-setser |
| **r/economics top weekly** | Ground-level consumer reality | reddit.com/r/economics |
| **YouTube transcripts** | Free access to expert interviews | Various |

**With these FREE sources + our scripts, you can build world-class source packs 
without paying for any subscriptions.**

---

## PAID SOURCES: IF YOU WANT TO UPGRADE

If you have budget for 1-2 subscriptions, priority order:

1. **The Economist ($25/mo or $90/quarter)** - BEST single source for macro context
   - Weekly deep analysis across all geographies
   - Excellent for "big picture" podcast episodes
   - Copy-paste specific articles into NotebookLM

2. **Bloomberg ($35/mo)** - BEST for markets/real-time
   - Opinion section has top-tier macro analysts
   - Live markets data
   - Use for weekly briefing source packs

3. **Financial Times ($40/mo)** - BEST for global perspective
   - Excellent on Europe, Asia, EM
   - Alphaville blog is free-ish and excellent
   - Good if you want non-US-centric perspective

4. **Reuters (free tier is sufficient)** - Usually enough without paying
   - 10 free articles/month
   - Highest factual quality of any free source

**My recommendation:** The Economist ($25/mo) + free sources. That gives you 
weekly deep analysis + real-time Reuters + our data. Total spend: $25/month. 
Podcast quality: excellent.

---

## HOW TO COPY PAYWALLED CONTENT FOR NOTEBOOKLM

If you have a subscription but NotebookLM can't read the URL:

1. **Manual copy-paste:** Open the article, select all text, copy, paste into 
   NotebookLM as "Pasted Text" source. Include source name, date, title, URL.

2. **Reader mode:** Most browsers have a "Reader" mode that strips paywalls 
   for some sites. Try it.

3. **Archive.ph:** Paste a paywalled URL into archive.ph -> it creates a free 
   cached copy you can read and copy from.

4. **Newsletter format:** Many paid articles get republished in free newsletters 
   a few days later. Subscribe to free versions of paid newsletters.

---

## QUICK REFERENCE: WHAT TO GRAB EACH WEEK

```
MONDAY:   Check Reuters energy section for Hormuz/oil updates
          Save 1-2 article URLs

TUESDAY:  Check Lyn Alden / Macro Compass for any new posts
          Check BIS/IMF blogs for research papers

WEDNESDAY: Check FOMC schedule (if meeting week, prepare for statement)

THURSDAY: Jobless claims drop at 8:30am ET (FRED ICSA series)
          Check for any Fed speaker speeches

FRIDAY:   Check r/economics top posts for consumer sentiment
          Grab any interesting YouTube transcripts

SATURDAY: Run weekly_macro_briefing.py
          Assemble source pack
          Generate NotebookLM podcast
```

---

*This document is part of the LLM-First Analysis System.*
*See templates/llm_first_system.md for the complete workflow.*
