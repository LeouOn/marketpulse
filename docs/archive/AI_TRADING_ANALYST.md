

# AI Trading Analyst

## Overview

MarketPulse's AI Trading Analyst combines the power of **Massive.com's institutional-grade market data**, **Anthropic's Claude 4**, and **MarketPulse's advanced technical analysis** to create an intelligent trading assistant that understands natural language and provides actionable market insights.

## 🚀 What Makes This Special

This isn't just another chatbot. The AI Trading Analyst:

✅ **Accesses Real-Time Market Data** via Massive.com's MCP server
✅ **Reasons Like a Pro Trader** using Claude 4's advanced capabilities
✅ **Combines Multiple Analysis Systems** (divergences, ICT, risk management)
✅ **Validates Every Trade** against strict risk management rules
✅ **Provides Specific Price Levels** (entry, stop, target)
✅ **Explains Its Reasoning** step-by-step

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     AI Trading Analyst                       │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │  Massive.com │  │   Claude 4   │  │  MarketPulse    │  │
│  │  MCP Server  │  │   Sonnet     │  │  Analysis       │  │
│  │              │  │              │  │  - Divergences  │  │
│  │  - Real-time │  │  - Reasoning │  │  - ICT Concepts │  │
│  │  - Historical│  │  - Planning  │  │  - Risk Mgmt    │  │
│  │  - Options   │  │  - Tool Use  │  │  - Indicators   │  │
│  │  - News      │  │              │  │                 │  │
│  └──────────────┘  └──────────────┘  └─────────────────┘  │
│                                                              │
│              ↓                                               │
│     ┌──────────────────────┐                               │
│     │  Natural Language     │                               │
│     │  Interface            │                               │
│     │  - CLI                │                               │
│     │  - API                │                               │
│     │  - Web                │                               │
│     └──────────────────────┘                               │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Set Environment Variables

```bash
export MASSIVE_API_KEY="your_massive_api_key"
export ANTHROPIC_API_KEY="your_anthropic_api_key"
```

Get API keys:
- **Massive.com**: https://massive.com (generous free tier)
- **Anthropic**: https://console.anthropic.com

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

Key dependencies:
- `pydantic-ai==0.0.14` - AI agent framework
- `anthropic==0.39.0` - Claude 4 API
- `rich==13.9.4` - Beautiful terminal formatting

### 3. Run Interactive CLI

```bash
python scripts/ai_analyst_cli.py
```

### 4. Or Use the API

```bash
# Start the API server
uvicorn src.api.main:app --reload

# Query the AI
curl "http://localhost:8000/api/ai/query/AAPL?question=Should+I+buy+this+stock?"
```

## Usage Examples

### Example 1: Basic Stock Analysis

**Question:**
```
How is AAPL performing right now compared to MSFT?
```

**AI Response:**
```
Based on the latest data from Massive.com:

AAPL (Apple Inc.):
- Current Price: $178.45 (+2.3% today)
- 52-week range: $164.08 - $199.62
- Market Cap: $2.8T
- P/E Ratio: 29.4

MSFT (Microsoft Corp.):
- Current Price: $378.91 (+1.8% today)
- 52-week range: $309.45 - $384.30
- Market Cap: $2.8T
- P/E Ratio: 36.2

Comparison:
- Both are outperforming the market today
- AAPL showing stronger momentum (+2.3% vs +1.8%)
- MSFT trading near all-time highs
- AAPL has better value (lower P/E)

Technical Analysis (MarketPulse):
- AAPL: Bullish divergence detected on daily chart (RSI strength: 82)
- MSFT: Neutral, consolidating near highs

Recommendation: AAPL shows better risk-reward currently due to the bullish divergence and lower valuation.
```

### Example 2: Futures Trading Setup

**Question:**
```
Give me a complete trading setup for MNQ futures
```

**AI Response:**
```
MNQ (Micro E-mini Nasdaq-100 Futures) Trading Setup

Current Market Analysis:
- Price: $16,245
- Trend: Bullish (above 20 EMA and 50 SMA)
- Divergence: Hidden bullish divergence on 15m chart (continuation signal)
- ICT: Bullish Fair Value Gap at $16,180-$16,200 (support zone)

Trade Recommendation:
Direction: LONG
Entry: $16,220 (on pullback to FVG)
Stop Loss: $16,160 (below FVG)
Take Profit: $16,340 (recent high resistance)
Contracts: 2

Risk Management:
- Risk per contract: $60 (16,220 - 16,160) × $2/point = $120
- Reward per contract: $120 (16,340 - 16,220) × $2/point = $240
- Risk-Reward Ratio: 1:2 ✅
- Total risk: $240 (2.4% of $10,000 account) ✅

Entry Criteria:
1. Wait for price to pull back to $16,200-$16,220 (FVG zone)
2. Look for bullish candle close above $16,220
3. Enter on next candle open

Exit Plan:
- Take 50% profit at $16,280 (1:1)
- Move stop to breakeven
- Let remaining 50% run to $16,340

Invalidation:
- Close below $16,160 (exit immediately)
- If price doesn't pull back to entry zone within 2 hours, look for new setup

Trade validated against risk management: ✅ APPROVED
```

### Example 3: Divergence Analysis

**Question:**
```
Analyze SPY for divergences and tell me if it's a good short
```

**AI Response:**
```
SPY Divergence Analysis

MarketPulse Divergence Scan Results:
- Total Divergences: 3
- Signal: STRONG_BEARISH

Detected Divergences:
1. RSI Regular Bearish (Strength: 88/100)
   - Price: Higher high ($452.30 vs $448.20)
   - RSI: Lower high (68.2 vs 72.5)
   - Interpretation: Strong reversal signal

2. MACD Bearish (Strength: 75/100)
   - Price making new highs
   - MACD histogram declining
   - Momentum weakening

3. OBV Bearish (Strength: 92/100)
   - Price higher
   - Volume declining
   - Distribution pattern

Technical Context:
- Current Price: $452.30
- Trend: Uptrend but weakening
- Recent High: $452.30 (today)
- Support: $446.00 (20-day SMA)

Is This a Good Short?

YES - High probability short setup

Reasoning:
1. Multiple bearish divergences confirm each other
2. Volume divergence (OBV) is especially strong (92/100)
3. Price near resistance
4. Momentum declining despite new highs

Recommended Short Setup:
Entry: $451.50 (on break below today's low)
Stop: $453.50 (above today's high)
Target 1: $446.00 (20 SMA support)
Target 2: $442.00 (50 SMA)

Risk: $2.00/share
Reward: $9.50/share (to Target 2)
R:R: 1:4.75 ✅

Timing: Wait for confirmation (break below $451.50)
Don't short blindly - let price confirm the reversal
```

### Example 4: Long-Term Investment

**Question:**
```
Compare META, AMZN, and GOOGL for a 5-year investment
```

**AI Response:**
```
5-Year Investment Analysis: META vs AMZN vs GOOGL

Historical Performance (Last 5 Years):
- META: +156% total return (20.6% annualized)
- AMZN: +87% total return (13.3% annualized)
- GOOGL: +124% total return (17.5% annualized)

Current Valuation Metrics:
META:
- P/E: 24.8 (most attractive)
- Forward P/E: 22.1
- PEG Ratio: 1.2
- Profit Margin: 29.4%

AMZN:
- P/E: 52.3 (expensive)
- Forward P/E: 38.4
- PEG Ratio: 2.1
- Profit Margin: 6.3%

GOOGL:
- P/E: 28.9
- Forward P/E: 24.2
- PEG Ratio: 1.4
- Profit Margin: 26.7%

Growth Prospects:
- META: AI integration, Metaverse, strong ad business
- AMZN: AWS growth, e-commerce dominance, logistics network
- GOOGL: AI leadership, search monopoly, cloud growth

Risk Assessment:
- META: Regulatory risks, user growth concerns
- AMZN: Competition, margin pressure
- GOOGL: Antitrust, search disruption (AI)

Recommendation: META

Reasoning:
1. Best value (lowest P/E and PEG)
2. Highest profit margins
3. Strong AI positioning
4. Best historical returns
5. Multiple revenue streams

However, for diversification, consider:
- 50% META (value + growth)
- 30% GOOGL (AI leader)
- 20% AMZN (AWS growth)

This balances value, growth, and risk across the tech sector.
```

## API Endpoints

### POST /api/ai/query

Query the AI analyst with natural language.

**Request:**
```json
{
  "question": "Should I buy Tesla?",
  "symbol": "TSLA",
  "timeframe": "1d",
  "period": "3mo",
  "include_technical_analysis": true
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "question": "Should I buy Tesla?",
    "response": "Based on analysis... [detailed response]",
    "timestamp": "2024-11-16T12:00:00"
  }
}
```

### GET /api/ai/query/{symbol}

Simple GET endpoint for symbol analysis.

**Example:**
```bash
curl "http://localhost:8000/api/ai/query/AAPL?question=Give me a trade setup"
```

### POST /api/ai/recommend

Get complete trade recommendation.

**Request:**
```json
{
  "symbol": "MNQ",
  "timeframe": "5m",
  "period": "1d",
  "account_size": 10000.0,
  "risk_per_trade": 0.02
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "symbol": "MNQ",
    "recommendation": "Complete trade setup with entry, stop, target...",
    "timestamp": "2024-11-16T12:00:00"
  }
}
```

### GET /api/ai/recommend/{symbol}

Get trade recommendation (simple GET).

**Example:**
```bash
curl "http://localhost:8000/api/ai/recommend/AAPL"
```

### POST /api/ai/validate

Validate a trade against risk management rules.

**Request:**
```json
{
  "symbol": "MNQ",
  "entry_price": 16220.0,
  "stop_loss": 16160.0,
  "take_profit": 16340.0,
  "direction": "LONG",
  "contracts": 2
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "approved": true,
    "reason": "Trade meets all risk management criteria",
    "risk_amount": 240.0,
    "reward_amount": 480.0,
    "risk_reward_ratio": 2.0,
    "position_size": 2
  }
}
```

### GET /api/ai/status

Check AI analyst status.

**Response:**
```json
{
  "success": true,
  "data": {
    "massive_api_configured": true,
    "anthropic_api_configured": true,
    "agent_initialized": true,
    "message_history_length": 4,
    "features": {
      "divergence_detection": true,
      "ict_analysis": true,
      "risk_management": true,
      "technical_indicators": true,
      "massive_mcp_server": true
    }
  }
}
```

## Python Client Example

```python
import asyncio
from src.ai.massive_analyst import MassiveAIAnalyst, TradingContext

async def main():
    # Initialize analyst
    analyst = MassiveAIAnalyst()
    await analyst.create_agent()

    # Simple query
    response = await analyst.query("How is AAPL doing today?")
    print(response)

    # Query with context
    context = TradingContext(
        symbol="MNQ",
        timeframe="5m",
        period="1d"
    )

    response = await analyst.query(
        "Give me a scalping setup",
        context=context,
        include_technical_analysis=True
    )
    print(response)

    # Get trade recommendation
    recommendation = await analyst.get_trade_recommendation("AAPL")
    print(recommendation['recommendation'])

    # Validate a trade
    validation = await analyst.validate_trade(
        symbol="MNQ",
        entry_price=16220.0,
        stop_loss=16160.0,
        take_profit=16340.0,
        direction="LONG",
        contracts=2
    )

    if validation['approved']:
        print(f"✅ Trade approved! R:R = {validation['risk_reward_ratio']:.2f}")
    else:
        print(f"❌ Trade rejected: {validation['reason']}")

if __name__ == '__main__':
    asyncio.run(main())
```

## How It Works

### 1. MCP Server Integration

The Massive.com MCP (Model Context Protocol) server exposes market data as "tools" that Claude 4 can use:

```python
def create_massive_mcp_server(self):
    return MCPServerStdio(
        command="uvx",
        args=[
            "--from",
            "git+https://github.com/massive-com/mcp_massive@v0.4.0",
            "mcp_massive"
        ],
        env={'MASSIVE_API_KEY': self.massive_api_key}
    )
```

Available tools include:
- Get current stock prices
- Get historical data
- Get options chains
- Get market news
- Get financial statements
- And more...

### 2. AI Agent with Claude 4

Pydantic AI creates a structured agent:

```python
self.agent = Agent(
    model="anthropic:claude-sonnet-4-20250514",
    mcp_servers=[massive_mcp_server],
    system_prompt=trading_expert_prompt
)
```

Claude 4 can:
- Understand natural language questions
- Formulate analysis plans
- Call appropriate tools (Massive.com data)
- Reason about the results
- Provide structured recommendations

### 3. MarketPulse Integration

The AI automatically runs technical analysis:

```python
# Divergence detection
divergences = scan_for_divergences(df, min_strength=70.0)

# ICT analysis
fvgs = self.ict_analyzer.detect_fair_value_gaps(df)
order_blocks = self.ict_analyzer.detect_order_blocks(df)

# Technical indicators
trends = identify_trends(df_with_indicators)
```

This data is injected into the AI's context for comprehensive analysis.

### 4. Risk Management Validation

Every trade is validated:

```python
validation = self.risk_manager.validate_trade(
    symbol=symbol,
    entry_price=entry,
    stop_loss=stop,
    take_profit=target,
    direction=direction,
    contracts=size
)
```

The AI won't recommend trades that violate risk rules.

## Best Practices

### 1. Be Specific in Your Questions

**Good:**
> "Give me a long entry for MNQ on the 5-minute chart with specific entry, stop, and target prices"

**Bad:**
> "What about MNQ?"

### 2. Provide Context

**Good:**
> "I'm swing trading with $50,000 account. What's a good risk-reward setup for AAPL over the next 1-2 weeks?"

**Bad:**
> "Is AAPL good?"

### 3. Ask for Validation

Always ask the AI to validate trades:

```
"Validate this trade:
Entry: $16,220
Stop: $16,160
Target: $16,340
Direction: LONG
Contracts: 2"
```

### 4. Combine Multiple Analysis Types

```
"Analyze SPY for:
1. Divergences on the daily chart
2. ICT Fair Value Gaps
3. Key support/resistance levels
4. Give me a short setup if bearish"
```

### 5. Use Conversation History

The AI remembers your conversation:

```
You: "Analyze AAPL"
AI: [provides analysis]

You: "Now compare it to MSFT"
AI: [compares, remembering AAPL analysis]

You: "Which is better for a swing trade?"
AI: [recommends based on both analyses]
```

## Advanced Features

### Multi-Timeframe Analysis

```python
"Analyze MNQ on three timeframes:
- Daily for overall trend
- 4-hour for intermediate structure
- 5-minute for entry timing

Give me the best entry setup that aligns all three."
```

### Sector Comparison

```python
"Compare all FAANG stocks (META, AAPL, AMZN, NFLX, GOOGL) and tell me which has:
1. Best technical setup
2. Best value
3. Best momentum
Rank them 1-5."
```

### Risk-Adjusted Recommendations

```python
"I have $25,000 account and want to risk 1.5% per trade.
Give me 3 different trade setups (stocks or futures) with different risk profiles:
- Conservative (high win rate, lower R:R)
- Moderate (balanced)
- Aggressive (lower win rate, higher R:R)"
```

### Earnings Analysis

```python
"AAPL earnings are tomorrow after close. Based on:
- Recent price action
- Historical earnings moves
- Current technical setup
- Options implied volatility

Should I:
1. Go long before earnings?
2. Wait for post-earnings dip?
3. Avoid completely?"
```

## Limitations

1. **Not Financial Advice**: The AI provides analysis, not personalized financial advice
2. **Data Latency**: Real-time data has slight delay (usually <1 second with Massive.com)
3. **No Guarantees**: Past performance doesn't guarantee future results
4. **Requires Validation**: Always validate AI recommendations with your own analysis
5. **API Costs**: Massive.com and Anthropic APIs have usage costs (generous free tiers available)

## Troubleshooting

### "Anthropic API key required"

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

### "Massive.com MCP server disabled"

```bash
export MASSIVE_API_KEY="your_key"
```

Or use Yahoo Finance (free but limited):
- AI will still work
- Uses Yahoo Finance instead of Massive.com
- Less data coverage

### "uvx command not found"

Install uv:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Agent initialization slow

First query is slow (15-30 seconds) as it:
- Initializes MCP server
- Loads AI model
- Fetches initial data

Subsequent queries are fast (2-5 seconds).

## Cost Estimate

### Free Tier (Testing)
- **Massive.com**: 1,000 API calls/month free
- **Anthropic**: $5 free credit (Claude 4: ~$3/million input tokens)
- **Estimated monthly cost**: $0 for light usage

### Production Usage
- **Massive.com**: $99/month (unlimited calls)
- **Anthropic**: ~$50-100/month (heavy usage)
- **Total**: ~$150-200/month

This gives you institutional-grade data + frontier AI - much cheaper than Bloomberg Terminal ($2,000/month).

## Roadmap

Future enhancements:

- [ ] WebSocket for streaming analysis
- [ ] Portfolio optimization
- [ ] Backtesting integration
- [ ] Multi-asset correlation analysis
- [ ] Sentiment analysis from news
- [ ] Automated trade execution (with approval)
- [ ] Performance tracking and learning
- [ ] Custom strategy builder

## Contributing

Want to improve the AI Trading Analyst?

1. Add new technical indicators
2. Enhance system prompts
3. Create specialized agents (scalping, swing, options)
4. Integrate additional data sources
5. Improve error handling

## License

This AI Trading Analyst is part of MarketPulse and follows the same license.

## Disclaimer

**The AI Trading Analyst is a tool for analysis and education. All trading involves risk. Never trade with money you can't afford to lose. Always do your own research and consider seeking advice from a licensed financial advisor.**

---

Built with ❤️ by the MarketPulse team

Powered by:
- [Massive.com](https://massive.com) - Institutional market data
- [Anthropic Claude 4](https://www.anthropic.com) - Advanced AI
- [Pydantic AI](https://github.com/pydantic/pydantic-ai) - AI agent framework
- [MarketPulse](https://github.com/yourusername/marketpulse) - Technical analysis platform
