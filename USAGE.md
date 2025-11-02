# MarketPulse Usage Guide

## Quick Start

### 1. Initial Setup (One-time)

**Windows:**
```cmd
setup.bat
```

**Mac/Linux:**
```bash
chmod +x setup.sh
./setup.sh
```

### 2. Configure API Keys

Copy `config/credentials.example.yaml` to `config/credentials.yaml` and add your API keys:

```yaml
api_keys:
  alpaca:
    key_id: YOUR_ALPACA_KEY_HERE
    secret_key: YOUR_ALPACA_SECRET_HERE
```

### 3. Start MarketPulse

**Single Collection (for regular market condition updates):**
```bash
python marketpulse.py --mode collect
```

**Continuous Monitoring (run in background):**
```bash
python marketpulse.py --mode monitor
```

## What You'll See

MarketPulse provides comprehensive market internals analysis:

```
📈 MarketPulse Market Internals - 2025-11-02 21:06:20
==================================================================
🔍 MARKET OVERVIEW:
   🟢 SPY (Market): $450.25 | +1.25 (+0.28%)
   🟢 QQQ (Tech):  $180.50 | +2.15 (+1.21%)
   📈 VIX (Vol):   18.50 (NORMAL)

🧠 MARKET INTERNALS:
   • Volatility Regime: Real-time analysis based on VIX
   • Volume Flow: 60-minute accumulation tracking
   • Correlation: SPY-QQQ relationship strength
   • Support/Resistance: Dynamic levels

🎯 TRADING CONTEXT:
   🟢 Market Bias: BULLISH
   • High volatility - consider position sizing carefully
==================================================================
```

## Features Implemented

### ✅ Completed Core Features

1. **Market Data Collection**
   - Alpaca API integration for stock data
   - Real-time price tracking for SPY, QQQ, VIX, IWM
   - Historical data storage in PostgreSQL

2. **Market Internals Analysis**
   - Advance/decline line calculations
   - Volume flow analysis
   - Momentum scoring
   - Volatility regime classification
   - Support/resistance level detection

3. **Database Storage**
   - PostgreSQL with Docker
   - Price data, market internals, alerts storage
   - Historical data preservation

4. **Multi-Asset Foundation**
   - Symbol mapping for NQ, BTC, ETH
   - Extensible architecture for additional assets

### 🔄 Ready for Extension

1. **LLM Integration** - Architecture in place for LM Studio
2. **Rithmic Integration** - Client structure ready for NQ futures data
3. **Coinbase Integration** - Framework prepared for BTC/ETH data
4. **Alert System** - Database models ready, needs implementation
5. **Historical Analysis** - Data storage complete, analysis tools pending

## Database Access

View collected data:
```bash
docker exec -it marketpulse-db psql -U marketpulse -d marketpulse
```

Check latest market internals:
```sql
SELECT * FROM market_internals ORDER BY timestamp DESC LIMIT 5;
```

## System Requirements

- Docker Desktop
- Python 3.8+
- 2GB RAM minimum
- Internet connection for API calls

## API Keys Needed

1. **Alpaca** (free) - Get from [alpaca.markets](https://alpaca.markets)
2. **Rithmic** (optional) - $99/month for NQ futures data
3. **Coinbase** (optional) - For BTC/ETH data
4. **OpenRouter** (optional) - For cloud LLM fallback

## Trading Assets Supported

| Asset | Source | Status | Description |
|-------|--------|---------|-------------|
| SPY | Alpaca | ✅ Active | S&P 500 ETF (overall market) |
| QQQ | Alpaca | ✅ Active | NASDAQ ETF (tech sector) |
| VIX | Alpaca | ✅ Active | Volatility index |
| NQ | Alpaca (proxy) | ✅ Ready | NASDAQ futures tracking |
| BTC | Framework | 🔄 Planned | Bitcoin data |
| ETH | Framework | 🔄 Planned | Ethereum data |

## Troubleshooting

**Database Connection Issues:**
```bash
docker-compose down
docker-compose up -d postgres
```

**No Market Data:**
- Check Alpaca API keys are valid
- Ensure internet connection
- Verify market hours for stock data

**Import Errors:**
- Ensure virtual environment is activated
- Check all __init__.py files exist
- Verify Python path in marketpulse.py

## Next Development Steps

1. Add Rithmic client for real NQ futures data
2. Implement Coinbase client for crypto data
3. Integrate LM Studio for AI analysis
4. Build alert system for market changes
5. Create web dashboard for data visualization
6. Add automated trading signal generation

---

**Happy Trading! 📈**

MarketPulse is now ready to provide you with regular market condition updates to track how the market changes over time.