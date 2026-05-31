"""
AI Trading Analyst API Endpoints

Natural language interface for market analysis powered by:
- Massive.com institutional data
- Claude 4 reasoning
- MarketPulse technical analysis
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from loguru import logger
import asyncio
import json

from src.ai.massive_analyst import MassiveAIAnalyst, TradingContext


# Initialize router
ai_router = APIRouter(prefix="/api/ai", tags=["AI Trading Analyst"])

# Global analyst instance (will be initialized on first use)
analyst: Optional[MassiveAIAnalyst] = None


def get_analyst() -> MassiveAIAnalyst:
    """Get or create AI analyst instance"""
    global analyst
    if analyst is None:
        analyst = MassiveAIAnalyst()
    return analyst


class QueryRequest(BaseModel):
    """Natural language query request"""
    question: str
    symbol: Optional[str] = None
    timeframe: str = "1d"
    period: str = "3mo"
    include_technical_analysis: bool = True


class TradeRecommendationRequest(BaseModel):
    """Trade recommendation request"""
    symbol: str
    timeframe: str = "1d"
    period: str = "3mo"
    account_size: float = 10000.0
    risk_per_trade: float = 0.02


class TradeValidationRequest(BaseModel):
    """Trade validation request"""
    symbol: str
    entry_price: float
    stop_loss: float
    take_profit: float
    direction: str  # LONG or SHORT
    contracts: int = 1


@ai_router.post("/query")
async def query_ai_analyst(request: QueryRequest):
    """
    Query AI trading analyst with natural language

    Ask questions like:
    - "How is AAPL performing right now compared to MSFT?"
    - "Should I buy Tesla?"
    - "What's the best entry for MNQ futures?"
    - "Analyze the divergences on SPY"

    The AI has access to:
    - Real-time market data (Massive.com)
    - Technical analysis (divergences, ICT, indicators)
    - Risk management validation
    """
    try:
        analyst = get_analyst()

        # Create trading context if symbol provided
        context = None
        if request.symbol:
            context = TradingContext(
                symbol=request.symbol,
                timeframe=request.timeframe,
                period=request.period
            )

        # Query the AI
        response = await analyst.query(
            question=request.question,
            context=context,
            include_technical_analysis=request.include_technical_analysis
        )

        return JSONResponse(content={
            "success": True,
            "data": {
                "question": request.question,
                "response": response,
                "timestamp": datetime.now().isoformat()
            }
        })

    except Exception as e:
        logger.error(f"Error in AI query: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@ai_router.get("/query/{symbol}")
async def query_symbol(
    symbol: str,
    question: str = Query(..., description="Natural language question about the symbol"),
    timeframe: str = Query("1d"),
    period: str = Query("3mo")
):
    """
    Query AI analyst about a specific symbol (GET endpoint)

    Examples:
    - /api/ai/query/AAPL?question=Should I buy this stock?
    - /api/ai/query/MNQ?question=Give me entry and exit levels
    - /api/ai/query/SPY?question=Analyze divergences and trend
    """
    request = QueryRequest(
        question=question,
        symbol=symbol,
        timeframe=timeframe,
        period=period
    )

    return await query_ai_analyst(request)


@ai_router.post("/recommend")
async def get_trade_recommendation(request: TradeRecommendationRequest):
    """
    Get comprehensive trade recommendation from AI

    Returns:
    - Entry price
    - Stop loss
    - Take profit
    - Direction (LONG/SHORT)
    - Position size
    - Risk-reward ratio
    - Key factors
    - Risks
    """
    try:
        analyst = get_analyst()

        context = TradingContext(
            symbol=request.symbol,
            timeframe=request.timeframe,
            period=request.period,
            account_size=request.account_size,
            risk_per_trade=request.risk_per_trade
        )

        recommendation = await analyst.get_trade_recommendation(
            symbol=request.symbol,
            context=context
        )

        return JSONResponse(content={
            "success": True,
            "data": recommendation
        })

    except Exception as e:
        logger.error(f"Error getting trade recommendation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@ai_router.get("/recommend/{symbol}")
async def get_trade_recommendation_simple(
    symbol: str,
    timeframe: str = Query("1d"),
    period: str = Query("3mo")
):
    """
    Get trade recommendation (simple GET endpoint)

    Example:
    - /api/ai/recommend/AAPL
    - /api/ai/recommend/MNQ?timeframe=5m&period=1d
    """
    request = TradeRecommendationRequest(
        symbol=symbol,
        timeframe=timeframe,
        period=period
    )

    return await get_trade_recommendation(request)


@ai_router.post("/validate")
async def validate_trade(request: TradeValidationRequest):
    """
    Validate a trade against risk management rules

    Checks:
    - Risk per trade (max 2%)
    - Reward-to-risk ratio (min 1.5:1)
    - Daily loss limits
    - Portfolio heat
    - Consecutive losses
    """
    try:
        analyst = get_analyst()

        validation = await analyst.validate_trade(
            symbol=request.symbol,
            entry_price=request.entry_price,
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
            direction=request.direction,
            contracts=request.contracts
        )

        return JSONResponse(content={
            "success": True,
            "data": validation
        })

    except Exception as e:
        logger.error(f"Error validating trade: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@ai_router.get("/status")
async def get_ai_status():
    """Get AI analyst status and configuration"""
    try:
        analyst = get_analyst()

        import os
        status = {
            "massive_api_configured": bool(os.getenv('MASSIVE_API_KEY')),
            "anthropic_api_configured": bool(os.getenv('ANTHROPIC_API_KEY')),
            "agent_initialized": analyst.agent is not None,
            "message_history_length": len(analyst.message_history),
            "features": {
                "divergence_detection": True,
                "ict_analysis": True,
                "risk_management": True,
                "technical_indicators": True,
                "massive_mcp_server": bool(os.getenv('MASSIVE_API_KEY'))
            }
        }

        return JSONResponse(content={
            "success": True,
            "data": status
        })

    except Exception as e:
        logger.error(f"Error getting AI status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@ai_router.get("/")
async def ai_home():
    """AI Trading Analyst home page"""
    from fastapi.responses import HTMLResponse

    html = """
<!DOCTYPE html>
<html>
<head>
    <title>AI Trading Analyst</title>
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
        .description {
            text-align: center;
            color: #888;
            margin-bottom: 40px;
        }
        .feature-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-top: 30px;
        }
        .feature-card {
            background-color: #2d2d2d;
            padding: 25px;
            border-radius: 10px;
            border-left: 4px solid #26a69a;
        }
        .feature-card h3 {
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
        .info-box h3 {
            color: #FFD700;
            margin-top: 0;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🤖 AI Trading Analyst</h1>
        <div class="description">
            <p>Powered by Massive.com + Claude 4 + MarketPulse</p>
            <p>Natural language interface for institutional-grade market analysis</p>
        </div>

        <div class="feature-grid">
            <div class="feature-card">
                <h3>💬 Natural Language Queries</h3>
                <p>Ask questions in plain English about any market</p>
                <div class="endpoint">
                    POST /api/ai/query<br>
                    <a href="/api/ai/query/AAPL?question=Should I buy this stock?" target="_blank">
                        GET /api/ai/query/{symbol}
                    </a>
                </div>
            </div>

            <div class="feature-card">
                <h3>📊 Trade Recommendations</h3>
                <p>Get complete trade setups with entry, stop, and target</p>
                <div class="endpoint">
                    <a href="/api/ai/recommend/AAPL" target="_blank">
                        GET /api/ai/recommend/{symbol}
                    </a>
                </div>
            </div>

            <div class="feature-card">
                <h3>✅ Trade Validation</h3>
                <p>Validate trades against risk management rules</p>
                <div class="endpoint">
                    POST /api/ai/validate
                </div>
            </div>

            <div class="feature-card">
                <h3>⚡ Real-Time Data</h3>
                <p>Institutional-grade data from Massive.com</p>
                <ul>
                    <li>Stock prices</li>
                    <li>Options chains</li>
                    <li>Historical data</li>
                    <li>News & sentiment</li>
                </ul>
            </div>

            <div class="feature-card">
                <h3>📈 Technical Analysis</h3>
                <p>MarketPulse's advanced analysis systems</p>
                <ul>
                    <li>Divergence detection</li>
                    <li>ICT concepts (FVG, Order Blocks)</li>
                    <li>Indicators & trends</li>
                    <li>Support/resistance</li>
                </ul>
            </div>

            <div class="feature-card">
                <h3>🎯 Risk Management</h3>
                <p>Automated risk validation</p>
                <ul>
                    <li>2% max risk per trade</li>
                    <li>1.5:1 min R:R</li>
                    <li>Daily loss limits</li>
                    <li>Position sizing</li>
                </ul>
            </div>
        </div>

        <div class="info-box">
            <h3>💡 Example Queries</h3>
            <ul>
                <li>"How is AAPL performing right now compared to MSFT?"</li>
                <li>"Should I buy Tesla based on the latest data?"</li>
                <li>"Give me entry and exit levels for MNQ futures"</li>
                <li>"Analyze SPY divergences and tell me if it's a good short"</li>
                <li>"What's the best risk-reward setup for NVDA?"</li>
                <li>"Compare the last 5 years of returns for META vs GOOGL"</li>
            </ul>
        </div>

        <div class="info-box" style="border-left-color: #26a69a;">
            <h3>🚀 Quick Start</h3>
            <ol>
                <li>Set environment variables:
                    <pre>MASSIVE_API_KEY=your_key
ANTHROPIC_API_KEY=your_key</pre>
                </li>
                <li>Query the AI:
                    <pre>curl "http://localhost:8000/api/ai/query/AAPL?question=Should+I+buy+this?"</pre>
                </li>
                <li>Get trade recommendations:
                    <pre>curl "http://localhost:8000/api/ai/recommend/MNQ"</pre>
                </li>
            </ol>
        </div>

        <div class="info-box" style="border-left-color: #64b5f6;">
            <h3>📚 Documentation</h3>
            <p>See <code>AI_TRADING_ANALYST.md</code> for complete documentation, examples, and best practices.</p>
        </div>
    </div>
</body>
</html>
    """
    return HTMLResponse(content=html)
