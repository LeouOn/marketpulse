#!/usr/bin/env python3
"""
MarketPulse FastAPI Application
Real-time market internals analysis API
"""

import sys
import os
from pathlib import Path

# Add the project root to Python path for absolute imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import asyncio
import json
from datetime import datetime
from loguru import logger

from src.core.config import get_settings
from src.data.market_collector import MarketPulseCollector
from src.core.database import DatabaseManager
from src.llm.llm_client import LLMManager
from src.core.cache import cache_manager

app = FastAPI(
    title="MarketPulse API",
    description="Real-time market internals analysis API",
    version="0.1.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Next.js dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

settings = get_settings()
db_manager = DatabaseManager(settings.database_url)
collector = MarketPulseCollector()

class MarketResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: str

class UserComment(BaseModel):
    """User comment on LLM analysis"""
    analysis_id: str
    comment: str
    user_id: Optional[str] = "anonymous"
    timestamp: Optional[str] = None

class RefinedAnalysisRequest(BaseModel):
    """Request for refined analysis based on user feedback"""
    original_analysis: str
    user_comments: List[str]
    additional_context: Optional[Dict[str, Any]] = None
    focus_areas: Optional[List[str]] = None

class ChartAnalysisRequest(BaseModel):
    """Request for chart data analysis"""
    chart_data: Dict[str, Any]
    analysis_type: str = "technical"
    specific_questions: Optional[List[str]] = None

@app.on_event("startup")
async def startup_event():
    """Initialize the application on startup"""
    logger.info("Starting MarketPulse API...")

    # Initialize cache manager
    cache_connected = await cache_manager.connect()
    if cache_connected:
        logger.info("Redis cache enabled")
    else:
        logger.warning("Redis cache unavailable - running without cache")

    await collector.initialize()

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down MarketPulse API...")
    await cache_manager.disconnect()

@app.get("/")
async def root():
    """API health check"""
    return {
        "message": "MarketPulse API is running",
        "version": "0.1.0",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/market/internals", response_model=MarketResponse)
async def get_market_internals():
    """Get current market internals"""
    try:
        internals = await collector.collect_market_internals()
        return MarketResponse(
            success=True,
            data=internals,
            timestamp=datetime.now().isoformat()
        )
    except Exception as e:
        logger.error(f"Error fetching market internals: {e}")
        return MarketResponse(
            success=False,
            error=str(e),
            timestamp=datetime.now().isoformat()
        )

@app.get("/api/market/dashboard", response_model=MarketResponse)
async def get_dashboard_data():
    """Get dashboard data with AI analysis"""
    try:
        # Try to get from cache first
        cached_data = await cache_manager.get_dashboard_data()
        if cached_data:
            logger.debug("Serving dashboard data from cache")
            return MarketResponse(
                success=True,
                data=cached_data,
                timestamp=datetime.now().isoformat()
            )

        internals = await collector.collect_market_internals()

        # Calculate market bias
        market_bias = "NEUTRAL"
        if 'spy' in internals and 'qqq' in internals:
            spy_trend = internals['spy']['change']
            qqq_trend = internals['qqq']['change']

            if spy_trend > 0 and qqq_trend > 0:
                market_bias = "BULLISH"
            elif spy_trend < 0 and qqq_trend < 0:
                market_bias = "BEARISH"
            else:
                market_bias = "MIXED"

        # Get AI analysis
        ai_analysis = None
        try:
            ai_analysis = await collector.analyze_with_ai(internals, 'quick')
        except Exception as e:
            logger.warning(f"AI analysis failed: {e}")

        dashboard_data = {
            "timestamp": datetime.now().isoformat(),
            "marketBias": market_bias,
            "volatilityRegime": collector._classify_volatility(internals),
            "symbols": {
                "spy": internals.get('spy'),
                "qqq": internals.get('qqq'),
                "vix": internals.get('vix')
            },
            "volumeFlow": internals.get('volume_flow', {}),
            "aiAnalysis": ai_analysis
        }

        # Cache the dashboard data (30 second TTL)
        await cache_manager.set_dashboard_data(dashboard_data, ttl=30)

        return MarketResponse(
            success=True,
            data=dashboard_data,
            timestamp=datetime.now().isoformat()
        )
    except Exception as e:
        logger.error(f"Error fetching dashboard data: {e}")
        return MarketResponse(
            success=False,
            error=str(e),
            timestamp=datetime.now().isoformat()
        )

@app.get("/api/market/historical", response_model=MarketResponse)
async def get_historical_data(
    symbol: str,
    timeframe: str = "1Min",
    limit: int = 100
):
    """Get historical price data for a symbol"""
    try:
        # Try to get from cache first
        cached_data = await cache_manager.get_historical_data(symbol, timeframe, limit)
        if cached_data:
            logger.debug(f"Serving historical data for {symbol} from cache")
            return MarketResponse(
                success=True,
                data={"symbol": symbol, "data": cached_data},
                timestamp=datetime.now().isoformat()
            )

        from src.api.alpaca_client import AlpacaClient
        async with AlpacaClient(settings) as client:
            data = await client.get_bars(symbol, timeframe, limit)

            if data is not None:
                historical_data = []
                for _, row in data.iterrows():
                    historical_data.append({
                        "timestamp": row.name.isoformat(),
                        "open": float(row['open']),
                        "high": float(row['high']),
                        "low": float(row['low']),
                        "close": float(row['close']),
                        "volume": int(row['volume'])
                    })

                # Cache historical data (5 minute TTL)
                await cache_manager.set_historical_data(
                    symbol, timeframe, limit, historical_data, ttl=300
                )

                return MarketResponse(
                    success=True,
                    data={"symbol": symbol, "data": historical_data},
                    timestamp=datetime.now().isoformat()
                )
            else:
                return MarketResponse(
                    success=False,
                    error="No data available",
                    timestamp=datetime.now().isoformat()
                )
    except Exception as e:
        logger.error(f"Error fetching historical data: {e}")
        return MarketResponse(
            success=False,
            error=str(e),
            timestamp=datetime.now().isoformat()
        )

@app.get("/api/market/ai-analysis", response_model=MarketResponse)
async def get_ai_analysis():
    """Get AI analysis of current market conditions"""
    try:
        internals = await collector.collect_market_internals()
        analysis = await collector.analyze_with_ai(internals, 'quick')
        
        return MarketResponse(
            success=True,
            data={"analysis": analysis},
            timestamp=datetime.now().isoformat()
        )
    except Exception as e:
        logger.error(f"Error getting AI analysis: {e}")
        return MarketResponse(
            success=False,
            error=str(e),
            timestamp=datetime.now().isoformat()
        )

@app.websocket("/ws/market")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time market data"""
    await websocket.accept()
    try:
        while True:
            # Send market data every 30 seconds
            internals = await collector.collect_market_internals()
            await websocket.send_json({
                "type": "market_update",
                "data": internals,
                "timestamp": datetime.now().isoformat()
            })
            await asyncio.sleep(30)
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await websocket.close()

@app.post("/api/llm/comment", response_model=MarketResponse)
async def add_user_comment(comment: UserComment):
    """Add user comment to LLM analysis"""
    try:
        # Store comment in database
        comment_data = {
            'analysis_id': comment.analysis_id,
            'user_id': comment.user_id,
            'comment': comment.comment,
            'timestamp': comment.timestamp or datetime.now().isoformat()
        }
        
        db_manager.save_user_comment(comment_data)
        
        return MarketResponse(
            success=True,
            data={"message": "Comment added successfully", "comment_id": comment.analysis_id},
            timestamp=datetime.now().isoformat()
        )
    except Exception as e:
        logger.error(f"Error adding comment: {e}")
        return MarketResponse(
            success=False,
            error=str(e),
            timestamp=datetime.now().isoformat()
        )

@app.post("/api/llm/refine", response_model=MarketResponse)
async def refine_analysis(request: RefinedAnalysisRequest):
    """Refine LLM analysis based on user comments"""
    try:
        llm_manager = LLMManager()
        
        # Build refinement prompt
        comments_text = "\n".join([f"- {comment}" for comment in request.user_comments])
        focus_text = f"Focus on: {', '.join(request.focus_areas)}" if request.focus_areas else ""
        
        refinement_prompt = f"""
        Original Analysis:
        {request.original_analysis}

        User Comments/Feedback:
        {comments_text}

        {focus_text}

        Please refine the analysis addressing the user feedback. 
        Provide an improved analysis that incorporates their perspectives 
        and focuses on the areas they mentioned.

        Additional Context:
        {json.dumps(request.additional_context, indent=2) if request.additional_context else 'None'}

        Provide a refined, more accurate analysis.
        """
        
        messages = [{'role': 'user', 'content': refinement_prompt}]
        
        async with LMStudioClient() as client:
            response = await client.generate_completion(
                model='deep_analysis',
                messages=messages,
                max_tokens=400,
                temperature=0.4
            )
            
            if response and 'choices' in response:
                refined_analysis = response['choices'][0]['message']['content']
                
                return MarketResponse(
                    success=True,
                    data={
                        "refined_analysis": refined_analysis,
                        "original_analysis": request.original_analysis,
                        "user_comments_count": len(request.user_comments)
                    },
                    timestamp=datetime.now().isoformat()
                )
        
        return MarketResponse(
            success=False,
            error="Failed to generate refined analysis",
            timestamp=datetime.now().isoformat()
        )
        
    except Exception as e:
        logger.error(f"Error refining analysis: {e}")
        return MarketResponse(
            success=False,
            error=str(e),
            timestamp=datetime.now().isoformat()
        )

@app.post("/api/llm/analyze-chart", response_model=MarketResponse)
async def analyze_chart(request: ChartAnalysisRequest):
    """Analyze text-encoded chart data"""
    try:
        llm_manager = LLMManager()
        
        # Use the chart interpretation method
        async with LMStudioClient() as client:
            analysis = await client.interpret_text_chart_data(request.chart_data)
            
            if analysis:
                return MarketResponse(
                    success=True,
                    data={
                        "chart_analysis": analysis,
                        "symbol": request.chart_data.get('symbol'),
                        "timeframe": request.chart_data.get('timeframe')
                    },
                    timestamp=datetime.now().isoformat()
                )
            else:
                return MarketResponse(
                    success=False,
                    error="Failed to analyze chart data",
                    timestamp=datetime.now().isoformat()
                )
                
    except Exception as e:
        logger.error(f"Error analyzing chart: {e}")
        return MarketResponse(
            success=False,
            error=str(e),
            timestamp=datetime.now().isoformat()
        )

@app.get("/api/llm/validation/sanity-check", response_model=MarketResponse)
async def run_sanity_check():
    """Run sanity check on current market data"""
    try:
        # Collect current market data
        internals = await collector.collect_market_internals()
        
        if not internals:
            return MarketResponse(
                success=False,
                error="No market data available for validation",
                timestamp=datetime.now().isoformat()
            )
        
        # Run validation
        async with LMStudioClient() as client:
            validation_result = await client.validate_data_interpretation(internals, "market_internals")
            
            return MarketResponse(
                success=True,
                data={
                    "validation_result": validation_result,
                    "market_data": internals
                },
                timestamp=datetime.now().isoformat()
            )
            
    except Exception as e:
        logger.error(f"Error running sanity check: {e}")
        return MarketResponse(
            success=False,
            error=str(e),
            timestamp=datetime.now().isoformat()
        )

@app.get("/api/llm/conversation-history/{analysis_id}", response_model=MarketResponse)
async def get_conversation_history(analysis_id: str):
    """Get conversation history for an analysis"""
    try:
        # Retrieve from database
        history = db_manager.get_analysis_conversation(analysis_id)
        
        return MarketResponse(
            success=True,
            data={
                "analysis_id": analysis_id,
                "conversation_history": history,
                "turns_count": len(history) if history else 0
            },
            timestamp=datetime.now().isoformat()
        )
        
    except Exception as e:
        logger.error(f"Error retrieving conversation history: {e}")
        return MarketResponse(
            success=False,
            error=str(e),
            timestamp=datetime.now().isoformat()
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)