# LLM-First Analysis System: The Complete Workflow
# -----------------------------------------------------------------------------
# This document describes the system for generating AI-optimized analysis
# documents that feed into NotebookLM podcasts, LLM follow-ups, and human reading.
#
# The core principle: WRITE FOR THE AI, READ AS A HUMAN.
# =============================================================================

## SYSTEM ARCHITECTURE

```
Data Sources          Our Tools              LLM-First Output          AI Consumption
===============       ===========            ================          ==============
FRED (macro)    \                           /-- Weekly Briefing  -->  NotebookLM Podcast
Yahoo (markets) ---> Python scripts  --->  |-- Fed Reaction     -->  NotebookLM Podcast
EIA (oil)       /    (in /scripts/)        |-- Trade Thesis     -->  ChatGPT/Claude Q&A
News (manual)   /                          |-- Research Deep Dive ->  NotebookLM Study Guide
                                             \-- Discussion Guide  -->  NotebookLM Custom Prompt
```

## DOCUMENT TYPES (5 Formats)

### 1. Weekly Macro Briefing (every Saturday)
**Script:** `scripts/weekly_macro_briefing.py`
**Output:** `reports/weekly/macro_briefing_YYYY-MM-DD.md`
**Length:** 1,500-2,000 words (10-15 min podcast)
**Upload to:** NotebookLM (with discussion guide)
**Format:** Structured markdown with specific numbers, tensions, and questions

### 2. Fed Release Reaction (when data drops)
**Template:** `templates/fed_release_reaction.md`
**Output:** `reports/fed_releases/[release]_YYYY-MM-DD.md`
**Length:** 800-1,200 words (5-8 min podcast)
**Trigger:** CPI, Employment, PCE, GDP, FOMC
**Upload to:** NotebookLM (with that week's briefing for context)

### 3. Trade Thesis (when you're considering a position)
**Template:** (create as needed)
**Output:** `reports/trades/[asset]_thesis_YYYY-MM-DD.md`
**Length:** 500-1,000 words
**Content:** Setup, entry, stop, targets, risk/reward, regime context
**Upload to:** NotebookLM OR just read yourself

### 4. Research Deep Dive (multi-asset or thematic)
**Examples:** Bay Area housing, precious metals, Hormuz oil, HK property
**Output:** `reports/research/[topic]_YYYY-MM-DD.md`
**Length:** 2,000-5,000 words
**Upload to:** NotebookLM (as a standalone notebook for that topic)

### 5. Discussion Guide (the "steering wheel")
**Template:** `templates/notebooklm_discussion_guide.md`
**Purpose:** Tells NotebookLM what to debate, what questions to explore
**Usage:** Upload alongside any other document for richer podcasts

## NOTEBOOKLM OPTIMIZATION: THE SOURCE PACK

### What is a Source Pack?
A collection of 3-5 documents/URLs that you upload to ONE NotebookLM notebook 
to generate a podcast. The combination matters more than any single source.

### The Formula

```
Source Pack = 
  1x Our Analysis (weekly briefing or fed reaction)
  + 1x Real-world article (Reuters, Bloomberg, FT link)
  + 1x Contrarian view (someone who disagrees with us)
  + 1x Discussion guide (steering the podcast)
  + 0-1x Historical context (Wikipedia article, prior event)
```

### Example: This Week's Hormuz Source Pack

1. `reports/weekly/macro_briefing_2026-06-20.md` (our analysis)
2. Reuters article URL: "Oil shipments rise in Hormuz" (real-world)
3. Wikipedia: "2026 Strait of Hormuz crisis" (historical context)
4. Bloomberg opinion piece URL: "Why oil at $200 is wrong" (contrarian)
5. `templates/notebooklm_discussion_guide.md` (steering)

### Why 3-5 Sources?
- 1 source = boring monologue podcast
- 2 sources = slightly better but still thin
- 3-5 sources = rich debate between hosts, multiple perspectives
- >5 sources = hosts get confused, lose focus

## NOTEBOOKLM FEATURES BEYOND PODCASTS

### 1. Audio Overview (Podcast)
- The main feature you use
- Two AI hosts discuss your sources
- ~10 minutes per podcast
- TIP: Use "Customize" to steer the conversation

### 2. Q&A Chat
- Ask questions about your uploaded sources
- Use the discussion questions from our templates
- Great for follow-up after listening to the podcast
- TIP: Ask "What evidence would change this conclusion?" for deeper analysis

### 3. Study Guide
- Auto-generated FAQ, key terms, timeline
- Good for learning a new topic quickly
- TIP: Upload 5 sources on a topic you don't understand, generate study guide

### 4. Mind Map
- Visual map of how concepts connect
- Good for seeing relationships between macro factors
- TIP: Upload a complex briefing, generate mind map to see the structure

## NOTEBOOKLM CUSTOM PROMPTS (Copy-Paste Library)

### For Macro Briefings:
```
Create a podcast focused on the TENSIONS in this data. The hosts should disagree 
on at least 2 topics. Use specific numbers (unemployment 4.1%, CPI 2.7%, gold 
$4,173/oz). Reference real events (Iran war, Fed rate cuts). End with what each 
host is watching next week. Keep it conversational, not academic.
```

### For Fed Release Reactions:
```
Create a podcast where two analysts react to this economic release in real-time. 
One should be bullish (sees the good news), one should be bearish (sees the risks). 
Debate whether the Fed will change course. Use specific numbers from the data. 
Reference what the market did immediately after the release.
```

### For Research Deep Dives:
```
Create an educational podcast that teaches the listener about this topic. Start 
with the basics, build to the advanced analysis. Use analogies. Reference the 
specific data points. End with "what should the listener DO with this information?"
```

### For Trade Setups:
```
Create a podcast where two traders debate this trade idea. One argues for the 
trade, one argues against. Discuss entry, stop, targets, and risk management. 
Reference the macro regime and trend danger score. Be specific about position 
sizing for a $50,000 futures account.
```

## THE WEEKLY ROUTINE (15 Minutes, Once a Week)

### Saturday Morning (Preparation)

```bash
# 1. Generate this week's briefing
python scripts/weekly_macro_briefing.py

# 2. Output: reports/weekly/macro_briefing_YYYY-MM-DD.md
```

### Saturday Afternoon (NotebookLM)

1. Go to notebooklm.google.com
2. Create new notebook (or use existing "Weekly Macro" notebook)
3. Upload sources:
   - `reports/weekly/macro_briefing_YYYY-MM-DD.md`
   - `templates/notebooklm_discussion_guide.md`
   - 1-2 URLs from this week's news
4. Customize: paste the custom prompt from the discussion guide
5. Generate Audio Overview (podcast)
6. While it generates, scroll through the Q&A and Study Guide

### Sunday Evening (Review)

1. Listen to the podcast
2. Ask NotebookLM follow-up questions
3. Note anything that surprised you
4. Come back to me (ChatGPT/Claude/this session) with follow-up questions

### Monday Morning (Action)

1. Check if anything changed over the weekend (Hormuz, Fed speakers)
2. Run the MNQ dashboard: `python scripts/mnq_sizing_dashboard.py`
3. Check trend danger score
4. Execute the week's plan

## DIVERSE LEARNING SOURCES (Beyond Our Analysis)

### AI Podcasts (for variety):
- **NotebookLM** (your own custom podcasts from our data)
- **Google Daily AI Podcast** (if available in your region)
- **ChatGPT Voice Mode** (conversational Q&A about markets)

### YouTube Channels by Category:

**Macro / Economics:**
- Real Vision (Raoul Pal) - macro cycles, crypto
- Lyn Alden - fiscal dominance, monetary policy
- Peter Boockvar - inflation, Fed analysis
- Cam Harvey (Duke) - recession indicators, yield curve

**Trading / Technical:**
- TraderXO - technical analysis, S&P levels
- Imbalance Trader - order flow, market structure
- Mark Douglas (psychology) - trading discipline

**Precious Metals / Commodities:**
- Ronan Manly / BullionStar - physical gold/silver
- Rafi Farber - inflation, monetary debasement
- CRU Group - industrial metals, mining

**Crypto:**
- Bankless - Ethereum/DeFi
- Pomp Podcast - Bitcoin macro
- Coin Bureau - crypto education

**Geopolitics:**
- Peter Zeihan - demographics, geopolitics
- Real Life Lore - geographic analysis
- Caspian Report - regional conflicts

### How to Combine Sources:
1. Listen to 1-2 YouTube videos on a topic
2. Download the transcript (use YouTube transcript tools)
3. Upload transcript + our analysis to NotebookLM
4. Generate a podcast that COMBINES the YouTuber's view with our data
5. You get a synthesis of human + AI analysis

## DIRECTORY STRUCTURE

```
marketpulse/
  scripts/
    weekly_macro_briefing.py        # Weekly macro snapshot generator
    mnq_sizing_dashboard.py         # MNQ position sizing tool
    regime_trend_analysis.py        # Counter-trend danger scoring
    precious_metals_deep_dive.py    # Metals comparison
    silver_crash_probability.py     # Silver entry timing
    employment_deep_dive.py         # Labor market detail
    [all other analysis scripts]
  
  templates/
    notebooklm_discussion_guide.md  # Steering document for podcasts
    fed_release_reaction.md         # Template for Fed data analysis
    llm_first_system.md             # This document
  
  reports/
    weekly/
      macro_briefing_YYYY-MM-DD.md  # Generated each Saturday
    
    fed_releases/
      [release]_YYYY-MM-DD.md       # Generated when data drops
    
    research/
      [topic]_YYYY-MM-DD.md         # Deep dive analysis
    
    trades/
      [asset]_thesis_YYYY-MM-DD.md  # Trade setup documentation
    
    notebooklm/
      source_pack_YYYY-MM-DD.md     # Combined source pack for upload
  
  data/
    macro/                          # FRED cached data
    yahoo_cache/                    # Yahoo Finance cached data
    fed_releases/                   # Downloaded PDFs from Fed/BLS/BEA
      2026-06/
        CPI_2026-06.pdf
        Employment_2026-06.pdf
```

## THE FEEDBACK LOOP

```
You ask me questions
        |
        v
I generate analysis (scripts + MD documents)
        |
        v
Documents saved to reports/
        |
        v
You upload to NotebookLM + customize prompt
        |
        v
NotebookLM generates podcast
        |
        v
You listen, learn, form new questions
        |
        v
You come back with better questions
        |
        v
[Cycle repeats, each iteration deeper]
```

Each cycle, the analysis gets richer because:
1. We have more historical data cached
2. The templates get refined based on what works
3. The podcast prompts get better tuned
4. You learn what questions to ask
5. I learn what output format serves you best

## VERSION CONTROL

All reports and templates should be version-controlled (git). This means:
- Every weekly briefing is saved permanently
- You can compare "what did we think in March vs June?"
- NotebookLM notebooks can reference historical briefings
- Templates evolve with a clear history

Commit weekly: `git add reports/ templates/ && git commit -m "weekly briefing YYYY-MM-DD"`
