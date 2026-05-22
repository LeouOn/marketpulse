# MarketPulse 📈

Real-time market analysis platform with AI-powered trading insights, OHLC technical analysis, and comprehensive market internals monitoring.

## 🚀 Quick Start

### Prerequisites

- **Python 3.8+** - For the backend API
- **Node.js 16+** - For the Next.js frontend
- **Docker & Docker Compose** - For containerized deployment (optional)

### Option 1: Automated Setup (Recommended)

#### Windows PowerShell
```powershell
# One-time setup
.\scripts\setup.ps1

# Start development servers
.\scripts\dev.ps1

# Or start with Docker
.\scripts\docker.ps1 -Action up
```

#### Linux/macOS (Bash)
```bash
# One-time setup
./scripts/setup.sh

# Start development servers
./scripts/dev.sh

# Or start with Docker
./scripts/docker.sh up
```

#### Make (Cross-platform)
```bash
# One-time setup
make install

# Start development servers
make dev

# Or start with Docker
make docker-up
```

### Option 2: Manual Setup

1. **Clone and setup environment**
```bash
git clone <repository>
cd marketpulse

# Python virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\Activate     # Windows

# Install dependencies
pip install -r requirements-lite.txt
cd marketpulse-client && npm install && cd ..
```

2. **Start development servers**
```bash
# Backend (http://localhost:8000)
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend (http://localhost:3000) - in separate terminal
cd marketpulse-client && npm run dev
```

## 🌐 Access Points

Once running, access the application at:

- **Frontend Dashboard**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **Interactive API**: http://localhost:8000/redoc

## 📊 Features

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