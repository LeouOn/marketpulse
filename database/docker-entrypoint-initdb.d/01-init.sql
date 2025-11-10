-- MarketPulse Database Schema
-- Main tables for market data storage and analysis

-- Create schemas first
CREATE SCHEMA IF NOT EXISTS market_data;
CREATE SCHEMA IF NOT EXISTS analysis;

-- Market Data Tables
CREATE TABLE IF NOT EXISTS market_data.prices (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    open_price DECIMAL(15,6) NOT NULL,
    high_price DECIMAL(15,6) NOT NULL,
    low_price DECIMAL(15,6) NOT NULL,
    close_price DECIMAL(15,6) NOT NULL,
    volume BIGINT DEFAULT 0,
    trade_count INTEGER DEFAULT 0,
    vwap DECIMAL(15,6),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(symbol, timeframe, timestamp)
);

-- Market Internals Tables
CREATE TABLE IF NOT EXISTS market_data.internals (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    advance_decline_ratio DECIMAL(8,4),
    volume_flow DECIMAL(15,2),
    momentum_score DECIMAL(8,4),
    volatility_regime VARCHAR(20),
    correlation_strength DECIMAL(4,3),
    support_level DECIMAL(15,6),
    resistance_level DECIMAL(15,6),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(symbol, timestamp)
);

-- LLM Analysis Results
CREATE TABLE IF NOT EXISTS analysis.llm_insights (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    analysis_type VARCHAR(50) NOT NULL,
    model_used VARCHAR(50) NOT NULL,
    input_data JSONB,
    analysis_result TEXT,
    confidence_score DECIMAL(4,3),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Alerts and Signals
CREATE TABLE IF NOT EXISTS analysis.alerts (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    alert_type VARCHAR(50) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    trigger_condition TEXT,
    message TEXT,
    severity VARCHAR(20) DEFAULT 'INFO',
    acknowledged BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Market Regime Classification
CREATE TABLE IF NOT EXISTS analysis.market_regime (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    regime_type VARCHAR(50) NOT NULL,
    confidence DECIMAL(4,3) NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ,
    characteristics JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);