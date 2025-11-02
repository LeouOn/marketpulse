-- Indexes for MarketPulse Database
-- Optimize query performance for time-series data

-- Price data indexes
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_prices_symbol_timeframe_timestamp 
    ON market_data.prices(symbol, timeframe, timestamp DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_prices_timestamp 
    ON market_data.prices(timestamp DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_prices_symbol 
    ON market_data.prices(symbol);

-- Market internals indexes
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_internals_symbol_timestamp 
    ON market_data.internals(symbol, timestamp DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_internals_timestamp 
    ON market_data.internals(timestamp DESC);

-- LLM insights indexes
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_llm_insights_symbol_timestamp 
    ON analysis.llm_insights(symbol, timestamp DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_llm_insights_analysis_type 
    ON analysis.llm_insights(analysis_type);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_llm_insights_timestamp 
    ON analysis.llm_insights(timestamp DESC);

-- Alerts indexes
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_alerts_symbol_timestamp 
    ON analysis.alerts(symbol, timestamp DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_alerts_timestamp 
    ON analysis.alerts(timestamp DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_alerts_severity 
    ON analysis.alerts(severity);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_alerts_acknowledged 
    ON analysis.alerts(acknowledged);

-- Market regime indexes
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_market_regime_symbol 
    ON analysis.market_regime(symbol);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_market_regime_time_range 
    ON analysis.market_regime(start_time, end_time);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_market_regime_type 
    ON analysis.market_regime(regime_type);