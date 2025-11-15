-- Risk Management and Trade Journal Tables
-- Schema for positions, trades, performance tracking, and alerts

-- Positions Table
CREATE TABLE IF NOT EXISTS trading.positions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Position details
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL, -- 'long' or 'short'
    contracts INTEGER NOT NULL,

    -- Prices
    entry_price NUMERIC(12,4) NOT NULL,
    stop_loss NUMERIC(12,4) NOT NULL,
    take_profit NUMERIC(12,4) NOT NULL,
    exit_price NUMERIC(12,4),

    -- Timing
    entry_timestamp TIMESTAMPTZ NOT NULL,
    exit_timestamp TIMESTAMPTZ,

    -- Status
    status VARCHAR(20) NOT NULL, -- 'open', 'closed', 'stopped_out', 'target_hit'

    -- P&L
    realized_pnl NUMERIC(12,2),
    unrealized_pnl NUMERIC(12,2),

    -- Trade context
    setup_type VARCHAR(50), -- 'FVG_FILL', 'ORDER_BLOCK_RETEST', etc.
    signal_confidence NUMERIC(5,2), -- 0-100

    -- Market conditions at entry
    cvd_at_entry NUMERIC(20,2),
    vix_at_entry NUMERIC(6,2),
    session VARCHAR(20), -- 'London', 'NY_Open', 'Asian', etc.

    -- Risk metrics
    risk_amount NUMERIC(12,2),
    reward_amount NUMERIC(12,2),
    risk_reward_ratio NUMERIC(8,4),
    point_value NUMERIC(8,2) DEFAULT 2.00, -- MNQ = $2/point

    -- Tags
    tags TEXT[], -- Array of tags for filtering
    notes TEXT,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_positions_symbol (symbol),
    INDEX idx_positions_status (status),
    INDEX idx_positions_entry_time (entry_timestamp DESC),
    INDEX idx_positions_exit_time (exit_timestamp DESC),
    INDEX idx_positions_setup_type (setup_type)
);

-- Daily Trading Stats
CREATE TABLE IF NOT EXISTS trading.daily_stats (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL UNIQUE,

    -- Balance
    starting_balance NUMERIC(12,2) NOT NULL,
    ending_balance NUMERIC(12,2) NOT NULL,

    -- P&L
    realized_pnl NUMERIC(12,2) NOT NULL DEFAULT 0,
    unrealized_pnl NUMERIC(12,2) DEFAULT 0,

    -- Trade counts
    total_trades INTEGER NOT NULL DEFAULT 0,
    winning_trades INTEGER NOT NULL DEFAULT 0,
    losing_trades INTEGER NOT NULL DEFAULT 0,
    break_even_trades INTEGER NOT NULL DEFAULT 0,

    -- P&L breakdown
    gross_profit NUMERIC(12,2) NOT NULL DEFAULT 0,
    gross_loss NUMERIC(12,2) NOT NULL DEFAULT 0,
    largest_win NUMERIC(12,2) NOT NULL DEFAULT 0,
    largest_loss NUMERIC(12,2) NOT NULL DEFAULT 0,

    -- Metrics
    win_rate NUMERIC(5,2), -- Percentage
    profit_factor NUMERIC(8,4),
    average_win NUMERIC(12,2),
    average_loss NUMERIC(12,2),

    -- Risk tracking
    max_portfolio_heat NUMERIC(12,2), -- Max at-risk during day

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_daily_stats_date (trade_date DESC)
);

-- Risk Events (Daily loss limits, consecutive losses, etc.)
CREATE TABLE IF NOT EXISTS trading.risk_events (
    id SERIAL PRIMARY KEY,

    -- Event details
    event_type VARCHAR(50) NOT NULL, -- 'DAILY_LOSS_LIMIT', 'CONSECUTIVE_LOSSES', 'PORTFOLIO_HEAT', etc.
    severity VARCHAR(20) NOT NULL, -- 'warning', 'critical'

    -- Event data
    description TEXT NOT NULL,
    triggered_value NUMERIC(12,2),
    limit_value NUMERIC(12,2),

    -- Context
    account_balance NUMERIC(12,2),
    daily_pnl NUMERIC(12,2),
    open_positions INTEGER,

    -- Timing
    event_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Actions taken
    action_taken TEXT, -- What was done in response

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_risk_events_type (event_type),
    INDEX idx_risk_events_severity (severity),
    INDEX idx_risk_events_time (event_timestamp DESC)
);

-- Performance Analytics (Aggregated over different periods)
CREATE TABLE IF NOT EXISTS trading.performance_analytics (
    id SERIAL PRIMARY KEY,

    -- Period
    period_type VARCHAR(20) NOT NULL, -- 'daily', 'weekly', 'monthly', 'all_time'
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,

    -- Basic metrics
    total_trades INTEGER NOT NULL,
    winning_trades INTEGER NOT NULL,
    losing_trades INTEGER NOT NULL,

    -- P&L
    total_pnl NUMERIC(12,2) NOT NULL,
    gross_profit NUMERIC(12,2) NOT NULL,
    gross_loss NUMERIC(12,2) NOT NULL,

    -- Averages
    average_win NUMERIC(12,2),
    average_loss NUMERIC(12,2),
    largest_win NUMERIC(12,2),
    largest_loss NUMERIC(12,2),

    -- Ratios
    win_rate NUMERIC(5,2),
    profit_factor NUMERIC(8,4),
    average_rr NUMERIC(8,4), -- Average R:R achieved
    expectancy NUMERIC(12,2), -- Expected $ per trade

    -- Risk metrics
    max_drawdown NUMERIC(12,2),
    max_drawdown_pct NUMERIC(5,2),
    sharpe_ratio NUMERIC(8,4),

    -- Streaks
    max_consecutive_wins INTEGER,
    max_consecutive_losses INTEGER,
    current_consecutive_wins INTEGER,
    current_consecutive_losses INTEGER,

    -- Metadata
    calculated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(period_type, period_start, period_end),
    INDEX idx_perf_period (period_type, period_end DESC)
);

-- Setup Type Performance
CREATE TABLE IF NOT EXISTS trading.setup_performance (
    id SERIAL PRIMARY KEY,

    -- Setup identification
    setup_type VARCHAR(50) NOT NULL,

    -- Period
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,

    -- Metrics
    total_trades INTEGER NOT NULL,
    winning_trades INTEGER NOT NULL,
    losing_trades INTEGER NOT NULL,

    win_rate NUMERIC(5,2),
    profit_factor NUMERIC(8,4),
    total_pnl NUMERIC(12,2),
    average_pnl NUMERIC(12,2),

    best_trade NUMERIC(12,2),
    worst_trade NUMERIC(12,2),

    -- Metadata
    last_updated TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(setup_type, period_start, period_end),
    INDEX idx_setup_perf_type (setup_type),
    INDEX idx_setup_perf_pf (profit_factor DESC)
);

-- Session Performance
CREATE TABLE IF NOT EXISTS trading.session_performance (
    id SERIAL PRIMARY KEY,

    -- Session identification
    session VARCHAR(20) NOT NULL, -- 'London', 'NY_Open', 'Asian', etc.

    -- Period
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,

    -- Metrics
    total_trades INTEGER NOT NULL,
    winning_trades INTEGER NOT NULL,

    win_rate NUMERIC(5,2),
    total_pnl NUMERIC(12,2),
    average_pnl NUMERIC(12,2),

    -- Metadata
    last_updated TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(session, period_start, period_end),
    INDEX idx_session_perf_session (session),
    INDEX idx_session_perf_pnl (total_pnl DESC)
);

-- Alert History
CREATE TABLE IF NOT EXISTS trading.alert_history (
    id SERIAL PRIMARY KEY,

    -- Alert details
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    priority VARCHAR(20) NOT NULL, -- 'low', 'medium', 'high', 'critical'

    -- Channels sent to
    channels TEXT[], -- Array of channel names

    -- Related data
    alert_type VARCHAR(50), -- 'trade_signal', 'risk_alert', 'position_update'
    related_position_id UUID REFERENCES trading.positions(id),
    alert_data JSONB, -- Additional structured data

    -- Delivery status
    sent_successfully BOOLEAN DEFAULT TRUE,
    failed_channels TEXT[],

    -- Timing
    alert_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_alerts_type (alert_type),
    INDEX idx_alerts_priority (priority),
    INDEX idx_alerts_time (alert_timestamp DESC),
    INDEX idx_alerts_position (related_position_id)
);

-- Account State (For persistence across restarts)
CREATE TABLE IF NOT EXISTS trading.account_state (
    id SERIAL PRIMARY KEY,

    -- There should only ever be one row - current state
    is_current BOOLEAN DEFAULT TRUE UNIQUE,

    -- Balance
    current_balance NUMERIC(12,2) NOT NULL,

    -- Daily tracking
    daily_pnl NUMERIC(12,2) DEFAULT 0,
    daily_trades INTEGER DEFAULT 0,
    daily_date DATE NOT NULL,

    -- Risk state
    consecutive_losses INTEGER DEFAULT 0,
    consecutive_wins INTEGER DEFAULT 0,

    -- Limits
    max_daily_loss NUMERIC(12,2) NOT NULL,
    max_position_risk NUMERIC(12,2) NOT NULL,
    max_portfolio_heat NUMERIC(12,2) NOT NULL,

    -- Status
    can_trade BOOLEAN DEFAULT TRUE,
    trading_halt_reason TEXT,

    -- Timestamps
    last_reset TIMESTAMPTZ, -- Last daily reset
    last_trade TIMESTAMPTZ,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Insert initial account state
INSERT INTO trading.account_state (
    is_current,
    current_balance,
    daily_date,
    max_daily_loss,
    max_position_risk,
    max_portfolio_heat
) VALUES (
    TRUE,
    10000.00,
    CURRENT_DATE,
    500.00,
    250.00,
    600.00
) ON CONFLICT (is_current) DO NOTHING;

-- Equity Curve (Historical balance snapshots)
CREATE TABLE IF NOT EXISTS trading.equity_curve (
    id SERIAL PRIMARY KEY,

    -- Balance at this point
    balance NUMERIC(12,2) NOT NULL,

    -- What caused the change
    change_amount NUMERIC(12,2),
    change_type VARCHAR(20), -- 'trade', 'deposit', 'withdrawal', 'adjustment'

    -- Related trade if applicable
    related_position_id UUID REFERENCES trading.positions(id),

    -- Timing
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    INDEX idx_equity_time (timestamp DESC)
);

-- Functions and Triggers

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_positions_updated_at
    BEFORE UPDATE ON trading.positions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_daily_stats_updated_at
    BEFORE UPDATE ON trading.daily_stats
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_account_state_updated_at
    BEFORE UPDATE ON trading.account_state
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Materialized views for performance (optional)

-- Recent performance summary
CREATE MATERIALIZED VIEW IF NOT EXISTS trading.recent_performance AS
SELECT
    COUNT(*) as total_trades,
    SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
    SUM(CASE WHEN realized_pnl < 0 THEN 1 ELSE 0 END) as losses,
    SUM(realized_pnl) as total_pnl,
    AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END) as avg_win,
    AVG(CASE WHEN realized_pnl < 0 THEN realized_pnl END) as avg_loss,
    MAX(realized_pnl) as largest_win,
    MIN(realized_pnl) as largest_loss
FROM trading.positions
WHERE exit_timestamp >= NOW() - INTERVAL '30 days'
  AND status != 'open'
  AND realized_pnl IS NOT NULL;

CREATE UNIQUE INDEX idx_recent_performance ON trading.recent_performance ((true));

-- Comments for documentation
COMMENT ON TABLE trading.positions IS 'All trading positions (open and closed)';
COMMENT ON TABLE trading.daily_stats IS 'Daily trading statistics and metrics';
COMMENT ON TABLE trading.risk_events IS 'Risk management events and violations';
COMMENT ON TABLE trading.performance_analytics IS 'Aggregated performance metrics by period';
COMMENT ON TABLE trading.setup_performance IS 'Performance breakdown by setup type (FVG, OB, etc.)';
COMMENT ON TABLE trading.session_performance IS 'Performance breakdown by trading session';
COMMENT ON TABLE trading.alert_history IS 'History of all alerts sent';
COMMENT ON TABLE trading.account_state IS 'Current account state for persistence';
COMMENT ON TABLE trading.equity_curve IS 'Historical balance snapshots for equity curve';

-- Grant permissions (adjust as needed)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA trading TO marketpulse_user;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA trading TO marketpulse_user;
