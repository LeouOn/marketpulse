"""
Backtesting API Endpoints

Run backtests, get performance metrics, and optimize strategies.
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
from loguru import logger

from src.backtesting.backtest_engine import BacktestEngine, BacktestResults
from src.analysis.position_scaler import PositionScaler, calculate_performance_stats
from src.llm.regime_classifier import MarketRegimeClassifier, classify_current_regime


# Initialize router
backtest_router = APIRouter(prefix="/api/backtest", tags=["Backtesting"])

# Initialize services
backtest_engine = BacktestEngine()
position_scaler = PositionScaler()
regime_classifier = MarketRegimeClassifier()


class BacktestRequest(BaseModel):
    """Backtest request"""
    symbol: str = "NQ"
    start_date: str = "2024-01-01"
    end_date: str = "2024-11-15"
    initial_capital: float = 10000
    contracts: int = 1
    interval: str = "5m"


class PositionSizeRequest(BaseModel):
    """Position size recommendation request"""
    recent_trades: List[Dict[str, Any]]
    signal_strength: float = 70.0
    account_balance: float = 10000


@backtest_router.post("/run")
async def run_backtest(request: BacktestRequest):
    """
    Run backtest on historical data

    Tests FVG + Divergence strategy on historical data and returns
    comprehensive performance metrics.

    Returns:
    - Total P&L and return percentage
    - Win rate and profit factor
    - Max drawdown
    - Sharpe ratio
    - Best time of day / day of week
    - Performance by setup type
    - Equity curve
    """
    try:
        logger.info(f"Running backtest: {request.symbol} from {request.start_date} to {request.end_date}")

        # Run backtest
        results = backtest_engine.run_backtest(
            symbol=request.symbol,
            start_date=request.start_date,
            end_date=request.end_date,
            initial_capital=request.initial_capital,
            contracts=request.contracts,
            interval=request.interval
        )

        # Convert to dict
        results_dict = {
            'basic_metrics': {
                'total_trades': results.total_trades,
                'winning_trades': results.winning_trades,
                'losing_trades': results.losing_trades,
                'win_rate': round(results.win_rate, 2)
            },
            'pnl_metrics': {
                'total_pnl': round(results.total_pnl, 2),
                'total_pnl_percent': round(results.total_pnl_percent, 2),
                'average_winner': round(results.average_winner, 2),
                'average_loser': round(results.average_loser, 2),
                'largest_winner': round(results.largest_winner, 2),
                'largest_loser': round(results.largest_loser, 2),
                'profit_factor': round(results.profit_factor, 2)
            },
            'risk_metrics': {
                'max_drawdown': round(results.max_drawdown, 4),
                'max_drawdown_percent': round(results.max_drawdown_percent, 2),
                'sharpe_ratio': round(results.sharpe_ratio, 2),
                'sortino_ratio': round(results.sortino_ratio, 2)
            },
            'trade_metrics': {
                'average_trade_duration_minutes': round(results.average_trade_duration, 1),
                'average_trade_pnl': round(results.average_trade_pnl, 2),
                'expectancy': round(results.expectancy, 2)
            },
            'strategy_metrics': {
                'fvg_success_rate': round(results.fvg_success_rate, 2),
                'divergence_success_rate': round(results.divergence_success_rate, 2),
                'best_hour_of_day': results.best_hour_of_day,
                'worst_hour_of_day': results.worst_hour_of_day,
                'best_day_of_week': results.best_day_of_week
            },
            'performance_by_setup': results.performance_by_setup,
            'equity_curve': results.equity_curve.to_dict('records') if not results.equity_curve.empty else [],
            'sample_trades': [
                {
                    'entry_time': t.entry_time.isoformat(),
                    'exit_time': t.exit_time.isoformat(),
                    'direction': t.direction,
                    'entry_price': round(t.entry_price, 2),
                    'exit_price': round(t.exit_price, 2),
                    'pnl': round(t.pnl, 2),
                    'setup_type': t.setup_type,
                    'win': t.win
                }
                for t in results.trades[:10]  # First 10 trades
            ]
        }

        return JSONResponse(content={
            "success": True,
            "data": results_dict
        })

    except Exception as e:
        logger.error(f"Error running backtest: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@backtest_router.get("/run/{symbol}")
async def run_backtest_simple(
    symbol: str,
    start_date: str = Query("2024-01-01"),
    end_date: str = Query("2024-11-15"),
    contracts: int = Query(1)
):
    """Run backtest (simple GET endpoint)"""
    request = BacktestRequest(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        contracts=contracts
    )

    return await run_backtest(request)


@backtest_router.post("/position-size")
async def get_position_size(request: PositionSizeRequest):
    """
    Get recommended position size

    Based on:
    - Recent performance (consecutive wins/losses)
    - Kelly Criterion
    - Signal strength
    - Account balance
    """
    try:
        # Convert dict trades to objects (simplified)
        from src.backtesting.backtest_engine import Trade
        from datetime import datetime

        trades = []
        for t_dict in request.recent_trades:
            trade = Trade(
                entry_time=datetime.fromisoformat(t_dict['entry_time']),
                exit_time=datetime.fromisoformat(t_dict['exit_time']),
                entry_price=t_dict['entry_price'],
                exit_price=t_dict['exit_price'],
                direction=t_dict['direction'],
                contracts=t_dict.get('contracts', 1),
                pnl=t_dict['pnl'],
                pnl_percent=t_dict.get('pnl_percent', 0),
                duration_minutes=t_dict.get('duration_minutes', 0),
                setup_type=t_dict.get('setup_type', 'UNKNOWN'),
                win=t_dict['win']
            )
            trades.append(trade)

        # Calculate stats
        stats = calculate_performance_stats(trades)

        # Get recommendation
        recommendation = position_scaler.get_size_with_confidence(
            stats=stats,
            signal_strength=request.signal_strength,
            account_balance=request.account_balance
        )

        return JSONResponse(content={
            "success": True,
            "data": recommendation
        })

    except Exception as e:
        logger.error(f"Error calculating position size: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@backtest_router.get("/regime")
async def get_market_regime(symbol: str = Query("NQ")):
    """
    Get current market regime classification

    Uses LLM to classify market as:
    - TRENDING_BULLISH
    - TRENDING_BEARISH
    - RANGE_BOUND
    - CHOPPY_AVOID
    - BREAKOUT_PENDING

    Provides trading recommendations for current regime.
    """
    try:
        logger.info(f"Classifying market regime for {symbol}")

        regime = await classify_current_regime(symbol)

        return JSONResponse(content={
            "success": True,
            "data": {
                'regime': regime.regime,
                'confidence': round(regime.confidence, 1),
                'recommended_bias': regime.recommended_bias,
                'optimal_strategy': regime.optimal_strategy,
                'key_support': round(regime.key_support, 2) if regime.key_support else None,
                'key_resistance': round(regime.key_resistance, 2) if regime.key_resistance else None,
                'reasoning': regime.reasoning,
                'timestamp': regime.timestamp.isoformat()
            }
        })

    except Exception as e:
        logger.error(f"Error classifying regime: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@backtest_router.get("/")
async def backtest_home():
    """Backtesting home page"""
    html = """
<!DOCTYPE html>
<html>
<head>
    <title>Backtesting & Optimization</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background-color: #1e1e1e;
            color: #e0e0e0;
            padding: 40px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        h1 {
            color: #26a69a;
            text-align: center;
        }
        .endpoint-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 20px;
            margin-top: 30px;
        }
        .endpoint-card {
            background-color: #2d2d2d;
            padding: 25px;
            border-radius: 10px;
            border-left: 4px solid #26a69a;
        }
        .endpoint-card h3 {
            color: #26a69a;
            margin-top: 0;
        }
        .endpoint {
            background-color: #1e1e1e;
            padding: 12px;
            border-radius: 5px;
            margin-top: 12px;
            font-family: monospace;
            font-size: 13px;
        }
        .endpoint a {
            color: #64b5f6;
            text-decoration: none;
        }
        .info-box {
            background-color: #2d2d2d;
            padding: 25px;
            border-radius: 10px;
            margin-top: 30px;
            border-left: 4px solid #FFD700;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Backtesting & Optimization</h1>
        <p style="text-align: center; color: #888;">
            Validate your edge, optimize parameters, and adapt to market conditions
        </p>

        <div class="endpoint-grid">
            <div class="endpoint-card">
                <h3>🔬 Run Backtest</h3>
                <p>Test FVG + Divergence strategy on historical data</p>
                <div class="endpoint">
                    <a href="/api/backtest/run/NQ?start_date=2024-01-01&end_date=2024-11-15" target="_blank">
                        GET /api/backtest/run/{symbol}
                    </a>
                </div>
                <p style="font-size: 12px; color: #888; margin-top: 10px;">
                    Returns: Win rate, P&L, Sharpe ratio, drawdown, best setups
                </p>
            </div>

            <div class="endpoint-card">
                <h3>📏 Position Sizing</h3>
                <p>Get optimal position size based on performance</p>
                <div class="endpoint">
                    POST /api/backtest/position-size
                </div>
                <p style="font-size: 12px; color: #888; margin-top: 10px;">
                    Uses Kelly Criterion + consecutive performance
                </p>
            </div>

            <div class="endpoint-card">
                <h3>🎯 Market Regime</h3>
                <p>AI-powered market condition classification</p>
                <div class="endpoint">
                    <a href="/api/backtest/regime?symbol=NQ" target="_blank">
                        GET /api/backtest/regime?symbol=NQ
                    </a>
                </div>
                <p style="font-size: 12px; color: #888; margin-top: 10px;">
                    Trending, ranging, choppy, or breakout pending
                </p>
            </div>
        </div>

        <div class="info-box">
            <h3>📈 Performance Metrics</h3>
            <p>Backtesting provides comprehensive metrics:</p>
            <ul>
                <li><strong>Win Rate:</strong> Percentage of winning trades</li>
                <li><strong>Profit Factor:</strong> Gross profit / gross loss</li>
                <li><strong>Sharpe Ratio:</strong> Risk-adjusted returns</li>
                <li><strong>Max Drawdown:</strong> Largest peak-to-trough decline</li>
                <li><strong>Expectancy:</strong> Average $ per trade</li>
                <li><strong>FVG Success Rate:</strong> Win rate for FVG setups</li>
                <li><strong>Best Time of Day:</strong> Most profitable hours</li>
            </ul>
        </div>

        <div class="info-box" style="border-left-color: #26a69a;">
            <h3>⚖️ Position Sizing Strategy</h3>
            <p>Auto-scale position size based on performance:</p>
            <ul>
                <li>Start with 1 contract (base size)</li>
                <li>After 3 consecutive wins → 2 contracts</li>
                <li>After 6 consecutive wins → 4 contracts</li>
                <li>After 2 consecutive losses → back to 1 contract</li>
                <li>Combined with Kelly Criterion for optimal sizing</li>
            </ul>
        </div>

        <div class="info-box" style="border-left-color: #64b5f6;">
            <h3>🌊 Market Regimes</h3>
            <p>AI classifies market into 5 regimes:</p>
            <ul>
                <li><strong>TRENDING_BULLISH:</strong> Favor longs, wide stops</li>
                <li><strong>TRENDING_BEARISH:</strong> Favor shorts, wide stops</li>
                <li><strong>RANGE_BOUND:</strong> Trade both directions, tight stops</li>
                <li><strong>CHOPPY_AVOID:</strong> Reduce size or avoid</li>
                <li><strong>BREAKOUT_PENDING:</strong> Wait for direction</li>
            </ul>
        </div>
    </div>
</body>
</html>
    """
    return HTMLResponse(content=html)
