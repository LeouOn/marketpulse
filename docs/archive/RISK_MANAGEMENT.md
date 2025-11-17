# Risk Management & Trade Journal - MarketPulse

## Overview

Comprehensive risk management system designed to prevent catastrophic losses and enforce systematic trading rules.

**Your Trading Stats:**
- Account: $10,000
- Daily Loss Limit: $500 (prevents 75% drawdowns like before!)
- Per-Trade Risk: $250 max
- Position: 4 MNQ contracts
- Minimum R:R: 1.5:1

## Features Implemented

### 1. Risk Manager (`src/analysis/risk_manager.py`)

Enforces systematic risk rules to protect capital.

#### Core Protection Rules

**Daily Loss Limit**
- Maximum $500 loss per day
- Trading automatically halted when limit hit
- Prevents emotional revenge trading

**Position Risk Limits**
- Maximum $250 risk per trade (2.5% of account)
- Automatically calculates safe position size
- Rejects trades that exceed limit

**Risk/Reward Enforcement**
- Minimum 1.5:1 R:R ratio required
- Validates entry, stop, and target prices
- Suggests adjustments if trade doesn't meet criteria

**Consecutive Loss Protection**
- Stops trading after 3 consecutive losses
- Forces you to step back and reassess
- Resets on next win

**Portfolio Heat Monitoring**
- Tracks total at-risk across all positions
- Maximum 6% of account at risk simultaneously
- Prevents over-leveraging

**Maximum Positions**
- 3 concurrent positions maximum
- Prevents overtrading
- Maintains focus on quality over quantity

#### Usage Examples

**Validate a Trade:**
```python
from src.analysis.risk_manager import RiskManager

risk_manager = RiskManager(
    account_size=10000,
    max_daily_loss=500,
    max_position_risk=250
)

# Validate your FVG + CVD signal
validation = risk_manager.validate_trade(
    symbol="MNQ",
    entry_price=15850,
    stop_loss=15840,  # 10 points below
    take_profit=15870,  # 20 points above (2:1 R:R)
    direction="long",
    contracts=2,  # 2 MNQ contracts
    point_value=2.0  # $2 per point for MNQ
)

if validation.approved:
    print("✅ Trade approved!")
    print(f"Risk: ${validation.risk_metrics.total_risk}")
    print(f"Reward: ${validation.risk_metrics.total_reward}")
    print(f"R:R: {validation.risk_metrics.risk_reward_ratio:.2f}")

    if validation.warnings:
        for warning in validation.warnings:
            print(f"⚠️  {warning}")
else:
    print(f"❌ Trade rejected: {validation.reason}")
    if validation.suggested_contracts:
        print(f"💡 Try {validation.suggested_contracts} contract(s) instead")
```

**Calculate Position Size:**
```python
# How many contracts can I trade?
contracts = risk_manager.calculate_position_size(
    entry_price=15850,
    stop_loss=15840,  # 10 points
    direction="long",
    risk_amount=250  # Your max per-trade risk
)

print(f"Position size: {contracts} contracts")
# Output: 12 contracts (but capped at 4 for MNQ)
```

**Record Trade Results:**
```python
# After closing trade
risk_manager.record_trade_result(pnl=100)  # $100 profit
# OR
risk_manager.record_trade_result(pnl=-50)  # $50 loss

# Check current state
summary = risk_manager.get_risk_summary()
print(f"Daily P&L: ${summary['daily_pnl']}")
print(f"Consecutive losses: {summary['consecutive_losses']}")
print(f"Can trade: {summary['can_trade']}")
```

---

### 2. Position Manager (`src/state/position_manager.py`)

Tracks all positions and maintains state across app restarts.

#### Features

- **Open Positions Tracking**: All active trades with entry, stop, target
- **P&L Calculations**: Unrealized and realized P&L
- **Daily Statistics**: Trades per day, win rate, P&L
- **Persistent State**: Saves to disk, survives crashes/restarts
- **Risk Aggregation**: Total portfolio heat calculation

#### Usage Examples

**Open a Position:**
```python
from src.state.position_manager import (
    PositionManager, Position, PositionSide, PositionStatus
)
import uuid
from datetime import datetime

position_manager = PositionManager()

# Your FVG fill signal triggered!
position = Position(
    id=str(uuid.uuid4()),
    symbol="MNQ",
    side=PositionSide.LONG,
    entry_price=15850,
    stop_loss=15840,
    take_profit=15870,
    contracts=2,
    entry_timestamp=datetime.now(),
    status=PositionStatus.OPEN,

    # Trade context (for journal analysis later)
    setup_type="FVG_FILL",
    signal_confidence=85.0,
    cvd_at_entry=1250,
    vix_at_entry=15.2,
    session="NY_Open",
    tags=["bullish_fvg", "cvd_confirm", "structure_aligned"],

    point_value=2.0
)

position_manager.add_position(position)
```

**Close a Position:**
```python
# Target hit!
closed = position_manager.close_position(
    position_id=position.id,
    exit_price=15870,
    status=PositionStatus.TARGET_HIT
)

print(f"Realized P&L: ${closed.realized_pnl}")
# Output: Realized P&L: $80.00 (20 points * $2 * 2 contracts)
```

**Check Open Positions:**
```python
open_positions = position_manager.get_all_open_positions()

for pos in open_positions:
    print(f"{pos.symbol} {pos.side.value}: Entry ${pos.entry_price}, Stop ${pos.stop_loss}")
```

**Get Daily P&L:**
```python
daily_pnl = position_manager.get_daily_pnl()
print(f"Today's P&L: ${daily_pnl:+.2f}")
```

---

### 3. Trade Journal (`src/journal/trade_tracker.py`)

Detailed trade logging and performance analytics.

#### Features

- **Performance Metrics**: Win rate, profit factor, expectancy, Sharpe ratio
- **Setup Analysis**: Which ICT setups work best for you?
- **Session Analysis**: Best times to trade (London, NY Open, etc.)
- **Drawdown Tracking**: Maximum drawdown monitoring
- **Actionable Insights**: AI-powered recommendations

#### Usage Examples

**Analyze Performance:**
```python
from src.journal.trade_tracker import TradeJournal

journal = TradeJournal()

# Load trades from position manager
journal.load_trades(position_manager.closed_positions)

# Analyze last 30 days
stats = journal.analyze_performance(days=30)

print(f"Total Trades: {stats.total_trades}")
print(f"Win Rate: {stats.win_rate:.1f}%")
print(f"Profit Factor: {stats.profit_factor:.2f}")
print(f"Total P&L: ${stats.total_pnl:+,.2f}")
print(f"Expectancy: ${stats.expectancy:+.2f} per trade")
print(f"Average R:R: {stats.average_rr:.2f}")
print(f"Max Drawdown: ${stats.max_drawdown:.2f} ({stats.max_drawdown_pct:.1f}%)")
print(f"Sharpe Ratio: {stats.sharpe_ratio:.2f}")
```

**Find Best Setups:**
```python
setup_analyses = journal.analyze_by_setup(days=30)

print("\n📊 Setup Performance Rankings:")
for analysis in setup_analyses:
    print(f"\n{analysis.setup_type}:")
    print(f"  Trades: {analysis.total_trades}")
    print(f"  Win Rate: {analysis.win_rate:.1f}%")
    print(f"  Profit Factor: {analysis.profit_factor:.2f}")
    print(f"  Total P&L: ${analysis.total_pnl:+,.2f}")
```

Example output:
```
📊 Setup Performance Rankings:

FVG_FILL:
  Trades: 45
  Win Rate: 62.2%
  Profit Factor: 2.15
  Total P&L: $+1,250.00

ORDER_BLOCK_RETEST:
  Trades: 28
  Win Rate: 57.1%
  Profit Factor: 1.85
  Total P&L: $+640.00

LIQUIDITY_SWEEP:
  Trades: 12
  Win Rate: 50.0%
  Profit Factor: 1.42
  Total P&L: $+180.00
```

**Get Trading Insights:**
```python
insights = journal.get_insights(days=30)

print("\n💡 INSIGHTS:")
print(insights['summary'])

if insights['warnings']:
    print("\n⚠️  WARNINGS:")
    for warning in insights['warnings']:
        print(f"  {warning}")

if insights['recommendations']:
    print("\n✅ RECOMMENDATIONS:")
    for rec in insights['recommendations']:
        print(f"  {rec}")

if insights['strengths']:
    print("\n🎯 STRENGTHS:")
    for strength in insights['strengths']:
        print(f"  {strength}")
```

Example output:
```
💡 INSIGHTS:
Period: 30 days
Total Trades: 85
Win Rate: 58.8%
Profit Factor: 1.92
Total P&L: $+2,070.00

⚠️  WARNINGS:
  ⚠️ 2 consecutive losses. Trade carefully.

✅ RECOMMENDATIONS:
  ✅ Focus on 'FVG_FILL' setup - your best performer
  ❌ Avoid or refine 'BREAKOUT' setup - underperforming
  ⏰ Consider avoiding 'Asian' session - negative results

🎯 STRENGTHS:
  🎯 Strong win rate: 58.8%
  💰 Excellent profit factor: 1.92
  📈 Good risk/reward management: 2.1:1
```

---

### 4. Alert Manager (`src/alerts/alert_manager.py`)

Multi-channel notifications for trade signals and risk events.

#### Supported Channels

- **Desktop Notifications**: Pop-ups on your computer
- **Telegram**: Bot messages to your phone
- **Email**: SMTP email alerts
- **Webhook**: Custom integrations
- **Console**: Log output

#### Usage Examples

**Send Trade Signal Alert:**
```python
from src.alerts.alert_manager import AlertManager, AlertPriority

alert_manager = AlertManager()

# Your FVG signal triggered!
await alert_manager.send_trade_signal(
    symbol="MNQ",
    signal_type="LONG",
    entry_price=15850,
    stop_loss=15840,
    take_profit=15870,
    risk=40,  # $40
    reward=80,  # $80
    confidence=85,
    reasoning="Bullish FVG fill with CVD confirmation. Market structure bullish.",
    priority=AlertPriority.HIGH
)
```

Alert sent to all channels:
```
🎯 LONG Signal - MNQ

Entry: 15850.00
Stop: 15840.00
Target: 15870.00

Risk: $40
Reward: $80
R:R: 2.00:1
Confidence: 85%

Bullish FVG fill with CVD confirmation. Market structure bullish.
```

**Send Risk Alert:**
```python
# Daily loss limit approaching!
await alert_manager.send_risk_alert(
    alert_type="Daily Loss Limit",
    message="Daily P&L: -$450. Approaching limit of -$500. Trade carefully!",
    priority=AlertPriority.CRITICAL
)
```

**Setup Telegram (Optional):**
```bash
# Add to .env file
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

---

## API Endpoints

All endpoints return JSON with this format:
```json
{
  "success": true,
  "data": { ... },
  "error": "Optional error message"
}
```

### Risk Management

**Validate Trade**
```http
POST /api/risk/validate-trade
Content-Type: application/json

{
  "symbol": "MNQ",
  "entry_price": 15850,
  "stop_loss": 15840,
  "take_profit": 15870,
  "direction": "long",
  "contracts": 2,
  "point_value": 2.0
}
```

**Calculate Position Size**
```http
POST /api/risk/calculate-position-size?entry_price=15850&stop_loss=15840&direction=long&point_value=2.0
```

**Get Risk Summary**
```http
GET /api/risk/risk-summary
```

Returns:
```json
{
  "success": true,
  "data": {
    "account_size": 10000,
    "daily_pnl": -120.50,
    "daily_limit": 500,
    "daily_limit_used_pct": 24.1,
    "portfolio_heat": 85.00,
    "max_heat": 600,
    "heat_used_pct": 14.2,
    "open_positions": 2,
    "max_positions": 3,
    "consecutive_losses": 1,
    "daily_trades": 4,
    "risk_level": "moderate",
    "can_trade": true
  }
}
```

**Open Position**
```http
POST /api/risk/positions/open
Content-Type: application/json

{
  "symbol": "MNQ",
  "side": "long",
  "entry_price": 15850,
  "stop_loss": 15840,
  "take_profit": 15870,
  "contracts": 2,
  "setup_type": "FVG_FILL",
  "signal_confidence": 85,
  "cvd_at_entry": 1250,
  "vix_at_entry": 15.2,
  "session": "NY_Open",
  "tags": ["bullish_fvg", "cvd_confirm"]
}
```

**Close Position**
```http
POST /api/risk/positions/close
Content-Type: application/json

{
  "position_id": "550e8400-e29b-41d4-a716-446655440000",
  "exit_price": 15870,
  "exit_reason": "target_hit"
}
```

**Get Open Positions**
```http
GET /api/risk/positions/open
```

### Trade Journal

**Analyze Performance**
```http
POST /api/journal/analyze
Content-Type: application/json

{
  "days": 30
}
```

**Get Insights**
```http
GET /api/journal/insights?days=30
```

**Analyze by Setup Type**
```http
GET /api/journal/by-setup?days=30
```

**Analyze by Session**
```http
GET /api/journal/by-session?days=30
```

### Alerts

**Send Custom Alert**
```http
POST /api/alerts/send
Content-Type: application/json

{
  "title": "Market Alert",
  "message": "VIX spiking above 20!",
  "priority": "high"
}
```

---

## Database Schema

See `database/04-risk-journal-tables.sql` for complete schema.

**Key Tables:**
- `trading.positions` - All positions (open and closed)
- `trading.daily_stats` - Daily P&L and metrics
- `trading.risk_events` - Risk limit violations
- `trading.performance_analytics` - Aggregated performance
- `trading.setup_performance` - Performance by setup type
- `trading.session_performance` - Performance by trading session
- `trading.alert_history` - All alerts sent
- `trading.account_state` - Current account state (for persistence)
- `trading.equity_curve` - Balance snapshots over time

---

## Testing

**Run All Risk Management Tests:**
```bash
python3 tests/test_risk_management.py
```

**Test Coverage:**
- ✅ Trade validation (15 tests)
- ✅ Position sizing
- ✅ Daily loss limits
- ✅ Consecutive loss tracking
- ✅ Portfolio heat monitoring
- ✅ R:R ratio enforcement
- ✅ Position management (8 tests)
- ✅ P&L calculations
- ✅ State persistence

**All 23 tests passing! ✅**

---

## Workflow Example

**Your Complete Trading Flow:**

1. **Morning Routine:**
```python
# Reset daily stats
await risk_manager.reset_daily_stats()

# Check risk summary
summary = risk_manager.get_risk_summary()
print(f"Ready to trade. Daily limit: ${summary['daily_limit']}")
```

2. **Signal Received (FVG + CVD):**
```python
# Validate trade first!
validation = risk_manager.validate_trade(
    symbol="MNQ",
    entry_price=15850,
    stop_loss=15840,
    take_profit=15870,
    direction="long",
    contracts=2
)

if not validation.approved:
    print(f"❌ {validation.reason}")
    # DON'T TAKE THE TRADE!
    return

# Trade approved, send alert
await alert_manager.send_trade_signal(...)
```

3. **Enter Trade:**
```python
# Record position
position = Position(...)
position_manager.add_position(position)
risk_manager.add_open_position(...)
```

4. **Exit Trade:**
```python
# Close position
closed = position_manager.close_position(
    position_id=position.id,
    exit_price=15870
)

# Update risk manager
risk_manager.record_trade_result(closed.realized_pnl)
risk_manager.remove_position(position.symbol)

# Add to journal
journal.add_trade(closed)

# Send alert
await alert_manager.send_position_update(...)
```

5. **End of Day Review:**
```python
# Analyze today's performance
stats = journal.analyze_performance(days=1)
print(f"Today: {stats.total_trades} trades, ${stats.total_pnl:+.2f}")

# Get insights
insights = journal.get_insights(days=7)
# Review warnings and recommendations
```

---

## Configuration

**Environment Variables (Optional):**

```bash
# Telegram alerts
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id

# Email alerts
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
EMAIL_FROM=your_email@gmail.com
EMAIL_TO=your_email@gmail.com

# Webhook alerts
WEBHOOK_URL=https://your-webhook-url.com/alerts
```

---

## Key Takeaways

### What This Prevents

✅ **No More 75% Drawdowns**
- Daily loss limit enforced automatically
- Trading halted when limit hit

✅ **No More Revenge Trading**
- Consecutive loss protection
- Forces you to step back after 3 losses

✅ **No More Overtrading**
- Maximum 3 positions
- Position size validation

✅ **No More Low R:R Trades**
- Minimum 1.5:1 R:R required
- Automatic validation

### What This Enables

🎯 **Data-Driven Improvement**
- Know which setups work best
- Identify best trading times
- Track all metrics automatically

📊 **Professional Risk Management**
- Systematic rules enforcement
- Portfolio heat monitoring
- Position sizing calculation

🔔 **Real-Time Awareness**
- Multi-channel alerts
- Signal notifications
- Risk warnings

📈 **Continuous Learning**
- Performance analytics
- Actionable insights
- Win/loss pattern analysis

---

**Version**: 1.0.0
**Last Updated**: November 15, 2025
**Implements**: Risk Management + Trade Journal + Alerts

**Remember**: The best system is useless if you don't follow it. Let the risk manager protect you. Trust the process. 🛡️
