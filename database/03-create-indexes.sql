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

-- Options chains indexes
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_options_chains_symbol_exp
    ON market_data.options_chains(symbol, expiration_date);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_options_chains_timestamp
    ON market_data.options_chains(timestamp DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_options_chains_symbol_exp_type
    ON market_data.options_chains(symbol, expiration_date, option_type);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_options_chains_strike
    ON market_data.options_chains(strike_price);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_options_chains_volume
    ON market_data.options_chains(volume DESC);

-- Options analysis indexes
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_options_analysis_symbol
    ON analysis.options_analysis(symbol);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_options_analysis_strategy
    ON analysis.options_analysis(strategy_type);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_options_analysis_timestamp
    ON analysis.options_analysis(timestamp DESC);

-- Options screening indexes
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_options_screening_type
    ON analysis.options_screening(screen_type);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_options_screening_timestamp
    ON analysis.options_screening(timestamp DESC);

-- Macro context indexes
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_macro_context_timestamp
    ON market_data.macro_context(timestamp DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_macro_context_regime
    ON market_data.macro_context(volatility_regime);

-- Options watchlist indexes
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_options_watchlist_user
    ON user_data.options_watchlist(user_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_options_watchlist_symbol
    ON user_data.options_watchlist(symbol);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_options_watchlist_alert
    ON user_data.options_watchlist(alert_triggered) WHERE alert_triggered = FALSE;