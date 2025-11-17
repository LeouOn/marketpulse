# 📊 Backtesting & Optimization System

Comprehensive backtesting engine with position scaling and market regime classification for validating and optimizing trading strategies.

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Components](#components)
- [Quick Start](#quick-start)
- [API Endpoints](#api-endpoints)
- [Usage Examples](#usage-examples)
- [Performance Metrics](#performance-metrics)
- [Advanced Features](#advanced-features)

---

## Overview

The MarketPulse backtesting system allows you to:

✅ **Validate your edge statistically** - Test strategies on historical data
✅ **Optimize parameters** - Find the best settings for your strategy
✅ **Analyze performance** - Comprehensive metrics and equity curves
✅ **Scale position size** - Auto-scaling based on performance
✅ **Classify market regimes** - LLM-powered market condition analysis

## Features

### 1. Backtesting Engine

- **Historical Simulation** - Realistic trade execution on historical data
- **FVG + Divergence Strategy** - Tests the core MarketPulse edge
- **Comprehensive Metrics** - 20+ performance statistics
- **MFE/MAE Tracking** - Maximum Favorable/Adverse Excursion per trade
- **Time Analysis** - Performance by hour of day and day of week
- **Setup Analysis** - Which ICT setups perform best

### 2. Position Scaler

- **Kelly Criterion** - Mathematically optimal position sizing
- **Streak-Based Scaling** - Scale up on wins, down on losses
- **Conservative Approach** - Uses 25% Kelly for safety
- **Automatic Adjustment** - Dynamically scales based on performance

Scaling Rules:
- Start: **1 contract**
- After 3 consecutive wins: **2 contracts**
- After 6 consecutive wins: **4 contracts**
- After 2 consecutive losses: **1 contract** (reset)

### 3. Market Regime Classifier

Uses LLM (Claude 4 or local model) to classify market conditions into 5 regimes:

1. **TRENDING_BULLISH** - Strong uptrend, go long
2. **TRENDING_BEARISH** - Strong downtrend, go short
3. **RANGE_BOUND** - Sideways movement, mean reversion
4. **CHOPPY_AVOID** - High volatility, low conviction - avoid trading
5. **BREAKOUT_PENDING** - Consolidation near key levels - prepare for breakout

Each regime includes trading recommendations and risk parameters.

---

## Components

### File Structure

```
src/
├── backtesting/
│   ├── __init__.py
│   └── backtest_engine.py          # Main backtesting engine
├── analysis/
│   └── position_scaler.py          # Position sizing system
├── llm/
│   └── regime_classifier.py        # Market regime classifier
└── api/
    └── backtest_endpoints.py       # REST API endpoints

tests/
└── test_backtest.py                # Comprehensive tests
```

### Core Classes

**BacktestEngine** - Main backtesting engine
```python
from src.backtesting import BacktestEngine

engine = BacktestEngine()
results = engine.run_backtest(
    symbol='NQ',
    start_date='2024-01-01',
    end_date='2024-11-15',
    initial_capital=10000,
    contracts=1,
    interval='5m'
)
```

**PositionScaler** - Auto-scaling position size
```python
from src.analysis.position_scaler import PositionScaler, calculate_performance_stats

scaler = PositionScaler(base_contracts=1, max_contracts=8)
stats = calculate_performance_stats(trades)
recommended_size = scaler.get_recommended_size(stats, account_balance=10000)
```

**MarketRegimeClassifier** - LLM-powered regime classification
```python
from src.llm.regime_classifier import MarketRegimeClassifier, MarketData

classifier = MarketRegimeClassifier()
market_data = MarketData(
    symbol='NQ',
    current_price=16500.0,
    vix=15.5,
    atr=50.0,
    rsi=55.0
)

regime = await classifier.classify_regime(market_data)
print(f"Regime: {regime.regime}")
print(f"Recommendation: {regime.recommendation}")
```

---

## Quick Start

### 1. Run a Backtest

```python
from src.backtesting import BacktestEngine

engine = BacktestEngine()

# Run backtest on NQ futures
results = engine.run_backtest(
    symbol='NQ',
    start_date='2024-01-01',
    end_date='2024-11-15',
    initial_capital=10000,
    contracts=1,
    interval='5m'
)

# Print results
print(f"Total Trades: {results.total_trades}")
print(f"Win Rate: {results.win_rate:.1f}%")
print(f"Profit Factor: {results.profit_factor:.2f}")
print(f"Sharpe Ratio: {results.sharpe_ratio:.2f}")
print(f"Max Drawdown: {results.max_drawdown:.1f}%")
print(f"Total Return: {results.total_return:.1f}%")
```

### 2. Get Position Size Recommendation

```python
from src.analysis.position_scaler import PositionScaler, calculate_performance_stats

# Calculate stats from your recent trades
stats = calculate_performance_stats(recent_trades)

# Get recommendation
scaler = PositionScaler(base_contracts=1, max_contracts=8)
recommended = scaler.get_recommended_size(
    stats=stats,
    account_balance=10000,
    use_kelly=True
)

print(f"Recommended contracts: {recommended}")
print(f"Consecutive wins: {stats.consecutive_wins}")
print(f"Kelly fraction: {scaler.calculate_kelly_size(stats):.3f}")
```

### 3. Classify Market Regime

```python
from src.llm.regime_classifier import MarketRegimeClassifier, MarketData

classifier = MarketRegimeClassifier()

# Prepare market data
market_data = MarketData(
    symbol='NQ',
    current_price=16500.0,
    vix=15.5,
    atr=50.0,
    rsi=55.0,
    volume_ratio=1.2,
    trend_strength=0.7,
    correlation_spy=0.85
)

# Classify regime
regime = await classifier.classify_regime(market_data)

print(f"Market Regime: {regime.regime}")
print(f"Confidence: {regime.confidence}%")
print(f"Recommendation: {regime.recommendation}")
print(f"Suggested R:R: {regime.risk_reward_ratio}")
```

---

## API Endpoints

### POST `/api/backtest/run`

Run a backtest on historical data.

**Request:**
```json
{
  "symbol": "NQ",
  "start_date": "2024-01-01",
  "end_date": "2024-11-15",
  "initial_capital": 10000,
  "contracts": 1,
  "interval": "5m"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "total_trades": 42,
    "winning_trades": 28,
    "losing_trades": 14,
    "win_rate": 66.67,
    "profit_factor": 2.15,
    "sharpe_ratio": 1.82,
    "max_drawdown": 8.5,
    "total_return": 24.3,
    "equity_curve": [...],
    "trades": [...],
    "performance_by_setup": {...},
    "performance_by_hour": {...}
  }
}
```

### POST `/api/backtest/position-size`

Get optimal position size recommendation.

**Request:**
```json
{
  "recent_trades": [...],
  "account_balance": 10000,
  "base_contracts": 1,
  "max_contracts": 8,
  "use_kelly": true
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "recommended_contracts": 2,
    "kelly_fraction": 0.15,
    "consecutive_wins": 3,
    "consecutive_losses": 0,
    "win_rate": 65.0,
    "profit_factor": 2.1,
    "current_streak": "winning"
  }
}
```

### GET `/api/backtest/regime?symbol=NQ`

Classify current market regime.

**Response:**
```json
{
  "success": true,
  "data": {
    "regime": "TRENDING_BULLISH",
    "confidence": 85,
    "recommendation": "Look for pullbacks to support/FVGs for long entries. Avoid counter-trend shorts.",
    "risk_reward_ratio": 2.5,
    "suggested_stop_multiplier": 1.0,
    "analysis": "Market showing strong bullish momentum with VIX low at 14.2...",
    "market_data": {
      "symbol": "NQ",
      "current_price": 16500.0,
      "vix": 14.2,
      "atr": 48.5
    }
  }
}
```

---

## Usage Examples

### Example 1: Optimize Strategy Parameters

```python
from src.backtesting import BacktestEngine

engine = BacktestEngine()
results_by_interval = {}

# Test different timeframes
for interval in ['1m', '5m', '15m', '30m']:
    results = engine.run_backtest(
        symbol='NQ',
        start_date='2024-01-01',
        end_date='2024-11-15',
        initial_capital=10000,
        contracts=1,
        interval=interval
    )

    results_by_interval[interval] = {
        'win_rate': results.win_rate,
        'profit_factor': results.profit_factor,
        'sharpe_ratio': results.sharpe_ratio,
        'total_return': results.total_return
    }

# Find best timeframe
best_interval = max(results_by_interval.items(),
                   key=lambda x: x[1]['sharpe_ratio'])
print(f"Best interval: {best_interval[0]}")
print(f"Sharpe Ratio: {best_interval[1]['sharpe_ratio']:.2f}")
```

### Example 2: Analyze Best Trading Hours

```python
results = engine.run_backtest(
    symbol='NQ',
    start_date='2024-01-01',
    end_date='2024-11-15'
)

# Print performance by hour
print("\nPerformance by Hour of Day:")
for hour, stats in results.performance_by_hour.items():
    print(f"{hour:02d}:00 - Trades: {stats['count']}, Win Rate: {stats['win_rate']:.1f}%, Avg P&L: ${stats['avg_pnl']:.2f}")

# Find best trading hours
best_hours = sorted(
    results.performance_by_hour.items(),
    key=lambda x: x[1]['win_rate'] if x[1]['count'] >= 5 else 0,
    reverse=True
)[:3]

print("\nTop 3 Trading Hours:")
for hour, stats in best_hours:
    print(f"{hour:02d}:00 - Win Rate: {stats['win_rate']:.1f}% ({stats['count']} trades)")
```

### Example 3: Dynamic Position Sizing

```python
from src.analysis.position_scaler import PositionScaler, calculate_performance_stats

scaler = PositionScaler(
    base_contracts=1,
    max_contracts=8,
    scale_up_threshold=3,
    scale_down_threshold=2
)

# Simulate trading with dynamic sizing
account_balance = 10000
trades = []

for signal in trading_signals:
    # Calculate current stats
    stats = calculate_performance_stats(trades[-20:] if trades else [])

    # Get recommended size
    contracts = scaler.get_recommended_size(stats, account_balance)

    # Execute trade with recommended size
    trade = execute_trade(signal, contracts)
    trades.append(trade)

    # Update balance
    account_balance += trade.pnl

print(f"Final Balance: ${account_balance:.2f}")
print(f"Total Return: {(account_balance/10000 - 1)*100:.1f}%")
```

### Example 4: Regime-Based Trading

```python
from src.llm.regime_classifier import MarketRegimeClassifier, MarketData

classifier = MarketRegimeClassifier()

async def adaptive_trading_strategy():
    # Get current market data
    market_data = get_current_market_data('NQ')

    # Classify regime
    regime = await classifier.classify_regime(market_data)

    # Adjust strategy based on regime
    if regime.regime == 'TRENDING_BULLISH':
        # Look for long setups only
        signals = scan_for_long_setups()
        stop_multiplier = 1.0

    elif regime.regime == 'TRENDING_BEARISH':
        # Look for short setups only
        signals = scan_for_short_setups()
        stop_multiplier = 1.0

    elif regime.regime == 'RANGE_BOUND':
        # Mean reversion strategy
        signals = scan_for_reversal_setups()
        stop_multiplier = 0.8

    elif regime.regime == 'CHOPPY_AVOID':
        # Avoid trading
        print("Market regime is CHOPPY - sitting on hands")
        return None

    elif regime.regime == 'BREAKOUT_PENDING':
        # Wait for breakout confirmation
        signals = scan_for_breakout_setups()
        stop_multiplier = 1.2

    return signals, stop_multiplier
```

---

## Performance Metrics

The backtesting engine calculates 20+ comprehensive metrics:

### Basic Metrics

| Metric | Description |
|--------|-------------|
| **Total Trades** | Number of completed trades |
| **Winning Trades** | Number of profitable trades |
| **Losing Trades** | Number of unprofitable trades |
| **Win Rate** | Percentage of winning trades |
| **Average Winner** | Average profit per winning trade |
| **Average Loser** | Average loss per losing trade |
| **Largest Winner** | Biggest single win |
| **Largest Loser** | Biggest single loss |

### Risk-Adjusted Metrics

| Metric | Description | Good Value |
|--------|-------------|-----------|
| **Profit Factor** | Gross profit / Gross loss | > 2.0 |
| **Sharpe Ratio** | Risk-adjusted return | > 1.5 |
| **Sortino Ratio** | Downside risk-adjusted return | > 2.0 |
| **Calmar Ratio** | Return / Max Drawdown | > 3.0 |
| **Max Drawdown** | Largest peak-to-trough decline | < 15% |
| **Max Drawdown Duration** | Longest time underwater | < 30 days |

### Advanced Metrics

| Metric | Description |
|--------|-------------|
| **Total Return** | Overall percentage return |
| **Total P&L** | Total profit/loss in dollars |
| **Average Trade** | Average P&L per trade |
| **Expectancy** | Expected value per trade |
| **Average Duration** | Average trade duration (minutes) |
| **Trades Per Day** | Average number of trades per day |
| **Best Streak** | Longest winning streak |
| **Worst Streak** | Longest losing streak |

### Time-Based Analysis

- **Performance by Hour** - Which hours are most profitable
- **Performance by Day of Week** - Which days are most profitable
- **Performance by Setup Type** - Which ICT setups work best

### Trade Quality Metrics

- **MFE (Max Favorable Excursion)** - Best price reached during trade
- **MAE (Max Adverse Excursion)** - Worst price reached during trade
- **MFE/MAE Ratio** - Indicates trade quality

---

## Advanced Features

### 1. Walk-Forward Optimization

Test strategy on rolling windows to avoid overfitting:

```python
def walk_forward_optimization(
    symbol: str,
    start_date: str,
    end_date: str,
    train_months: int = 6,
    test_months: int = 1
):
    """
    Walk-forward optimization
    - Train on N months
    - Test on next M months
    - Roll forward
    """
    results = []
    current_date = start_date

    while current_date < end_date:
        # Train period
        train_start = current_date
        train_end = add_months(current_date, train_months)

        # Test period
        test_start = train_end
        test_end = add_months(test_start, test_months)

        # Optimize on train data
        best_params = optimize_parameters(symbol, train_start, train_end)

        # Test with best params
        test_results = run_backtest_with_params(
            symbol, test_start, test_end, best_params
        )

        results.append(test_results)
        current_date = test_end

    return results
```

### 2. Monte Carlo Simulation

Assess strategy robustness with randomization:

```python
def monte_carlo_simulation(trades: List[Trade], iterations: int = 1000):
    """
    Shuffle trade order to assess robustness
    Returns distribution of possible outcomes
    """
    results = []

    for i in range(iterations):
        # Randomly shuffle trades
        shuffled = random.sample(trades, len(trades))

        # Calculate equity curve
        equity = 10000
        drawdowns = []

        for trade in shuffled:
            equity += trade.pnl
            peak = max(equity_curve) if equity_curve else equity
            drawdown = (peak - equity) / peak * 100
            drawdowns.append(drawdown)

        results.append({
            'final_equity': equity,
            'max_drawdown': max(drawdowns),
            'sharpe': calculate_sharpe(shuffled)
        })

    return results
```

### 3. Multi-Symbol Portfolio

Test strategy across multiple symbols:

```python
symbols = ['NQ', 'ES', 'RTY', 'YM']  # Nasdaq, S&P, Russell, Dow
portfolio_results = {}

for symbol in symbols:
    results = engine.run_backtest(
        symbol=symbol,
        start_date='2024-01-01',
        end_date='2024-11-15'
    )
    portfolio_results[symbol] = results

# Combine results
total_trades = sum(r.total_trades for r in portfolio_results.values())
total_pnl = sum(r.total_pnl for r in portfolio_results.values())
avg_win_rate = np.mean([r.win_rate for r in portfolio_results.values()])

print(f"Portfolio Win Rate: {avg_win_rate:.1f}%")
print(f"Total P&L: ${total_pnl:.2f}")
```

---

## Best Practices

### 1. Sufficient Data

- Use at least **6 months** of historical data
- More data = more reliable statistics
- Test across different market conditions

### 2. Realistic Assumptions

- Include **slippage** (1-2 ticks per side)
- Include **commissions** ($0.50-$1.00 per contract per side)
- Use **realistic fill prices** (mid-price, not best case)

### 3. Out-of-Sample Testing

- Train on 70% of data
- Test on remaining 30%
- Never optimize on the full dataset

### 4. Multiple Metrics

- Don't optimize for just one metric
- Balance win rate, profit factor, and drawdown
- Prioritize risk-adjusted returns (Sharpe, Sortino)

### 5. Market Regime Awareness

- Test strategy in all market conditions
- Consider filtering trades by regime
- Adjust position size based on regime confidence

---

## Troubleshooting

### Issue: Low Win Rate

**Possible Causes:**
- Strategy parameters too aggressive
- Insufficient confluence required
- Not filtering by market regime

**Solutions:**
- Increase minimum divergence strength
- Require multiple confirmations (FVG + Divergence + CVD)
- Only trade in favorable regimes

### Issue: High Drawdown

**Possible Causes:**
- Position size too large
- No stop losses
- Not scaling down after losses

**Solutions:**
- Use fractional Kelly (25% instead of full)
- Implement strict stop losses (1-2 ATR)
- Enable automatic scale-down after 2 losses

### Issue: Overfitting

**Possible Causes:**
- Too many parameters
- Optimizing on small dataset
- Using in-sample data for testing

**Solutions:**
- Simplify strategy
- Use walk-forward optimization
- Always test on out-of-sample data

---

## Performance Targets

Based on professional futures traders, here are realistic targets:

| Metric | Conservative | Moderate | Aggressive |
|--------|-------------|----------|------------|
| **Win Rate** | 55-60% | 60-65% | 65-70% |
| **Profit Factor** | 1.5-2.0 | 2.0-2.5 | > 2.5 |
| **Sharpe Ratio** | 1.0-1.5 | 1.5-2.0 | > 2.0 |
| **Max Drawdown** | < 20% | < 15% | < 10% |
| **Monthly Return** | 5-10% | 10-20% | > 20% |

**Note:** Consistency matters more than absolute returns. A strategy with 8% monthly return and 5% max drawdown is better than 25% monthly with 30% drawdown.

---

## Next Steps

1. **Run Your First Backtest**
   - Use the Quick Start examples above
   - Start with default parameters
   - Analyze the results

2. **Optimize Parameters**
   - Test different timeframes
   - Adjust divergence strength threshold
   - Find best trading hours

3. **Implement Position Scaling**
   - Start with conservative settings (base=1, max=4)
   - Monitor consecutive wins/losses
   - Adjust based on account size

4. **Integrate Regime Classification**
   - Set up LLM (Claude 4 or local)
   - Test regime-based filtering
   - Compare results with/without regime awareness

5. **Paper Trade**
   - Forward test on paper account
   - Verify backtest results in live market
   - Adjust strategy as needed

---

## Support

For questions or issues:

- Check the [API Documentation](./API_ENDPOINTS.md)
- Review [System Evaluation Guide](./SYSTEM_EVALUATION.md)
- See [ICT Concepts](./ICT_CONCEPTS.md) for strategy details

---

**Last Updated:** 2024-11-16

**Version:** 1.0.0
