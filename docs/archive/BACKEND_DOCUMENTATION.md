# MarketPulse Backend Documentation

## Architecture Overview

The MarketPulse backend is a Python-based FastAPI application that provides real-time market data collection, AI-powered analysis, and API endpoints for the frontend.

### System Components

```
Backend Architecture
├── FastAPI Application (src/api/main.py)
│   ├── REST API Endpoints
│   ├── WebSocket Real-time Updates
│   └── LLM Integration
├── Market Data Collection (src/data/market_collector.py)
│   ├── Alpaca API Integration
│   ├── Real-time Data Processing
│   └── Database Storage
├── Database Layer (src/core/database.py)
│   ├── PostgreSQL Connection
│   ├── Data Models
│   └── Query Interface
├── LLM Services (src/llm/)
│   ├── Enhanced LLM Client
│   ├── Knowledge RAG System
│   └── Hypothesis Testing
└── Configuration Management (src/core/config.py)
```

## API Endpoints

### Core Market Data Endpoints

#### GET `/api/market/internals`
**Description:** Get current market internals data

**Response:**
```json
{
  "success": true,
  "data": {
    "spy": {"price": 450.25, "change": 2.15, "change_pct": 0.48, "volume": 45000000},
    "qqq": {"price": 375.80, "change": -1.25, "change_pct": -0.33, "volume": 32000000},
    "vix": {"price": 18.50, "change": -0.75, "change_pct": -3.89},
    "volume_flow": {"total_volume_60min": 77000000, "symbols_tracked": 3}
  },
  "timestamp": "2024-01-15T10:30:00"
}
```

**Areas for Enhancement:**
- [ ] Add caching layer (Redis) for frequently accessed data
- [ ] Implement rate limiting per user/IP
- [ ] Add data compression for large responses
- [ ] Implement pagination for historical data

#### GET `/api/market/dashboard`
**Description:** Get dashboard data with AI analysis and market bias

**Response:**
```json
{
  "success": true,
  "data": {
    "timestamp": "2024-01-15T10:30:00",
    "marketBias": "MIXED",
    "volatilityRegime": "NORMAL",
    "symbols": {
      "spy": {"price": 450.25, "change": 2.15, "change_pct": 0.48},
      "qqq": {"price": 375.80, "change": -1.25, "change_pct": -0.33},
      "vix": {"price": 18.50, "change": -0.75, "change_pct": -3.89}
    },
    "volumeFlow": {"total_volume_60min": 77000000, "symbols_tracked": 3},
    "aiAnalysis": "🤖 LM Studio (Fast Analysis):\nCurrent market shows mixed signals..."
  }
}
```

**Areas for Enhancement:**
- [ ] Add caching for AI analysis (5-minute TTL)
- [ ] Implement WebSocket push for real-time updates
- [ ] Add user-specific dashboard configurations
- [ ] Implement dashboard widget customization

#### GET `/api/market/historical`
**Description:** Get historical price data for a symbol

**Parameters:**
- `symbol` (required): Trading symbol (e.g., SPY, QQQ, BTC-USD)
- `timeframe` (optional): Timeframe (1Min, 5Min, 15Min, 1H, 1D) - default: 1Min
- `limit` (optional): Number of candles - default: 100

**Response:**
```json
{
  "success": true,
  "data": {
    "symbol": "SPY",
    "data": [
      {
        "timestamp": "2024-01-15T10:00:00",
        "open": 448.50,
        "high": 449.20,
        "low": 448.30,
        "close": 449.10,
        "volume": 1250000
      }
    ]
  }
}
```

**Areas for Enhancement:**
- [ ] Add data pagination for large requests
- [ ] Implement caching by symbol/timeframe
- [ ] Add data aggregation for higher timeframes
- [ ] Implement data export functionality (CSV, JSON)

### AI Analysis Endpoints

#### GET `/api/market/ai-analysis`
**Description:** Get AI analysis of current market conditions

**Response:**
```json
{
  "success": true,
  "data": {
    "analysis": "🤖 LM Studio (Fast Analysis):\nMarket Bias: Mixed. SPY up +0.48%..."
  }
}
```

**Areas for Enhancement:**
- [ ] Add analysis type parameter (quick/deep/review)
- [ ] Implement analysis history tracking
- [ ] Add user feedback integration
- [ ] Create analysis confidence scoring

#### POST `/api/llm/comment`
**Description:** Add user comment to LLM analysis

**Request Body:**
```json
{
  "analysis_id": "market_analysis_20240115_103000",
  "comment": "I think the VIX level suggests more caution",
  "user_id": "trader_john"
}
```

**Areas for Enhancement:**
- [ ] Add comment threading/replies
- [ ] Implement comment upvoting/downvoting
- [ ] Add comment moderation system
- [ ] Create comment analytics

#### POST `/api/llm/refine`
**Description:** Refine LLM analysis based on user feedback

**Request Body:**
```json
{
  "original_analysis": "Original AI analysis text...",
  "user_comments": [
    "Concern about VIX level",
    "Focus on support levels"
  ],
  "additional_context": {
    "vix_level": 22.5,
    "key_support": 14950
  },
  "focus_areas": ["risk_assessment", "support_levels"]
}
```

**Areas for Enhancement:**
- [ ] Add refinement history tracking
- [ ] Implement multiple refinement rounds
- [ ] Add refinement quality scoring
- [ ] Create refinement templates

#### POST `/api/llm/analyze-chart`
**Description:** Analyze text-encoded chart data

**Request Body:**
```json
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
  "specific_questions": ["Is this a breakout?", "Volume pattern analysis"]
}
```

**Areas for Enhancement:**
- [ ] Add chart image upload support
- [ ] Implement pattern recognition library integration
- [ ] Add multiple timeframe analysis
- [ ] Create chart annotation features

#### GET `/api/llm/validation/sanity-check`
**Description:** Run data validation on current market data

**Response:**
```json
{
  "success": true,
  "data": {
    "validation_result": {
      "is_valid": true,
      "confidence": 95,
      "issues": [],
      "recommendations": ["Data quality is good"]
    },
    "market_data": {}
  }
}
```

**Areas for Enhancement:**
- [ ] Add custom validation rules
- [ ] Implement anomaly detection
- [ ] Add data quality scoring
- [ ] Create alerting for data issues

### WebSocket Endpoint

#### WebSocket `/ws/market`
**Description:** Real-time market data streaming

**Message Format:**
```json
{
  "type": "market_update",
  "data": {
    "spy": {"price": 450.25, "change": 2.15},
    "qqq": {"price": 375.80, "change": -1.25},
    "vix": {"price": 18.50, "change": -0.75}
  },
  "timestamp": "2024-01-15T10:30:00"
}
```

**Areas for Enhancement:**
- [ ] Add authentication for WebSocket connections
- [ ] Implement room-based broadcasting (per user/symbol)
- [ ] Add message queuing for reliability
- [ ] Implement reconnection logic with backoff

## Database Schema

### Core Tables

**market_internals**
```sql
CREATE TABLE market_internals (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    advance_decline_ratio FLOAT,
    volume_flow BIGINT,
    momentum_score FLOAT,
    volatility_regime VARCHAR(20),
    correlation_strength FLOAT,
    support_level FLOAT,
    resistance_level FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**price_data**
```sql
CREATE TABLE price_data (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    open FLOAT NOT NULL,
    high FLOAT NOT NULL,
    low FLOAT NOT NULL,
    close FLOAT NOT NULL,
    volume BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**llm_insights**
```sql
CREATE TABLE llm_insights (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    analysis_type VARCHAR(20) NOT NULL,
    market_data JSONB,
    analysis_text TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**user_comments**
```sql
CREATE TABLE user_comments (
    id SERIAL PRIMARY KEY,
    analysis_id VARCHAR(100) NOT NULL,
    user_id VARCHAR(100),
    comment TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Areas for Enhancement:**
- [ ] Add indexes for common queries (symbol, timestamp)
- [ ] Implement table partitioning for large datasets
- [ ] Add data retention policies
- [ ] Create materialized views for analytics
- [ ] Implement database migration system

## Configuration Management

### Environment Variables
```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/marketpulse

# APIs
ALPACA_API_KEY=your_alpaca_key
ALPACA_SECRET_KEY=your_alpaca_secret

# LLM
LM_STUDIO_URL=http://localhost:1234/v1
LM_STUDIO_MODEL=aquif-3.5-max-42b-a3b-i1

# Market Settings
MARKET_DATA_INTERVAL=60  # seconds
LLM_ANALYSIS_INTERVAL=300  # seconds
```

### Configuration Files
- `config/credentials.yaml` - API keys and secrets
- `config/settings.yaml` - Application settings
- `.env` - Environment-specific variables

**Areas for Enhancement:**
- [ ] Add configuration validation
- [ ] Implement hot-reloading of config
- [ ] Add configuration versioning
- [ ] Create configuration UI
- [ ] Implement secrets management integration

## Error Handling and Logging

### Current Logging Setup
```python
from loguru import logger

logger.add("logs/marketpulse.log", 
           rotation="500 MB", 
           retention="10 days", 
           level="INFO")
```

### Error Response Format
```json
{
  "success": false,
  "error": "Detailed error message",
  "timestamp": "2024-01-15T10:30:00"
}
```

**Areas for Enhancement:**
- [ ] Implement structured logging (JSON format)
- [ ] Add error tracking and alerting (Sentry)
- [ ] Create error classification system
- [ ] Add request/response logging
- [ ] Implement performance monitoring

## Security Considerations

### Current Security Measures
- CORS configuration for frontend
- API key management
- Database credential encryption

**Areas for Enhancement:**
- [ ] Implement API authentication (JWT/OAuth)
- [ ] Add rate limiting per user
- [ ] Implement request signing for critical endpoints
- [ ] Add input validation and sanitization
- [ ] Implement audit logging
- [ ] Add DDoS protection
- [ ] Create security headers middleware

## Performance Optimization

### Current Performance Characteristics
- API response time: 100-500ms
- WebSocket updates: every 30 seconds
- Database queries: 10-50ms
- LLM analysis: 2-5 seconds

**Optimization Opportunities:**
- [ ] Add Redis caching layer
- [ ] Implement connection pooling
- [ ] Add async database operations
- [ ] Implement query result caching
- [ ] Add CDN for static assets
- [ ] Implement database read replicas
- [ ] Add load balancing

## Testing Strategy

### Current Test Coverage
- LLM integration tests
- Basic API endpoint tests
- Knowledge base tests

**Recommended Test Additions:**
- [ ] Unit tests for all API endpoints
- [ ] Integration tests for data flow
- [ ] Performance benchmarks
- [ ] Load testing scripts
- [ ] Security testing (penetration tests)
- [ ] Chaos engineering tests
- [ ] End-to-end testing suite

## Deployment

### Docker Configuration
```yaml
# docker-compose.yml
services:
  postgres:
    image: postgres:18
    # ... database config
  
  api:
    build:
      context: .
      dockerfile: Dockerfile.api
    # ... API config
```

### Deployment Checklist
- [ ] Environment variable configuration
- [ ] Database migrations
- [ ] SSL certificate setup
- [ ] Monitoring and alerting
- [ ] Backup strategy
- [ ] Scaling configuration
- [ ] CI/CD pipeline setup

## Monitoring and Observability

### Key Metrics to Monitor
- API response times
- Database query performance
- LLM query success rates
- Market data collection latency
- Error rates by endpoint
- User engagement metrics

**Monitoring Tools to Implement:**
- [ ] Prometheus metrics collection
- [ ] Grafana dashboards
- [ ] Log aggregation (ELK stack)
- [ ] Application Performance Monitoring (APM)
- [ ] Custom business metrics
- [ ] Alerting system (PagerDuty/Opsgenie)

## API Rate Limits and Quotas

### Recommended Rate Limits
```python
# Per user/IP
RATE_LIMITS = {
    "market_internals": "100/minute",
    "ai_analysis": "10/minute",
    "chart_analysis": "20/minute",
    "hypothesis_test": "5/minute",
    "websocket": "1 connection per user"
}
```

## Future API Enhancements

### Planned Endpoints
- [ ] `POST /api/strategies/backtest` - Backtest trading strategies
- [ ] `GET /api/performance/metrics` - Get performance analytics
- [ ] `POST /api/alerts/create` - Create custom alerts
- [ ] `GET /api/market/correlations` - Get market correlations
- [ ] `POST /api/portfolio/analyze` - Portfolio analysis
- [ ] `GET /api/hypotheses/performance` - Hypothesis performance tracking

### Versioning Strategy
- Current version: v0.1.0
- Next version: v0.2.0 (with enhanced LLM features)
- Version header: `Accept: application/vnd.marketpulse.v1+json`

---

**Last Updated:** 2025-01-11
**API Version:** 0.1.0
**Status:** Production Ready