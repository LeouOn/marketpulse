# Options Pricing Implementation for MarketPulse

## Overview

This document describes the comprehensive options pricing and analysis system implemented for MarketPulse. The implementation extends the existing MarketPulse platform with full options trading capabilities, including Greeks calculations, multi-leg strategy analysis, and macro-aware screening.

## Implementation Summary

### Components Implemented

#### 1. Core Pricing Engine (`src/analysis/options_pricing.py`)
- **Black-Scholes Model**: Full implementation for European options
- **Greeks Calculations**: Delta, Gamma, Theta, Vega, Rho
- **Implied Volatility**: Newton-Raphson method for IV calculation
- **Features**:
  - Handles dividend yields
  - Supports both calls and puts
  - Accurate time-to-expiration calculations
  - Per-day theta, per-1% vega/rho scaling

#### 2. Yahoo Finance Integration (`src/api/yahoo_client.py`)
Extended YahooFinanceClient with:
- `get_options_expirations()`: Fetch available expiration dates
- `get_options_chain()`: Retrieve full options chain data
- `get_risk_free_rate()`: Pull 10-year Treasury yield
- `get_dividend_yield()`: Get stock dividend yield

#### 3. Single Leg Analyzer (`src/analysis/options_analyzer.py`)
- **Analysis Features**:
  - Complete risk metrics (breakeven, max profit/loss)
  - Position P&L calculations
  - Probability of profit estimates
  - P&L chart generation for visualization
- **Support for**:
  - Long/short calls and puts
  - Multiple contract sizes
  - Bid/ask/mid pricing

#### 4. Multi-Leg Strategy Builder (`src/analysis/strategy_builder.py`)
Implemented strategies:
- **Covered Calls**: Income generation analysis
  - Downside protection calculation
  - Annualized return projections
  - Upside cap analysis
- **Bull Call Spreads**: Defined-risk bullish plays
- **Bear Put Spreads**: Defined-risk bearish plays
- **Features**:
  - Net Greeks for multi-leg positions
  - Risk/reward ratios
  - Breakeven calculations
  - Max profit/loss for all strategies

#### 5. Macro Context Module (`src/analysis/macro_context.py`)
- **VIX Analysis**:
  - Historical percentile calculations
  - Volatility regime classification (low, normal, elevated, high)
  - Trading implications based on VIX levels
- **Sector Performance**:
  - Relative strength vs SPY
  - Leader/laggard identification
  - 11 sector ETF tracking
- **Market Breadth**:
  - Advance/decline ratios
  - Market bias indicators
- **Risk Metrics**:
  - Treasury yield tracking
  - Correlation analysis

#### 6. Intelligent Screener (`src/analysis/options_screener.py`)
- **Screening Capabilities**:
  - OTM call/put screening with configurable delta ranges
  - Volume and open interest filters
  - Days-to-expiration filters
- **Macro-Aware Filtering**:
  - Auto-adjusts parameters based on VIX regime
  - Strategy recommendations per market conditions
  - Multi-factor opportunity scoring
- **Scoring System** (0-100 points):
  - Liquidity (20 points)
  - Probability of profit (25 points)
  - Risk/reward ratio (20 points)
  - Time value (15 points)
  - Macro context (20 points)

### API Endpoints

All endpoints return standardized `MarketResponse` format:

#### Options Chain Endpoints
```
GET /api/options/expirations/{symbol}
  - Returns: Available expiration dates

GET /api/options/chain/{symbol}/{expiration}?include_greeks=true
  - Returns: Full options chain with calculated Greeks

GET /api/options/macro-context
  - Returns: Comprehensive macro market context
```

#### Analysis Endpoints
```
POST /api/options/analyze/single-leg
  Body: {
    symbol: str,
    strike: float,
    expiration: str,
    option_type: "call" | "put",
    position_type: "long" | "short",
    contracts: int
  }
  - Returns: Complete single-leg analysis with P&L chart

POST /api/options/screen
  Body: {
    screen_type: "otm_calls" | "otm_puts",
    symbols: [str],
    min_delta: float,
    max_delta: float,
    min_days_to_expiry: int,
    max_days_to_expiry: int,
    min_volume: int,
    min_open_interest: int
  }
  - Returns: Top 20 opportunities sorted by score
```

#### Strategy Endpoints
```
POST /api/options/strategy/covered-call
  Body: {
    symbol: str,
    shares_owned: int,
    strike: float,
    expiration: str,
    contracts?: int
  }
  - Returns: Covered call analysis with annualized returns

POST /api/options/strategy/bull-call-spread
  Body: {
    symbol: str,
    long_strike: float,
    short_strike: float,
    expiration: str,
    contracts: int
  }
  - Returns: Bull call spread analysis

POST /api/options/strategy/bear-put-spread
  Body: {
    symbol: str,
    long_strike: float,
    short_strike: float,
    expiration: str,
    contracts: int
  }
  - Returns: Bear put spread analysis
```

### Database Schema

#### Options Chains Table
```sql
market_data.options_chains
  - Stores raw options chain snapshots
  - Includes market data, Greeks, theoretical pricing
  - Indexed for fast querying by symbol/expiration
```

#### Options Analysis Table
```sql
analysis.options_analysis
  - Stores analyzed strategies
  - JSONB strategy configuration
  - Risk metrics and probabilities
  - LLM recommendations
```

#### Macro Context Table
```sql
market_data.macro_context
  - VIX levels and percentiles
  - Volatility regime classification
  - Sector performance data
  - Market breadth indicators
```

#### Screening Results Table
```sql
analysis.options_screening
  - Screen criteria and results
  - Market context at time of screen
  - Top picks
```

## Usage Examples

### 1. Analyze a Single Call Option
```python
from src.api.yahoo_client import YahooFinanceClient
from src.analysis.options_analyzer import OptionsAnalyzer

client = YahooFinanceClient()
analyzer = OptionsAnalyzer(client)

analysis = analyzer.analyze_single_leg(
    symbol='AAPL',
    strike=200,
    expiration='2025-12-19',
    option_type='call',
    position_type='long',
    contracts=1
)

print(f"Breakeven: ${analysis.breakeven:.2f}")
print(f"Max Loss: ${analysis.max_loss:.2f}")
print(f"Probability of Profit: {analysis.probability_profit:.1f}%")
print(f"Delta: {analysis.greeks.delta:.3f}")
```

### 2. Screen for OTM Call Opportunities
```python
from src.api.yahoo_client import YahooFinanceClient
from src.analysis.options_screener import OptionsScreener

client = YahooFinanceClient()
screener = OptionsScreener(client)

opportunities = screener.screen_otm_calls(
    symbols=['SPY', 'QQQ', 'AAPL', 'TSLA'],
    min_delta=0.25,
    max_delta=0.40,
    min_days_to_expiry=21,
    max_days_to_expiry=45,
    min_volume=200,
    use_macro_filter=True
)

for opp in opportunities[:5]:
    print(f"{opp.symbol} ${opp.strike} exp {opp.expiration}")
    print(f"  Score: {opp.score:.1f}, Prob: {opp.probability_profit:.1f}%")
```

### 3. Analyze Covered Call
```python
from src.api.yahoo_client import YahooFinanceClient
from src.analysis.strategy_builder import StrategyBuilder

client = YahooFinanceClient()
builder = StrategyBuilder(client)

analysis = builder.analyze_covered_call(
    symbol='AAPL',
    shares_owned=100,
    strike=210,
    expiration='2025-12-19'
)

print(f"Premium: ${analysis.total_premium:.2f}")
print(f"Downside Protection: {analysis.downside_protection:.2f}%")
print(f"Return if Called: {analysis.return_if_called:.2f}%")
print(f"Annualized Return: {analysis.annualized_return:.2f}%")
```

### 4. Get Macro Context
```python
from src.api.yahoo_client import YahooFinanceClient
from src.analysis.macro_context import MacroRegime

client = YahooFinanceClient()
macro = MacroRegime(client)

context = macro.get_comprehensive_context()

vix = context['vix']
regime = context['volatility_regime']

print(f"VIX: {vix['current_level']} ({vix['percentile']}th percentile)")
print(f"Regime: {regime['regime']}")
print(f"Implications: {regime['trading_implications']}")
```

## Installation

### Dependencies
```bash
pip install -r requirements.txt
```

Key new dependencies:
- `yfinance==0.2.48`: Options data from Yahoo Finance
- `scipy==1.14.1`: Statistical functions for Black-Scholes

### Database Setup
```bash
# Run migrations to create options tables
psql -U postgres -d marketpulse -f database/02-options-tables.sql
psql -U postgres -d marketpulse -f database/03-create-indexes.sql
```

## Testing

Run the validation script:
```bash
python3 test_options.py
```

This validates:
- Black-Scholes calculations
- Module imports
- API structure
- Yahoo client extensions

## Architecture Decisions

### Why Extend MarketPulse (vs Options_Pricing)?
1. **Production Infrastructure**: MarketPulse already has FastAPI, PostgreSQL, LLM integration
2. **Python Advantages**: Better libraries for financial math (scipy, numpy)
3. **Faster Development**: Leverage existing components

### Why Yahoo Finance?
1. **Free & Comprehensive**: Full options chains, no API key required
2. **Good Data Quality**: Sufficient for retail trading decisions
3. **Easy to Upgrade**: Can add Polygon/IBKR later

### Black-Scholes Limitations
- **European Options Only**: Most US equities are American-style
- **Early Exercise**: Not modeled (usually minor for OTM options)
- **Dividends**: Handled with continuous yield approximation
- **Practical Use**: Greeks are still accurate for position management

## Future Enhancements

### Week 2 (If Continuing)
- Iron condors and iron butterflies
- Historical options data collection
- Earnings date integration
- IV crush analysis

### Week 3
- Monte Carlo simulations
- Portfolio-level Greeks
- Automated alerts system
- Broker API integration

### Week 4
- ML for IV prediction
- Unusual options activity detection
- Advanced Greeks (charm, vanna, volga)
- Multi-symbol portfolio optimization

## API Testing with cURL

### Get Options Expirations
```bash
curl http://localhost:8000/api/options/expirations/AAPL
```

### Get Options Chain
```bash
curl "http://localhost:8000/api/options/chain/AAPL/2025-12-19?include_greeks=true"
```

### Analyze Single Leg
```bash
curl -X POST http://localhost:8000/api/options/analyze/single-leg \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "AAPL",
    "strike": 200,
    "expiration": "2025-12-19",
    "option_type": "call",
    "position_type": "long",
    "contracts": 1
  }'
```

### Screen for Opportunities
```bash
curl -X POST http://localhost:8000/api/options/screen \
  -H "Content-Type: application/json" \
  -d '{
    "screen_type": "otm_calls",
    "symbols": ["SPY", "QQQ", "AAPL"],
    "min_delta": 0.25,
    "max_delta": 0.40,
    "min_days_to_expiry": 21,
    "max_days_to_expiry": 45
  }'
```

### Analyze Covered Call
```bash
curl -X POST http://localhost:8000/api/options/strategy/covered-call \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "AAPL",
    "shares_owned": 100,
    "strike": 210,
    "expiration": "2025-12-19"
  }'
```

## Performance Considerations

### Caching Strategy
- **Options Chains**: 5-minute cache for active trading
- **VIX Data**: 15-minute cache
- **Sector Performance**: 1-hour cache
- **Greeks**: Calculate on-demand (fast with scipy)

### Database Optimization
- Indexed by symbol, expiration, timestamp
- Partial indexes for specific queries
- JSONB for flexible strategy storage

### API Rate Limiting
- Yahoo Finance: Generally permissive, but consider:
  - Batch requests when possible
  - Cache aggressively during market hours
  - Implement exponential backoff on errors

## Security & Risk Disclosure

### Data Accuracy
- Yahoo Finance data is best-effort, not guaranteed
- Always verify prices before trading
- Use limit orders, never market orders based on delayed data

### Model Limitations
- Black-Scholes assumes constant volatility (not realistic)
- Doesn't account for early exercise (American options)
- Greeks are estimates, not guarantees

### Disclaimer
This software is for educational and informational purposes only. Not financial advice. Options trading involves substantial risk. Only trade with capital you can afford to lose.

## Support & Contributions

### Issues
Report bugs via GitHub issues with:
- Expected vs actual behavior
- Sample data that reproduces issue
- Environment details (Python version, OS)

### Contributing
1. Fork the repository
2. Create feature branch
3. Add tests for new functionality
4. Submit pull request

## License

[Same as MarketPulse parent project]

---

**Implementation Date**: November 15, 2025
**Primary Developer**: Claude (Anthropic)
**Version**: 1.0.0
