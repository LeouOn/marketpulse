"""
Risk Management and Trade Journal API Endpoints

Endpoints for:
- Risk validation
- Position sizing
- Trade journaling
- Performance analytics
- Alert management
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from loguru import logger

from src.analysis.risk_manager import RiskManager, RiskLevel
from src.state.position_manager import PositionManager, Position, PositionSide, PositionStatus
from src.journal.trade_tracker import TradeJournal
from src.alerts.alert_manager import AlertManager, AlertPriority
import uuid


# Request/Response models

class TradeValidationRequest(BaseModel):
    """Request to validate a trade"""
    symbol: str
    entry_price: float
    stop_loss: float
    take_profit: float
    direction: str  # "long" or "short"
    contracts: int = 1
    point_value: float = 2.0


class PositionRequest(BaseModel):
    """Request to open a position"""
    symbol: str
    side: str  # "long" or "short"
    entry_price: float
    stop_loss: float
    take_profit: float
    contracts: int
    setup_type: Optional[str] = None
    signal_confidence: Optional[float] = None
    cvd_at_entry: Optional[float] = None
    vix_at_entry: Optional[float] = None
    session: Optional[str] = None
    tags: List[str] = []
    notes: Optional[str] = None
    point_value: float = 2.0


class ClosePositionRequest(BaseModel):
    """Request to close a position"""
    position_id: str
    exit_price: float
    exit_reason: Optional[str] = None  # "target_hit", "stopped_out", "manual"


class RecordTradeRequest(BaseModel):
    """Request to record trade P&L"""
    pnl: float


class PerformanceRequest(BaseModel):
    """Request for performance analysis"""
    days: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class SendAlertRequest(BaseModel):
    """Request to send an alert"""
    title: str
    message: str
    priority: str = "medium"  # low, medium, high, critical


# Initialize router
risk_router = APIRouter(prefix="/api/risk", tags=["Risk Management"])
journal_router = APIRouter(prefix="/api/journal", tags=["Trade Journal"])
alerts_router = APIRouter(prefix="/api/alerts", tags=["Alerts"])

# Initialize managers (in production, these would be singletons or dependency-injected)
risk_manager = RiskManager()
position_manager = PositionManager()
trade_journal = TradeJournal()
alert_manager = AlertManager()


# ============================================================================
# RISK MANAGEMENT ENDPOINTS
# ============================================================================

@risk_router.post("/validate-trade")
async def validate_trade(request: TradeValidationRequest):
    """
    Validate a trade against risk rules

    Returns approval status, warnings, and suggested position size
    """
    try:
        validation = risk_manager.validate_trade(
            symbol=request.symbol,
            entry_price=request.entry_price,
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
            direction=request.direction,
            contracts=request.contracts,
            point_value=request.point_value
        )

        return {
            "success": True,
            "data": {
                "approved": validation.approved,
                "reason": validation.reason,
                "warnings": validation.warnings,
                "suggested_contracts": validation.suggested_contracts,
                "risk_metrics": {
                    "entry_price": validation.risk_metrics.entry_price if validation.risk_metrics else None,
                    "stop_loss": validation.risk_metrics.stop_loss if validation.risk_metrics else None,
                    "take_profit": validation.risk_metrics.take_profit if validation.risk_metrics else None,
                    "total_risk": validation.risk_metrics.total_risk if validation.risk_metrics else None,
                    "total_reward": validation.risk_metrics.total_reward if validation.risk_metrics else None,
                    "risk_reward_ratio": validation.risk_metrics.risk_reward_ratio if validation.risk_metrics else None,
                    "risk_percentage": validation.risk_metrics.risk_percentage if validation.risk_metrics else None
                } if validation.risk_metrics else None
            }
        }

    except Exception as e:
        logger.error(f"Error validating trade: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@risk_router.post("/calculate-position-size")
async def calculate_position_size(
    entry_price: float = Query(...),
    stop_loss: float = Query(...),
    direction: str = Query(...),
    risk_amount: Optional[float] = Query(None),
    point_value: float = Query(2.0)
):
    """
    Calculate optimal position size based on risk

    Args:
        entry_price: Entry price
        stop_loss: Stop loss price
        direction: "long" or "short"
        risk_amount: Dollar amount to risk (optional, defaults to max_position_risk)
        point_value: Dollar value per point (default: 2.0 for MNQ)

    Returns:
        Suggested number of contracts
    """
    try:
        contracts = risk_manager.calculate_position_size(
            entry_price=entry_price,
            stop_loss=stop_loss,
            direction=direction,
            risk_amount=risk_amount,
            point_value=point_value
        )

        # Calculate actual risk
        if direction.lower() == "long":
            risk_points = entry_price - stop_loss
        else:
            risk_points = stop_loss - entry_price

        total_risk = abs(risk_points) * point_value * contracts

        return {
            "success": True,
            "data": {
                "contracts": contracts,
                "risk_points": abs(risk_points),
                "total_risk": total_risk,
                "risk_per_contract": abs(risk_points) * point_value
            }
        }

    except Exception as e:
        logger.error(f"Error calculating position size: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@risk_router.post("/record-trade-result")
async def record_trade_result(request: RecordTradeRequest):
    """
    Record trade result and update risk state

    Updates daily P&L and consecutive loss counter
    """
    try:
        risk_manager.record_trade_result(request.pnl)

        summary = risk_manager.get_risk_summary()

        return {
            "success": True,
            "data": {
                "trade_recorded": True,
                "daily_pnl": summary['daily_pnl'],
                "consecutive_losses": summary['consecutive_losses'],
                "can_trade": summary['can_trade'],
                "risk_level": summary['risk_level']
            }
        }

    except Exception as e:
        logger.error(f"Error recording trade result: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@risk_router.get("/risk-summary")
async def get_risk_summary():
    """
    Get current risk summary

    Includes daily P&L, portfolio heat, consecutive losses, etc.
    """
    try:
        summary = risk_manager.get_risk_summary()

        return {
            "success": True,
            "data": summary
        }

    except Exception as e:
        logger.error(f"Error getting risk summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@risk_router.post("/reset-daily")
async def reset_daily_stats():
    """
    Reset daily statistics (call at start of new trading day)
    """
    try:
        risk_manager.reset_daily_stats()

        return {
            "success": True,
            "message": "Daily statistics reset"
        }

    except Exception as e:
        logger.error(f"Error resetting daily stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# POSITION MANAGEMENT ENDPOINTS
# ============================================================================

@risk_router.post("/positions/open")
async def open_position(request: PositionRequest):
    """
    Open a new position

    Validates risk and records position
    """
    try:
        # First validate the trade
        validation = risk_manager.validate_trade(
            symbol=request.symbol,
            entry_price=request.entry_price,
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
            direction=request.side,
            contracts=request.contracts,
            point_value=request.point_value
        )

        if not validation.approved:
            return {
                "success": False,
                "error": validation.reason,
                "warnings": validation.warnings
            }

        # Create position
        position = Position(
            id=str(uuid.uuid4()),
            symbol=request.symbol,
            side=PositionSide.LONG if request.side.lower() == "long" else PositionSide.SHORT,
            entry_price=request.entry_price,
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
            contracts=request.contracts,
            entry_timestamp=datetime.now(),
            status=PositionStatus.OPEN,
            setup_type=request.setup_type,
            signal_confidence=request.signal_confidence,
            cvd_at_entry=request.cvd_at_entry,
            vix_at_entry=request.vix_at_entry,
            session=request.session,
            tags=request.tags,
            point_value=request.point_value
        )

        # Add to position manager
        position_manager.add_position(position)

        # Update risk manager
        risk_manager.add_open_position(
            symbol=request.symbol,
            entry_price=request.entry_price,
            stop_loss=request.stop_loss,
            contracts=request.contracts,
            direction=request.side,
            point_value=request.point_value
        )

        # Send alert (if configured)
        try:
            await alert_manager.send_position_update(
                symbol=request.symbol,
                action="OPENED",
                price=request.entry_price,
                priority=AlertPriority.MEDIUM
            )
        except:
            pass  # Don't fail if alert fails

        return {
            "success": True,
            "data": {
                "position_id": position.id,
                "warnings": validation.warnings
            }
        }

    except Exception as e:
        logger.error(f"Error opening position: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@risk_router.post("/positions/close")
async def close_position(request: ClosePositionRequest):
    """
    Close an open position
    """
    try:
        # Determine status
        status_map = {
            "target_hit": PositionStatus.TARGET_HIT,
            "stopped_out": PositionStatus.STOPPED_OUT,
            "manual": PositionStatus.CLOSED
        }
        status = status_map.get(request.exit_reason, PositionStatus.CLOSED)

        # Close position
        position = position_manager.close_position(
            position_id=request.position_id,
            exit_price=request.exit_price,
            status=status
        )

        if not position:
            raise HTTPException(status_code=404, detail="Position not found")

        # Update risk manager
        risk_manager.record_trade_result(position.realized_pnl)
        risk_manager.remove_position(position.symbol)

        # Add to journal
        trade_journal.add_trade(position)

        # Send alert
        try:
            await alert_manager.send_position_update(
                symbol=position.symbol,
                action=status.value.upper(),
                price=request.exit_price,
                pnl=position.realized_pnl,
                priority=AlertPriority.HIGH if position.realized_pnl > 0 else AlertPriority.MEDIUM
            )
        except:
            pass

        return {
            "success": True,
            "data": {
                "position_id": position.id,
                "realized_pnl": position.realized_pnl,
                "exit_price": request.exit_price,
                "status": status.value
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error closing position: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@risk_router.get("/positions/open")
async def get_open_positions():
    """Get all open positions"""
    try:
        positions = position_manager.get_all_open_positions()

        return {
            "success": True,
            "data": {
                "positions": [
                    {
                        "id": p.id,
                        "symbol": p.symbol,
                        "side": p.side.value,
                        "entry_price": p.entry_price,
                        "stop_loss": p.stop_loss,
                        "take_profit": p.take_profit,
                        "contracts": p.contracts,
                        "entry_timestamp": p.entry_timestamp.isoformat(),
                        "setup_type": p.setup_type,
                        "risk_amount": p.risk_amount
                    }
                    for p in positions
                ],
                "total_positions": len(positions),
                "total_risk": position_manager.get_total_portfolio_risk()
            }
        }

    except Exception as e:
        logger.error(f"Error getting open positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@risk_router.get("/positions/state")
async def get_position_state():
    """Get position manager state summary"""
    try:
        summary = position_manager.get_state_summary()

        return {
            "success": True,
            "data": summary
        }

    except Exception as e:
        logger.error(f"Error getting position state: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# TRADE JOURNAL ENDPOINTS
# ============================================================================

@journal_router.post("/analyze")
async def analyze_performance(request: PerformanceRequest):
    """
    Analyze trading performance

    Returns comprehensive statistics including win rate, profit factor, etc.
    """
    try:
        # Load trades from position manager
        trade_journal.load_trades(position_manager.closed_positions)

        stats = trade_journal.analyze_performance(
            days=request.days,
            start_date=request.start_date,
            end_date=request.end_date
        )

        return {
            "success": True,
            "data": {
                "total_trades": stats.total_trades,
                "winning_trades": stats.winning_trades,
                "losing_trades": stats.losing_trades,
                "win_rate": f"{stats.win_rate:.2f}%",
                "total_pnl": stats.total_pnl,
                "gross_profit": stats.gross_profit,
                "gross_loss": stats.gross_loss,
                "average_win": stats.average_win,
                "average_loss": stats.average_loss,
                "largest_win": stats.largest_win,
                "largest_loss": stats.largest_loss,
                "profit_factor": stats.profit_factor,
                "average_rr": stats.average_rr,
                "expectancy": stats.expectancy,
                "max_drawdown": stats.max_drawdown,
                "max_drawdown_pct": f"{stats.max_drawdown_pct:.2f}%",
                "sharpe_ratio": stats.sharpe_ratio,
                "consecutive_wins": stats.consecutive_wins,
                "consecutive_losses": stats.consecutive_losses,
                "max_consecutive_wins": stats.max_consecutive_wins,
                "max_consecutive_losses": stats.max_consecutive_losses,
                "best_setup": stats.best_setup,
                "worst_setup": stats.worst_setup,
                "best_session": stats.best_session,
                "worst_session": stats.worst_session
            }
        }

    except Exception as e:
        logger.error(f"Error analyzing performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@journal_router.get("/insights")
async def get_insights(days: int = Query(30)):
    """
    Get actionable trading insights

    Returns recommendations and warnings based on recent performance
    """
    try:
        trade_journal.load_trades(position_manager.closed_positions)
        insights = trade_journal.get_insights(days=days)

        return {
            "success": True,
            "data": insights
        }

    except Exception as e:
        logger.error(f"Error getting insights: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@journal_router.get("/by-setup")
async def analyze_by_setup(days: Optional[int] = Query(None)):
    """Analyze performance by setup type"""
    try:
        trade_journal.load_trades(position_manager.closed_positions)
        analyses = trade_journal.analyze_by_setup(days=days)

        return {
            "success": True,
            "data": {
                "setups": [
                    {
                        "setup_type": a.setup_type,
                        "total_trades": a.total_trades,
                        "win_rate": f"{a.win_rate:.2f}%",
                        "profit_factor": a.profit_factor,
                        "total_pnl": a.total_pnl,
                        "average_pnl": a.average_pnl,
                        "best_trade": a.best_trade,
                        "worst_trade": a.worst_trade
                    }
                    for a in analyses
                ]
            }
        }

    except Exception as e:
        logger.error(f"Error analyzing by setup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@journal_router.get("/by-session")
async def analyze_by_session(days: Optional[int] = Query(None)):
    """Analyze performance by trading session"""
    try:
        trade_journal.load_trades(position_manager.closed_positions)
        analyses = trade_journal.analyze_by_session(days=days)

        return {
            "success": True,
            "data": {
                "sessions": [
                    {
                        "session": a.session,
                        "total_trades": a.total_trades,
                        "win_rate": f"{a.win_rate:.2f}%",
                        "total_pnl": a.total_pnl,
                        "average_pnl": a.average_pnl
                    }
                    for a in analyses
                ]
            }
        }

    except Exception as e:
        logger.error(f"Error analyzing by session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ALERT ENDPOINTS
# ============================================================================

@alerts_router.post("/send")
async def send_alert(request: SendAlertRequest):
    """Send a custom alert"""
    try:
        priority_map = {
            "low": AlertPriority.LOW,
            "medium": AlertPriority.MEDIUM,
            "high": AlertPriority.HIGH,
            "critical": AlertPriority.CRITICAL
        }

        priority = priority_map.get(request.priority.lower(), AlertPriority.MEDIUM)

        results = await alert_manager.send_alert(
            title=request.title,
            message=request.message,
            priority=priority
        )

        return {
            "success": True,
            "data": {
                "sent_to": [ch.value for ch, success in results.items() if success],
                "failed": [ch.value for ch, success in results.items() if not success]
            }
        }

    except Exception as e:
        logger.error(f"Error sending alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))
