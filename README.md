# MarketPulse 📈

Real-time market analysis platform with AI-powered trading insights, advanced technical analysis, and comprehensive market monitoring. Built for professional traders focusing on futures and crypto derivatives.

## 🚀 Quick Start

### Prerequisites

- **Python 3.8+** - Backend API and analysis engine
- **Node.js 18+** - Next.js frontend
- **Git** - Version control

### Installation & Setup

**Windows:**
```cmd
REM 1. Clone the repository
git clone <repository-url>
cd marketpulse

REM 2. Create Python virtual environment
python -m venv venv
venv\Scripts\activate

REM 3. Install Python dependencies
pip install -r requirements-lite.txt

REM 4. Install frontend dependencies
cd marketpulse-client
npm install
cd ..

REM 5. Start the application
marketpulse.bat start
```

**Linux/macOS:**
```bash
# 1. Clone the repository
git clone <repository-url>
cd marketpulse

# 2. Create Python virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install Python dependencies
pip install -r requirements-lite.txt

# 4. Install frontend dependencies
cd marketpulse-client && npm install && cd ..

# 5. Start backend (terminal 1)
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload

# 6. Start frontend (terminal 2)
cd marketpulse-client && npm run dev
```

### Using marketpulse.bat (Windows)

The unified control script provides easy service management:

```cmd
marketpulse.bat start      REM Start backend and frontend
marketpulse.bat stop       REM Stop all services
marketpulse.bat restart    REM Restart services
marketpulse.bat status     REM Check service status
marketpulse.bat help       REM Show help
```

## 🌐 Access Points

Once running:

- **Frontend Dashboard**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **Interactive API Docs**: http://localhost:8000/redoc

## 📊 Features

### Market Analysis
- **Real-time OHLC Data**: Multi-asset price tracking (NQ, ES, BTC, ETH)
- **Technical Indicators**: Support/Resistance, RSI, MACD, ATR, Volume Profile
- **ICT Concepts**: Fair Value Gaps, Order Blocks, Liquidity Sweeps, OTE zones
- **Market Internals**: Breadth indicators, TICK, Advance/Decline ratios
- **Options Flow**: Real-time options data, unusual activity detection, Greeks

### AI Trading Assistant
- **Professional Trading Framework**: ATR-based stops, scaling strategies, entry/exit criteria
- **Market Context Awareness**: Sector analysis, breadth indicators, multi-symbol correlation
- **Hypothesis Testing**: Structured approach to validate trading ideas
- **Chart Analysis**: Technical pattern recognition and setup identification
- **Markdown Support**: Rich formatting for analysis (tables, code blocks, lists)

### Strategy Testing
- **Backtesting Engine**: Historical strategy validation with performance metrics
- **Pattern Scanner**: Automated detection of 5 pre-built strategies
- **Risk Management**: Position sizing, stop-loss placement, profit targets
- **Signal Generation**: Real-time trade setups with confidence scores

### Options Analysis
- **Options Chain Display**: Real-time calls and puts with Greeks
- **Unusual Activity**: Volume anomaly detection (Vol > 2x OI)
- **Macro Context**: VIX levels, Put/Call ratio, volatility skew
- **Multi-Symbol Support**: SPY, QQQ, IWM, AAPL, MSFT, TSLA, NVDA

## 🏗 Architecture

```
MarketPulse/
├── src/
│   ├── api/              # FastAPI backend
│   │   └── main.py       # Main API with enhanced AI system
│   ├── analysis/         # Technical analysis modules
│   │   ├── technical_indicators.py
│   │   ├── ohlc_analyzer.py
│   │   └── position_scaler.py
│   ├── llm/              # AI integration
│   │   ├── llm_client.py
│   │   └── system_prompts.py
│   └── data/             # Data collection services
│
├── marketpulse-client/   # Next.js 15 frontend
│   └── src/
│       └── components/
│           ├── ThreeColumnDashboard.tsx
│           ├── llm-chat.tsx         # AI chat with markdown
│           ├── BacktestTab.tsx
│           ├── RiskManagerTab.tsx
│           ├── OptionsFlowTab.tsx
│           └── StrategyTab.tsx
│
├── docs/                 # Documentation
│   └── archive/          # Historical documentation
│
├── marketpulse.bat       # Unified control script (Windows)
├── docker.sh             # Docker management (Linux/macOS)
└── run_tests.sh          # Test suite runner
```

## 🔑 Configuration

Create `config/credentials.yaml` from the example:

```yaml
# API Keys
polygon:
  api_key: "your_polygon_api_key"

# LLM Configuration
llm:
  primary:
    base_url: "http://127.0.0.1:1234/v1"
    api_key: "not-needed"
    model: "your-model-name"
```

## 📈 Trading Strategies

### Pre-Built Strategies
1. **FVG + Divergence**: Fair Value Gap with RSI divergence (68% win rate)
2. **ICT Kill Zone**: London/NY session setups (72% win rate)
3. **Breakout & Retest**: Structural breaks with volume confirmation (65% win rate)
4. **Reversal Patterns**: Double tops/bottoms with momentum (60% win rate)
5. **Regime-Filtered**: Only trade favorable market conditions (75% win rate)

### Risk Management Framework
- **Position Sizing**: 1-2% risk per trade maximum
- **Stop Placement**: ATR-based (1.5-2x ATR from entry)
- **Scaling In**: 50% → 25% → 25% (signal → confirmation → strength)
- **Scaling Out**: 25% at 1R → 50% at 2R → 25% runner at 3R+
- **Breakeven Rule**: Move stop to entry after TP1 hit

## 🧪 Testing

Run the comprehensive test suite:

```bash
# Linux/macOS
./run_tests.sh

# Windows (with Docker)
docker compose up -d
python -m pytest tests/
```

## 🐳 Docker Deployment (Optional)

```bash
# Start with Docker (Linux/macOS)
./docker.sh up

# Start with Docker Compose (Windows)
docker-compose up -d

# Stop services
./docker.sh down  # or: docker-compose down
```

## 📚 Documentation

- **USAGE.md**: Comprehensive API and LLM integration guide
- **docs/archive/**: Historical implementation documentation
- **API Docs**: http://localhost:8000/docs (when running)

## 🛠 Development

### Backend Development
```bash
# Activate virtual environment
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows

# Run backend with auto-reload
python -m uvicorn src.api.main:app --reload

# Run tests
pytest tests/
```

### Frontend Development
```bash
cd marketpulse-client

# Install dependencies
npm install

# Run dev server
npm run dev

# Build for production
npm run build
```

## 🎯 Trading Assets

- **Futures**: NQ (Nasdaq-100), ES (S&P 500)
- **Crypto**: BTC (Bitcoin), ETH (Ethereum)
- **Equities**: SPY, QQQ, IWM (via options)
- **Volatility**: VIX tracking

## 🔍 Key Features by Tab

### Market Overview
- Multi-asset price monitoring
- Real-time breadth indicators
- Volatility regime detection
- AI market analysis

### Backtests
- Historical strategy testing
- Performance metrics (Sharpe, win rate, profit factor)
- Drawdown analysis
- Trade-by-trade breakdown

### Risk Manager
- Position sizing calculator
- Portfolio heat tracking
- Correlation analysis
- Risk/reward optimization

### Options
- Live options chains
- Unusual volume detection
- Greeks display (Delta, Gamma, Theta, Vega)
- Macro context (VIX, P/C ratio, skew)

### Strategy
- Pattern scanning
- Signal generation
- Strategy comparison
- Performance tracking

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is proprietary. All rights reserved.

## 🆘 Support

For issues, questions, or feature requests:
1. Check the **USAGE.md** documentation
2. Review API docs at http://localhost:8000/docs
3. Check **docs/archive/** for historical context

---

**Built for traders, by traders.** Focus on edge, execution, and risk management.
