# MarketPulse - Real-Time Market Internals Analysis

A comprehensive market internals analysis system for NQ, BTC, and ETH trading with AI-powered insights.

## Overview

MarketPulse provides real-time analysis of market internals to help identify important levels, signals, and trading opportunities. The system integrates with multiple data sources and uses LLMs to provide intelligent market analysis.

## Features

- **Real-time Market Data Collection** from Alpaca, Rithmic, and Coinbase
- **PostgreSQL Database** for historical data storage and analysis
- **AI-Powered Insights** via LM Studio integration
- **Multi-Asset Support** for NQ, BTC, and ETH
- **Market Internals Calculation** including breadth, momentum, and volume flow
- **Alert System** for significant market condition changes

## Architecture

```
MarketPulse/
├── database/          # Database schemas and migrations
├── src/              # Main source code
│   ├── api/          # API integration modules
│   ├── core/         # Core business logic
│   ├── data/         # Data collection services
│   ├── analysis/     # Market analysis engine
│   └── llm/          # LLM integration
├── config/           # Configuration files
├── scripts/          # Utility scripts
├── tests/            # Test suites
└── docs/             # Documentation
```

## Quick Start

1. **Start Database**:
   ```bash
   docker-compose up -d
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure APIs**:
   - Copy `config/credentials.example.yaml` to `config/credentials.yaml`
   - Add your API keys

4. **Run Market Monitor**:
   ```bash
   python -m src.core.market_monitor
   ```

## Data Sources

- **Alpaca**: Stock market data (SPY, QQQ, etc.)
- **Rithmic**: Real-time futures data (NQ)
- **Coinbase**: Cryptocurrency data (BTC, ETH)
- **Yahoo Finance**: Additional market data (VIX, etc.)

## LLM Integration

- **Primary**: LM Studio (local models)
- **Fallback**: OpenRouter (cloud APIs)
- **Models**: Qwen3-30B-A3B (fast), GLM-4.5-air (analysis)

## Trading Assets

- **NQ**: E-mini Nasdaq-100 futures (primary focus)
- **BTC**: Bitcoin (perpetual contracts)
- **ETH**: Ethereum (perpetual contracts)

## Market Internals

- Market breadth analysis
- Volume flow indicators
- Momentum oscillators
- Correlation analysis
- Volatility regimes
- Support/resistance levels

Built for real-time trading decision support.