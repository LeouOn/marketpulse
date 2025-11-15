-- ICT and Order Flow Tables
-- Schema for storing ICT concepts and order flow data

-- Fair Value Gaps
CREATE TABLE IF NOT EXISTS market_data.fair_value_gaps (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    type VARCHAR(10) NOT NULL, -- 'bullish' or 'bearish'

    -- Gap boundaries
    upper_price NUMERIC(12,4) NOT NULL,
    lower_price NUMERIC(12,4) NOT NULL,
    gap_size NUMERIC(10,4) NOT NULL,
    midpoint NUMERIC(12,4) NOT NULL,

    -- Timing
    formation_timestamp TIMESTAMPTZ NOT NULL,
    candle_index INTEGER,

    -- Status
    is_filled BOOLEAN DEFAULT FALSE,
    fill_percentage NUMERIC(5,2) DEFAULT 0.0,
    fill_timestamp TIMESTAMPTZ,

    -- Metadata
    timeframe VARCHAR(10),  -- '5m', '15m', '1h', etc.
    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_fvg_symbol_time (symbol, formation_timestamp DESC),
    INDEX idx_fvg_filled (is_filled),
    INDEX idx_fvg_type (type)
);

-- Order Blocks
CREATE TABLE IF NOT EXISTS market_data.order_blocks (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    type VARCHAR(10) NOT NULL, -- 'bullish' or 'bearish'

    -- Price levels
    high_price NUMERIC(12,4) NOT NULL,
    low_price NUMERIC(12,4) NOT NULL,
    open_price NUMERIC(12,4) NOT NULL,
    close_price NUMERIC(12,4) NOT NULL,
    midpoint NUMERIC(12,4) NOT NULL,

    -- Volume and strength
    volume NUMERIC(20,2),
    strength NUMERIC(5,2), -- 0-100 score

    -- Timing
    formation_timestamp TIMESTAMPTZ NOT NULL,
    candle_index INTEGER,

    -- Status
    is_tested BOOLEAN DEFAULT FALSE,
    is_broken BOOLEAN DEFAULT FALSE,
    test_count INTEGER DEFAULT 0,

    -- Metadata
    timeframe VARCHAR(10),
    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_ob_symbol_time (symbol, formation_timestamp DESC),
    INDEX idx_ob_status (is_tested, is_broken),
    INDEX idx_ob_strength (strength DESC)
);

-- Liquidity Pools
CREATE TABLE IF NOT EXISTS market_data.liquidity_pools (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    type VARCHAR(20) NOT NULL, -- 'buy_side' or 'sell_side'

    -- Price level
    price NUMERIC(12,4) NOT NULL,
    strength NUMERIC(5,2), -- 0-100 based on significance

    -- Timing
    formation_timestamp TIMESTAMPTZ NOT NULL,

    -- Status
    is_swept BOOLEAN DEFAULT FALSE,
    sweep_timestamp TIMESTAMPTZ,
    sweep_price NUMERIC(12,4),

    -- Context
    swing_type VARCHAR(20), -- 'swing_high', 'swing_low', 'equal_highs', etc.

    -- Metadata
    timeframe VARCHAR(10),
    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_liq_symbol_time (symbol, formation_timestamp DESC),
    INDEX idx_liq_swept (is_swept),
    INDEX idx_liq_type (type)
);

-- Market Structure Events
CREATE TABLE IF NOT EXISTS market_data.market_structure (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,

    -- Structure type
    structure_type VARCHAR(20) NOT NULL, -- 'bullish', 'bearish', 'ranging'

    -- Events
    event_type VARCHAR(20), -- 'BOS', 'CHoCH', 'MSB'
    event_timestamp TIMESTAMPTZ,

    -- Swing points (stored as JSONB)
    swing_highs JSONB, -- Array of {timestamp, price}
    swing_lows JSONB,  -- Array of {timestamp, price}

    -- Analysis timestamp
    timestamp TIMESTAMPTZ NOT NULL,

    -- Metadata
    timeframe VARCHAR(10),
    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_ms_symbol_time (symbol, timestamp DESC),
    INDEX idx_ms_type (structure_type),
    INDEX idx_ms_event (event_type)
);

-- ICT Signals
CREATE TABLE IF NOT EXISTS analysis.ict_signals (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,

    -- Signal details
    signal_type VARCHAR(10) NOT NULL, -- 'long' or 'short'
    trigger VARCHAR(50) NOT NULL, -- 'FVG_FILL', 'ORDER_BLOCK_RETEST', etc.
    confidence NUMERIC(5,2) NOT NULL, -- 0-100

    -- Entry/Exit prices
    entry_price NUMERIC(12,4) NOT NULL,
    stop_loss NUMERIC(12,4) NOT NULL,
    take_profit_1 NUMERIC(12,4),
    take_profit_2 NUMERIC(12,4),
    take_profit_3 NUMERIC(12,4),

    -- Risk/Reward
    risk_points NUMERIC(10,4),
    reward_points NUMERIC(10,4),
    risk_reward_ratio NUMERIC(8,4),

    -- ICT elements involved
    ict_elements JSONB, -- Array of elements that created signal
    order_flow_confirmation TEXT,

    -- Market context
    market_structure VARCHAR(20),
    vix_regime VARCHAR(20),
    session VARCHAR(20), -- 'london', 'newyork', 'asian'

    -- Signal outcome (for backtesting)
    outcome VARCHAR(20), -- 'win', 'loss', 'pending'
    exit_price NUMERIC(12,4),
    pnl NUMERIC(12,2),

    -- Timing
    signal_timestamp TIMESTAMPTZ NOT NULL,
    closed_timestamp TIMESTAMPTZ,

    -- Metadata
    timeframe VARCHAR(10),
    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_ict_signal_symbol_time (symbol, signal_timestamp DESC),
    INDEX idx_ict_signal_type (signal_type),
    INDEX idx_ict_signal_trigger (trigger),
    INDEX idx_ict_signal_outcome (outcome)
);

-- Order Flow Data (CVD, Volume Profile, etc.)
CREATE TABLE IF NOT EXISTS market_data.order_flow (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,

    -- Volume breakdown
    buy_volume NUMERIC(20,2),
    sell_volume NUMERIC(20,2),
    total_volume NUMERIC(20,2),
    delta NUMERIC(20,2), -- buy - sell
    delta_percent NUMERIC(6,2),

    -- Cumulative metrics
    cumulative_delta NUMERIC(20,2),

    -- Price at timestamp
    price NUMERIC(12,4),

    -- Volume profile (stored as JSONB for flexibility)
    volume_profile JSONB, -- {POC, VAH, VAL, levels: [{price, volume, delta}]}

    -- Imbalances and absorption
    has_imbalance BOOLEAN DEFAULT FALSE,
    imbalance_type VARCHAR(10), -- 'buy' or 'sell'
    imbalance_ratio NUMERIC(8,2),

    has_absorption BOOLEAN DEFAULT FALSE,
    absorption_type VARCHAR(20), -- 'buy_absorption' or 'sell_absorption'

    -- Timing
    timestamp TIMESTAMPTZ NOT NULL,

    -- Metadata
    timeframe VARCHAR(10),
    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_of_symbol_time (symbol, timestamp DESC),
    INDEX idx_of_imbalance (has_imbalance, imbalance_type),
    INDEX idx_of_absorption (has_absorption)
);

-- Delta Divergences
CREATE TABLE IF NOT EXISTS analysis.delta_divergences (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,

    -- Divergence details
    divergence_type VARCHAR(10) NOT NULL, -- 'bullish' or 'bearish'
    strength NUMERIC(5,2), -- 0-100

    -- Price and delta at divergence
    price_at_signal NUMERIC(12,4),
    delta_at_signal NUMERIC(20,2),

    -- Context
    price_trend VARCHAR(20), -- 'lower_lows', 'higher_highs'
    delta_trend VARCHAR(20), -- 'higher_lows', 'lower_highs'

    -- Timing
    signal_timestamp TIMESTAMPTZ NOT NULL,

    -- Outcome
    resulted_in_reversal BOOLEAN,
    reversal_timestamp TIMESTAMPTZ,

    -- Metadata
    timeframe VARCHAR(10),
    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_div_symbol_time (symbol, signal_timestamp DESC),
    INDEX idx_div_type (divergence_type),
    INDEX idx_div_outcome (resulted_in_reversal)
);

-- ICT Session Data (London, New York, Asian)
CREATE TABLE IF NOT EXISTS market_data.trading_sessions (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,

    -- Session details
    session_name VARCHAR(20) NOT NULL, -- 'london', 'newyork', 'asian'
    session_start TIMESTAMPTZ NOT NULL,
    session_end TIMESTAMPTZ,

    -- Session stats
    high_price NUMERIC(12,4),
    low_price NUMERIC(12,4),
    open_price NUMERIC(12,4),
    close_price NUMERIC(12,4),
    volume NUMERIC(20,2),

    -- Liquidity levels from session
    asian_session_high NUMERIC(12,4),
    asian_session_low NUMERIC(12,4),
    london_session_high NUMERIC(12,4),
    london_session_low NUMERIC(12,4),

    -- ICT concepts created during session
    fvg_count INTEGER DEFAULT 0,
    order_block_count INTEGER DEFAULT 0,
    liquidity_sweep_count INTEGER DEFAULT 0,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_session_symbol_time (symbol, session_start DESC),
    INDEX idx_session_name (session_name)
);

-- Performance Tracking for ICT Signals
CREATE TABLE IF NOT EXISTS analysis.ict_signal_performance (
    id SERIAL PRIMARY KEY,

    -- Aggregation level
    symbol VARCHAR(20),
    trigger_type VARCHAR(50),
    signal_type VARCHAR(10), -- 'long' or 'short'
    timeframe VARCHAR(10),

    -- Performance metrics
    total_signals INTEGER DEFAULT 0,
    winning_signals INTEGER DEFAULT 0,
    losing_signals INTEGER DEFAULT 0,
    pending_signals INTEGER DEFAULT 0,

    win_rate NUMERIC(5,2), -- Percentage
    average_rr NUMERIC(8,4), -- Average risk/reward
    total_pnl NUMERIC(12,2),
    average_pnl_per_trade NUMERIC(12,2),

    -- Best/Worst
    best_trade_pnl NUMERIC(12,2),
    worst_trade_pnl NUMERIC(12,2),

    -- Period
    period_start TIMESTAMPTZ,
    period_end TIMESTAMPTZ,

    -- Metadata
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_perf_symbol (symbol),
    INDEX idx_perf_trigger (trigger_type),
    INDEX idx_perf_winrate (win_rate DESC)
);

-- Add indexes for common queries
CREATE INDEX IF NOT EXISTS idx_fvg_symbol_unfilled
    ON market_data.fair_value_gaps(symbol)
    WHERE is_filled = FALSE;

CREATE INDEX IF NOT EXISTS idx_ob_symbol_valid
    ON market_data.order_blocks(symbol)
    WHERE is_broken = FALSE;

CREATE INDEX IF NOT EXISTS idx_liq_symbol_unswept
    ON market_data.liquidity_pools(symbol)
    WHERE is_swept = FALSE;

CREATE INDEX IF NOT EXISTS idx_ict_signals_pending
    ON analysis.ict_signals(symbol, signal_timestamp DESC)
    WHERE outcome = 'pending';

-- Comments for documentation
COMMENT ON TABLE market_data.fair_value_gaps IS 'Fair Value Gaps - price imbalances that often get filled';
COMMENT ON TABLE market_data.order_blocks IS 'Order Blocks - areas where smart money placed orders';
COMMENT ON TABLE market_data.liquidity_pools IS 'Liquidity Pools - areas where stops likely sit (swing highs/lows)';
COMMENT ON TABLE analysis.ict_signals IS 'Trading signals generated from ICT concepts + order flow';
COMMENT ON TABLE market_data.order_flow IS 'Order flow data - CVD, volume profile, imbalances';
COMMENT ON TABLE analysis.delta_divergences IS 'Price/Delta divergences indicating potential reversals';
