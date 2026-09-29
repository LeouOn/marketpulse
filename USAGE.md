# MarketPulse LLM Integration Guide

How MarketPulse talks to LLM providers for market analysis, data validation, and user
interaction.

> **Status:** measured 2026-09-29. See [docs/STATUS.md](docs/STATUS.md) for what works,
> what is broken, and the exact command to check each part. Provider health at a glance:
> `curl -s localhost:8000/api/llm/model-status`.

## Overview

MarketPulse routes every LLM call through a single `ModelRouter`
(`src/llm/model_router.py`) that picks a provider per capability. It provides:

- **Data Validation**: Sanity checks on market data interpretation
- **Market Analysis**: AI-powered insights on market conditions
- **Chart Interpretation**: Text-based technical analysis
- **User Interaction**: Comment and refine AI responses
- **Multi-turn Conversations**: Build on previous analysis

## Providers

The default provider is **MiniMax**. `ds4` is a supported *local* provider; DeepSeek,
OpenRouter and LM Studio are configured as fallbacks.

| Provider | Role | Endpoint | Key |
|---|---|---|---|
| **MiniMax** | **default** | `https://api.minimax.io/v1` | `MINIMAX_API_KEY` |
| `ds4` | local | `http://localhost:8001` | none |
| DeepSeek | fallback | `https://api.deepseek.com/v1` | `DEEPSEEK_API_KEY` |
| OpenRouter | fallback | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` |
| LM Studio | fallback | `http://127.0.0.1:1234/v1` (auto-detects the loaded model) | none |

The default model for every capability is `MiniMax-M3`. Change the selection with
`llm.model_routing.primary_provider` in `.env` / `config/credentials.yaml`:

```yaml
llm:
  model_routing:
    primary_provider: minimax      # minimax | deepseek | lm_studio | openrouter | ds4
    fallback_providers: deepseek,lm_studio,openrouter
```

A `ds4` local server must listen on **:8001** — the API itself uses :8000. See
[docs/local-llm-ds4.md](docs/local-llm-ds4.md).

## Quick Start

### 1. Add a key

```bash
cp .env.example .env
# then set MINIMAX_API_KEY (or whichever provider you are using)
```

### 2. Check it is reachable

```bash
curl -s localhost:8000/api/llm/model-status
```

`configured: true` means a real key was found; `false` means the value is still a
placeholder such as `your_minimax_api_key`. The endpoint also reports `healthy` per
provider once a health check has run.

### 3. Ask something

```bash
curl -s -X POST localhost:8000/api/llm/chat -H 'Content-Type: application/json' \
     -d '{"message":"In one short sentence: what is a stop loss?"}'
```

> **Known issue:** MiniMax-M3 returns its reasoning inline, so the `response` currently
> begins with a raw `<think>…</think>` block before the answer. The AI analyst strips this;
> this chat route does not yet.

## API Endpoints

### Core AI Analysis

## API Endpoints

### Core AI Analysis

#### Get AI Market Analysis
```http
GET /api/market/ai-analysis
```

**Response:**
```json
{
  "success": true,
  "data": {
    "analysis": "🤖 MiniMax-M3 (Fast Analysis):\nCurrent market shows mixed signals..."
  },
  "timestamp": "2024-01-15T10:30:00"
}
```

#### Get Dashboard with AI Insights
```http
GET /api/market/dashboard
```

**Response:**
```json
{
  "success": true,
  "data": {
    "timestamp": "2024-01-15T10:30:00",
    "marketBias": "MIXED",
    "volatilityRegime": "NORMAL",
    "symbols": { /* market data */ },
    "aiAnalysis": "🤖 MiniMax-M3 analysis..."
  }
}
```

### Data Validation

#### Run Sanity Check on Market Data
```http
GET /api/llm/validation/sanity-check
```

**Response:**
```json
{
  "success": true,
  "data": {
    "validation_result": {
      "is_valid": true,
      "issues": [],
      "confidence": 95,
      "recommendations": ["Data quality is good"],
      "summary": "Market data appears valid and consistent"
    },
    "market_data": { /* current market internals */ }
  }
}
```

### Chart Analysis

#### Analyze Text-Encoded Chart Data
```http
POST /api/llm/analyze-chart
Content-Type: application/json

{
  "chart_data": {
    "symbol": "NQ",
    "timeframe": "5m",
    "candles": [
      {
        "time": "10:00",
        "open": 15000,
        "high": 15025,
        "low": 14995,
        "close": 15020,
        "volume": 1250
      }
    ],
    "indicators": {
      "sma_20": 15010,
      "rsi": 65.5
    }
  },
  "analysis_type": "technical",
  "specific_questions": ["Is this a breakout setup?", "What's the volume pattern?"]
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "chart_analysis": "Technical analysis of the chart shows...",
    "symbol": "NQ",
    "timeframe": "5m"
  }
}
```

### User Interaction

#### Add Comment to Analysis
```http
POST /api/llm/comment
Content-Type: application/json

{
  "analysis_id": "market_analysis_20240115_103000",
  "comment": "I think the VIX level suggests more caution than the AI indicated",
  "user_id": "trader_john"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "message": "Comment added successfully",
    "comment_id": "market_analysis_20240115_103000"
  }
}
```

#### Refine Analysis Based on User Feedback
```http
POST /api/llm/refine
Content-Type: application/json

{
  "original_analysis": "Original AI analysis text...",
  "user_comments": [
    "I think the VIX level suggests more caution",
    "Can you focus more on support levels?"
  ],
  "additional_context": {
    "vix_level": 22.5,
    "key_support": 14950
  },
  "focus_areas": ["risk_assessment", "support_levels"]
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "refined_analysis": "Refined analysis incorporating user feedback...",
    "original_analysis": "Original analysis text...",
    "user_comments_count": 2
  }
}
```

#### Get Conversation History
```http
GET /api/llm/conversation-history/{analysis_id}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "analysis_id": "market_analysis_20240115_103000",
    "conversation_history": [
      {
        "type": "original_analysis",
        "content": "Initial AI analysis...",
        "timestamp": "2024-01-15T10:30:00"
      },
      {
        "type": "user_comment",
        "content": "User feedback...",
        "timestamp": "2024-01-15T10:35:00"
      },
      {
        "type": "refined_analysis",
        "content": "Refined analysis...",
        "timestamp": "2024-01-15T10:36:00"
      }
    ],
    "turns_count": 3
  }
}
```

## Python SDK Usage

### Basic Market Analysis

```python
import asyncio
from src.llm.llm_client import LLMManager

async def analyze_market():
    # Sample market data
    market_internals = {
        'spy': {'price': 450.25, 'change': 2.15, 'change_pct': 0.48},
        'qqq': {'price': 375.80, 'change': -1.25, 'change_pct': -0.33},
        'vix': {'price': 18.50, 'change': -0.75, 'change_pct': -3.89}
    }
    
    # Get AI analysis
    llm_manager = LLMManager()
    analysis = await llm_manager.analyze_market(market_internals, 'quick')
    
    print(analysis)

# Run the analysis
asyncio.run(analyze_market())
```

### Data Validation

```python
from src.llm.llm_client import LMStudioClient

async def validate_data():
    market_data = {
        'spy': {'price': 450.25, 'change': 2.15, 'volume': 45000000},
        'qqq': {'price': 375.80, 'change': -1.25, 'volume': 32000000}
    }
    
    async with LMStudioClient() as client:
        validation = await client.validate_data_interpretation(
            market_data, 
            "market_internals"
        )
        
        print(f"Valid: {validation['is_valid']}")
        print(f"Confidence: {validation['confidence']}")
        print(f"Issues: {validation.get('issues', [])}")

asyncio.run(validate_data())
```

### Chart Analysis

```python
async def analyze_chart():
    chart_data = {
        'symbol': 'NQ',
        'timeframe': '5m',
        'candles': [
            {'time': '10:00', 'open': 15000, 'high': 15025, 'low': 14995, 'close': 15020, 'volume': 1250},
            {'time': '10:05', 'open': 15020, 'high': 15045, 'low': 15010, 'close': 15035, 'volume': 1380}
        ],
        'indicators': {
            'sma_20': 15010,
            'rsi': 65.5
        }
    }
    
    async with LMStudioClient() as client:
        analysis = await client.interpret_text_chart_data(chart_data)
        print(analysis)

asyncio.run(analyze_chart())
```

### User Feedback Loop

```python
async def refine_with_feedback():
    original_analysis = "The market shows bullish sentiment..."
    
    user_comments = [
        "I think the VIX level suggests more caution",
        "Can you elaborate on support levels?"
    ]
    
    async with LMStudioClient() as client:
        # Build refinement prompt
        refinement_prompt = f"""
        Original Analysis: {original_analysis}
        
        User Feedback:
        {chr(10).join(f"- {comment}" for comment in user_comments)}
        
        Please refine the analysis addressing these points.
        """
        
        messages = [{'role': 'user', 'content': refinement_prompt}]
        
        response = await client.generate_completion(
            model='deep_analysis',
            messages=messages,
            max_tokens=400,
            temperature=0.4
        )
        
        refined_analysis = response['choices'][0]['message']['content']
        print("Refined Analysis:", refined_analysis)

asyncio.run(refine_with_feedback())
```

## Text-Based Chart Encoding

The analysis path is text-only, so encode charts as structured text:

### Candlestick Data Format
```python
chart_data = {
    'symbol': 'NQ',
    'timeframe': '5m',
    'candles': [
        {
            'time': '10:00',
            'open': 15000.00,
            'high': 15025.00,
            'low': 14995.00,
            'close': 15020.00,
            'volume': 1250
        }
    ],
    'indicators': {
        'sma_20': 15010.00,
        'sma_50': 14980.00,
        'rsi': 65.5,
        'macd': 15.2,
        'macd_signal': 12.8
    },
    'key_levels': {
        'support': [14950, 14900],
        'resistance': [15050, 15100]
    }
}
```

### Volume Profile Encoding
```python
volume_profile = {
    'price_levels': [
        {'price': 14950, 'volume': 5000, 'buys': 3000, 'sells': 2000},
        {'price': 15000, 'volume': 8000, 'buys': 4000, 'sells': 4000},
        {'price': 15050, 'volume': 3500, 'buys': 1500, 'sells': 2000}
    ],
    'point_of_control': 15000,
    'value_area_high': 15025,
    'value_area_low': 14975
}
```

## Best Practices

### 1. Data Quality Validation
Always validate data before analysis:
```python
validation = await client.validate_data_interpretation(data, "market_internals")
if validation['is_valid'] and validation['confidence'] > 80:
    analysis = await client.analyze_market_internals(data)
```

### 2. Error Handling
```python
try:
    analysis = await llm_manager.analyze_market(data, 'quick')
    if analysis is None:
        logger.warning("AI analysis failed, using fallback logic")
        # Use traditional analysis methods
except Exception as e:
    logger.error(f"LLM analysis error: {e}")
    # Handle gracefully
```

### 3. Response Validation
```python
analysis = await client.analyze_market_internals(data)
if analysis and len(analysis) > 50:  # Reasonable length check
    # Process valid analysis
else:
    logger.warning("AI analysis too short or empty")
```

### 4. User Feedback Integration
```python
# Store user comments
await db_manager.save_user_comment({
    'analysis_id': analysis_id,
    'user_id': user_id,
    'comment': user_comment,
    'timestamp': datetime.now().isoformat()
})

# Refine analysis based on feedback
refined = await client.generate_completion(
    model='deep_analysis',
    messages=[refinement_prompt],
    max_tokens=400
)
```

## Troubleshooting

### Connection Issues

**Problem**: the provider returns 401/404, or `model-status` shows `configured: false`
- **Solution**: check the provider's key is present and not the `your_…` placeholder
- **Check**: `curl -s localhost:8000/api/llm/model-status` — `configured` and `healthy` per provider
- **Verify**: the model id matches `llm.<provider>.model` in `.env` / `config/credentials.yaml`
- **Local providers only** (`ds4`, LM Studio): confirm the server is up. `ds4` must listen on
  :8001 because the API owns :8000; LM Studio serves :1234 and auto-detects its loaded model.

**Problem**: `Timeout errors`
- **Solution**: Increase timeout in config: `timeout: 60`
- **Check**: Model is fully loaded (first request can be slow)

### Response Quality Issues

**Problem**: AI responses are too generic
- **Solution**: Provide more specific context and data
- **Improve**: Use structured prompts with clear questions

**Problem**: Analysis seems incorrect
- **Solution**: Run sanity check: `GET /api/llm/validation/sanity-check`
- **Validate**: Cross-check with traditional technical analysis

### Performance Issues

**Problem**: Slow response times
- **Solution**: Use `fast_analysis` model for quick checks
- **Optimize**: Reduce `max_tokens` for shorter responses

**Problem**: High memory usage
- **Solution**: Process data in smaller chunks
- **Monitor**: for cloud providers check the provider dashboard; for local ones check the server process

## Example Workflow

### 1. Morning Market Prep
```bash
# Run sanity check on market data
curl http://localhost:8000/api/llm/validation/sanity-check

# Get comprehensive AI analysis
curl http://localhost:8000/api/market/ai-analysis
```

### 2. During Trading
```bash
# Analyze specific chart setup
curl -X POST http://localhost:8000/api/llm/analyze-chart \
  -H "Content-Type: application/json" \
  -d '{"chart_data": { "symbol": "NQ", "candles": [...] }}'

# Add trading observation
curl -X POST http://localhost:8000/api/llm/comment \
  -H "Content-Type: application/json" \
  -d '{"analysis_id": "morning_prep", "comment": "VIX spiking, caution warranted"}'
```

### 3. Post-Trade Review
```bash
# Refine analysis with actual results
curl -X POST http://localhost:8000/api/llm/refine \
  -H "Content-Type: application/json" \
  -d '{
    "original_analysis": "Morning analysis...",
    "user_comments": ["Trade worked but exit was early", "Support held perfectly"],
    "focus_areas": ["exit_timing", "support_levels"]
  }'
```

## Next Steps

1. **Test the integration**: `curl -s localhost:8000/api/llm/model-status`
2. **Ask a question**: `curl -s -X POST localhost:8000/api/llm/chat -H 'Content-Type: application/json' -d '{"message":"hello"}'`
3. **Explore the API**: Use the endpoints above or visit `http://localhost:8000/docs`
4. **Run the test suite**: `env -i HOME="$HOME" PATH="$PATH" .venv/bin/python -m pytest tests -q`

For questions or issues, check the troubleshooting section or run the test suite to diagnose connection problems.