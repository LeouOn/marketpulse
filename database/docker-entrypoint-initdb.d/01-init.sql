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

-- Add new columns to prices table
ALTER TABLE market_data.prices ADD COLUMN IF NOT EXISTS adjusted_close DECIMAL(15,6);
ALTER TABLE market_data.prices ADD COLUMN IF NOT EXISTS split_factor DECIMAL(15,6) DEFAULT 1;
ALTER TABLE market_data.prices ADD COLUMN IF NOT EXISTS dividend_amount DECIMAL(15,6) DEFAULT 0;
ALTER TABLE market_data.prices ADD COLUMN IF NOT EXISTS source VARCHAR(20) DEFAULT 'yahoo';

-- Symbols master table
CREATE TABLE IF NOT EXISTS market_data.symbols (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    name VARCHAR(200),
    asset_type VARCHAR(20) NOT NULL,
    exchange VARCHAR(20),
    sector VARCHAR(50),
    industry VARCHAR(100),
    currency VARCHAR(3) DEFAULT 'USD',
    lot_size FLOAT DEFAULT 1,
    tick_size FLOAT DEFAULT 0.01,
    is_active BOOLEAN DEFAULT TRUE,
    yahoo_symbol VARCHAR(20),
    alpaca_symbol VARCHAR(20),
    data_source VARCHAR(20) DEFAULT 'yahoo',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (symbol)
);
CREATE INDEX IF NOT EXISTS ix_symbols_symbol ON market_data.symbols (symbol);
CREATE INDEX IF NOT EXISTS ix_symbols_sector ON market_data.symbols (sector);
CREATE INDEX IF NOT EXISTS ix_symbols_is_active ON market_data.symbols (is_active);

-- Symbol daily statistics
CREATE TABLE IF NOT EXISTS market_data.symbol_stats (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    high_52w FLOAT,
    low_52w FLOAT,
    pct_from_52w_high FLOAT,
    pct_from_52w_low FLOAT,
    avg_volume_20d INTEGER,
    avg_volume_50d INTEGER,
    sma_20 FLOAT,
    sma_50 FLOAT,
    sma_200 FLOAT,
    atr_14 FLOAT,
    beta FLOAT,
    market_cap BIGINT,
    pe_ratio FLOAT,
    prev_close FLOAT,
    day_range_pct FLOAT,
    year_high_date DATE,
    year_low_date DATE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (symbol, date)
);
CREATE INDEX IF NOT EXISTS ix_symbol_stats_symbol ON market_data.symbol_stats (symbol);

-- Screener snapshots
CREATE TABLE IF NOT EXISTS market_data.screener_snapshots (
    id SERIAL PRIMARY KEY,
    snapshot_date DATE NOT NULL,
    screener_type VARCHAR(20) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    rank INTEGER NOT NULL,
    price FLOAT,
    change_pct FLOAT,
    volume BIGINT,
    market_cap BIGINT,
    avg_volume_3m BIGINT,
    relative_volume FLOAT,
    extra_data JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (snapshot_date, screener_type, symbol)
);
CREATE INDEX IF NOT EXISTS ix_screener_snapshots_symbol ON market_data.screener_snapshots (symbol);

-- Market breadth snapshots
CREATE TABLE IF NOT EXISTS market_data.breadth_snapshots (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    nyse_advancing INTEGER,
    nyse_declining INTEGER,
    nyse_unchanged INTEGER,
    nyse_ad_ratio FLOAT,
    nasdaq_advancing INTEGER,
    nasdaq_declining INTEGER,
    nasdaq_unchanged INTEGER,
    nasdaq_ad_ratio FLOAT,
    new_highs_52w INTEGER,
    new_lows_52w INTEGER,
    tick_avg_30m FLOAT,
    vold_nyse BIGINT,
    mcclellan_osc FLOAT,
    mcclellan_sum FLOAT,
    trin FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (date)
);

-- Data fetch log
CREATE TABLE IF NOT EXISTS market_data.data_fetch_log (
    id SERIAL PRIMARY KEY,
    source VARCHAR(20) NOT NULL,
    endpoint VARCHAR(200) NOT NULL,
    symbols TEXT,
    status VARCHAR(10) NOT NULL,
    response_ms INTEGER,
    bars_fetched INTEGER DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Technical indicators
CREATE TABLE IF NOT EXISTS analysis.indicators (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    indicator_type VARCHAR(30) NOT NULL,
    params JSONB NOT NULL,
    value FLOAT,
    values JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (symbol, timeframe, timestamp, indicator_type, params)
);
CREATE INDEX IF NOT EXISTS ix_indicators_symbol ON analysis.indicators (symbol);
CREATE INDEX IF NOT EXISTS ix_indicators_timestamp ON analysis.indicators (timestamp);