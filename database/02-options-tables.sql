-- Options Data Tables
-- Schema for storing options chains, Greeks, and analysis

-- Options Chains - Raw options chain data from market
CREATE TABLE IF NOT EXISTS market_data.options_chains (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    expiration_date DATE NOT NULL,
    strike_price NUMERIC(10,2) NOT NULL,
    option_type VARCHAR(4) NOT NULL, -- 'call' or 'put'

    -- Market data
    last_price NUMERIC(10,4),
    bid NUMERIC(10,4),
    ask NUMERIC(10,4),
    volume INTEGER,
    open_interest INTEGER,

    -- Implied volatility from market
    implied_volatility NUMERIC(8,6),

    -- Calculated Greeks
    delta NUMERIC(8,6),
    gamma NUMERIC(8,6),
    theta NUMERIC(8,6),
    vega NUMERIC(8,6),
    rho NUMERIC(8,6),

    -- Theoretical pricing
    theoretical_price NUMERIC(10,4),

    -- Underlying stock data at time of snapshot
    underlying_price NUMERIC(10,2),
    underlying_change NUMERIC(10,4),
    underlying_change_pct NUMERIC(6,3),

    -- Additional metrics
    in_the_money BOOLEAN,
    intrinsic_value NUMERIC(10,4),
    time_value NUMERIC(10,4),

    -- Metadata
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    data_source VARCHAR(50) DEFAULT 'yahoo',

    UNIQUE(symbol, expiration_date, strike_price, option_type, timestamp)
);

-- Options Analysis - Analyzed options strategies
CREATE TABLE IF NOT EXISTS analysis.options_analysis (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    strategy_type VARCHAR(50) NOT NULL, -- 'single_leg', 'covered_call', 'bull_call_spread', etc.

    -- Strategy details (stored as JSONB for flexibility)
    strategy_config JSONB NOT NULL, -- Contains strikes, expirations, position types, etc.

    -- Risk metrics
    cost_basis NUMERIC(15,2),
    breakeven NUMERIC(10,2),
    max_profit NUMERIC(15,2), -- NULL for unlimited
    max_loss NUMERIC(15,2),   -- NULL for unlimited
    risk_reward_ratio NUMERIC(8,4),

    -- Probabilities
    probability_profit NUMERIC(5,2), -- Percentage
    probability_itm NUMERIC(5,2),    -- Percentage

    -- Greeks (portfolio Greeks for multi-leg)
    total_delta NUMERIC(10,6),
    total_gamma NUMERIC(10,6),
    total_theta NUMERIC(10,6),
    total_vega NUMERIC(10,6),

    -- Market context at time of analysis
    underlying_price NUMERIC(10,2),
    vix_level NUMERIC(6,2),
    risk_free_rate NUMERIC(6,4),

    -- LLM insights
    llm_recommendation TEXT,
    llm_confidence NUMERIC(4,3),

    -- Metadata
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    analyzed_by VARCHAR(50) DEFAULT 'system',

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Options Screening Results - Results from options screeners
CREATE TABLE IF NOT EXISTS analysis.options_screening (
    id SERIAL PRIMARY KEY,
    screen_type VARCHAR(50) NOT NULL, -- 'otm_calls', 'covered_calls', 'earnings_plays', etc.

    -- Screen criteria
    criteria JSONB NOT NULL, -- Min delta, max delta, days to expiry, volume, etc.

    -- Results (array of option opportunities)
    results JSONB NOT NULL, -- Array of matching options with full analysis

    -- Market context
    vix_level NUMERIC(6,2),
    vix_percentile NUMERIC(5,2),
    volatility_regime VARCHAR(20), -- 'low', 'normal', 'elevated', 'high'

    -- Top picks
    top_symbols TEXT[], -- Array of top symbol picks

    -- Metadata
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    results_count INTEGER,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Macro Context - VIX and market regime data
CREATE TABLE IF NOT EXISTS market_data.macro_context (
    id SERIAL PRIMARY KEY,

    -- VIX data
    vix_level NUMERIC(6,2),
    vix_change NUMERIC(6,2),
    vix_percentile NUMERIC(5,2), -- Percentile over lookback period

    -- Market indices
    spy_price NUMERIC(10,2),
    spy_change_pct NUMERIC(6,3),
    qqq_price NUMERIC(10,2),
    qqq_change_pct NUMERIC(6,3),

    -- Volatility regime
    volatility_regime VARCHAR(20), -- 'low', 'normal', 'elevated', 'high'
    regime_confidence NUMERIC(4,3),

    -- Sector performance (stored as JSONB)
    sector_performance JSONB, -- {'XLK': 1.5, 'XLF': -0.5, ...}

    -- Market breadth
    advance_decline_ratio NUMERIC(6,3),
    new_highs_lows_ratio NUMERIC(6,3),

    -- Risk indicators
    put_call_ratio NUMERIC(6,3),
    skew NUMERIC(6,2),

    -- Treasury rates
    treasury_10y NUMERIC(6,4),
    treasury_2y NUMERIC(6,4),
    yield_curve_spread NUMERIC(6,4),

    timestamp TIMESTAMPTZ DEFAULT NOW(),

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Watchlist - User-defined options watchlist
CREATE TABLE IF NOT EXISTS user_data.options_watchlist (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100), -- For future multi-user support

    symbol VARCHAR(20) NOT NULL,
    strike_price NUMERIC(10,2),
    expiration_date DATE,
    option_type VARCHAR(4), -- 'call' or 'put'

    -- Notes and alerts
    notes TEXT,
    alert_price NUMERIC(10,4), -- Alert when option reaches this price
    alert_triggered BOOLEAN DEFAULT FALSE,

    -- Metadata
    added_at TIMESTAMPTZ DEFAULT NOW(),
    last_checked TIMESTAMPTZ,

    UNIQUE(user_id, symbol, strike_price, expiration_date, option_type)
);

-- Create user_data schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS user_data;
