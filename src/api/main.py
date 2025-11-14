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
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional, List
import asyncio
import json
from datetime import datetime
from loguru import logger

# Import with error handling for missing dependencies
try:
    from src.core.config import get_settings
    settings = get_settings()
except Exception as e:
    logger.warning(f"Could not load config: {e}")
    settings = None

try:
    from src.data.market_collector import MarketPulseCollector
except Exception as e:
    logger.warning(f"Could not import MarketPulseCollector: {e}")
    MarketPulseCollector = None

try:
    from src.core.database import DatabaseManager
except Exception as e:
    logger.warning(f"Could not import DatabaseManager: {e}")
    DatabaseManager = None

try:
    from src.llm.llm_client import LLMManager, LMStudioClient
except Exception as e:
    logger.warning(f"Could not import LLM modules: {e}")
    LLMManager = None
    LMStudioClient = None

try:
    from src.analysis.ohlc_analyzer import OHLCAnalyzer
except Exception as e:
    logger.warning(f"Could not import OHLCAnalyzer: {e}")
    OHLCAnalyzer = None

# Global variables
collector = None
ohlc_analyzer = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    # Startup
    logger.info("Starting MarketPulse API...")
    global collector, ohlc_analyzer

    logger.info("Initializing global components...")

    # Initialize components with error handling
    if MarketPulseCollector:
        collector = MarketPulseCollector()
        logger.info(f"Created collector: {type(collector)}")
        try:
            await collector.initialize()
            logger.success("MarketPulse collector initialized successfully")
            logger.info(f"Collector after initialization: {collector is not None}")
        except Exception as e:
            logger.warning(f"Collector initialization failed (some features may be limited): {e}")
            # Keep collector for basic functionality
    else:
        logger.warning("MarketPulseCollector not available - running in limited mode")
        collector = None

    if OHLCAnalyzer:
        ohlc_analyzer = OHLCAnalyzer()
        logger.success("OHLC Analyzer initialized")
    else:
        logger.warning("OHLCAnalyzer not available - OHLC features disabled")
        ohlc_analyzer = None

    logger.info(f"Lifespan initialization complete. Collector: {collector is not None}")
    yield

    # Shutdown
    logger.info("Shutting down MarketPulse API...")

app = FastAPI(
    title="MarketPulse API",
    description="Real-time market internals analysis API",
    version="0.1.0",
    lifespan=lifespan
)

# CORS middleware - more permissive for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000", "http://127.0.0.1:3001"],  # Next.js dev server
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

db_manager = DatabaseManager(settings.database_url) if settings and DatabaseManager else None

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


@app.get("/")
async def root():
    """API health check"""
    return {
        "message": "MarketPulse API is running",
        "version": "0.1.0",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/test/status")
async def test_status():
    """Test endpoint to check global variables"""
    return {
        "collector_status": collector is not None,
        "collector_type": str(type(collector)) if collector else None,
        "ohlc_analyzer_status": ohlc_analyzer is not None,
        "timestamp": datetime.now().isoformat()
    }

@app.put("/api/test/data-source")
async def test_data_source(request: Dict[str, Any]):
    """Test endpoint to verify data source connectivity"""
    try:
        # Create a fresh collector for testing
        test_collector = MarketPulseCollector()
        await test_collector.initialize()

        # Test market data collection
        internals = await test_collector.collect_market_internals()

        return {
            "success": True,
            "data_source": internals.get("data_source", "unknown"),
            "symbols_collected": len([k for k in internals.keys() if isinstance(internals[k], dict) and "price" in internals[k]]),
            "sample_data": {k: v for k, v in list(internals.items())[:3]},  # First 3 items
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Data source test failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.put("/api/test/yahoo-finance")
async def test_yahoo_finance():
    """Test Yahoo Finance API connectivity specifically"""
    try:
        from ..api.yahoo_client import YahooFinanceClient
        from ..core.config import get_settings

        settings = get_settings()
        client = YahooFinanceClient(settings)

        # Test with a few symbols
        test_symbols = ["SPY", "QQQ", "AAPL"]
        results = {}

        for symbol in test_symbols:
            try:
                data = client.get_market_data([symbol])
                results[symbol] = {
                    "success": True,
                    "price": data[symbol]["price"] if symbol in data else None,
                    "change": data[symbol]["change"] if symbol in data else None,
                    "volume": data[symbol]["volume"] if symbol in data else None
                }
            except Exception as e:
                results[symbol] = {"success": False, "error": str(e)}

        return {
            "success": True,
            "yahoo_finance_results": results,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Yahoo Finance test failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.put("/api/test/data-source")
async def test_data_source(request: Dict[str, Any]):
    """Test data source connectivity with specified symbols"""
    try:
        logger.info(f"Testing data source with request: {request}")

        # Always create a fresh collector instance to avoid global variable issues
        test_collector = MarketPulseCollector()
        await test_collector.initialize()

        # Collect market data
        internals = await test_collector.collect_market_internals()

        # Analyze results
        analysis = {
            "success": True,
            "data_source": internals.get("data_source", "unknown"),
            "total_symbols": len(internals),
            "market_data": {},
            "sample_data": {},
            "timestamp": datetime.now().isoformat()
        }

        # Check for valid price data
        valid_symbols = []
        for symbol, data in internals.items():
            if isinstance(data, dict) and data.get("price", 0) > 0:
                valid_symbols.append(symbol)
                analysis["market_data"][symbol] = {
                    "price": data["price"],
                    "change": data.get("change", 0),
                    "change_pct": data.get("change_pct", 0),
                    "volume": data.get("volume", 0)
                }

        analysis["valid_symbols"] = valid_symbols
        analysis["symbols_with_prices"] = len(valid_symbols)

        # Add sample of raw data
        sample_keys = list(internals.keys())[:3]
        for key in sample_keys:
            analysis["sample_data"][key] = str(internals[key])[:200]  # First 200 chars

        logger.info(f"Data source test successful: {len(valid_symbols)} symbols with valid prices")
        return analysis

    except Exception as e:
        logger.error(f"Error in data source test: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.put("/api/test/yahoo-finance")
async def test_yahoo_finance():
    """Test Yahoo Finance client directly"""
    try:
        logger.info("Testing Yahoo Finance client directly...")

        # Use the working market collector approach
        test_collector = MarketPulseCollector()
        await test_collector.initialize()

        # Get specific test symbols
        internals = await test_collector.collect_market_internals()

        test_symbols = ["SPY", "QQQ", "AAPL", "BTC-USD", "ETH-USD"]
        results = {}

        for symbol in test_symbols:
            if symbol in internals and isinstance(internals[symbol], dict):
                data = internals[symbol]
                results[symbol] = {
                    "success": True,
                    "price": data.get("price"),
                    "change": data.get("change"),
                    "change_pct": data.get("change_pct"),
                    "volume": data.get("volume"),
                    "timestamp": data.get("timestamp"),
                    "raw_keys": list(data.keys())
                }
            else:
                results[symbol] = {"success": False, "error": "Symbol not found in response"}

        logger.info(f"Yahoo Finance test completed for {len(results)} symbols")
        return {
            "success": True,
            "yahoo_finance_results": results,
            "data_source": internals.get("data_source", "unknown"),
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error in Yahoo Finance test: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.get("/api/market/internals", response_model=MarketResponse)
async def get_market_internals():
    """Get current market internals"""
    try:
        # Always create a fresh collector instance to avoid global variable issues
        logger.info("Creating fresh collector instance for market internals")
        current_collector = MarketPulseCollector()

        # Initialize the collector
        init_result = await current_collector.initialize()
        logger.info(f"Collector initialization result: {init_result}")

        # Collect market data
        logger.info("Collecting market internals...")
        internals = await current_collector.collect_market_internals()

        if internals:
            logger.info(f"Successfully collected {len(internals)} data items")
            return MarketResponse(
                success=True,
                data=internals,
                timestamp=datetime.now().isoformat()
            )
        else:
            logger.warning("No market internals data collected")
            return MarketResponse(
                success=False,
                error="No market data available - check data source connectivity",
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
        from src.api.yahoo_client import YahooFinanceClient as AlpacaClient
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

@app.get("/api/market/macro", response_model=MarketResponse)
async def get_macro_data():
    """Get important macro economic indicators"""
    try:
        from src.api.yahoo_client import YahooFinanceClient as AlpacaClient

        # Macro symbols available in Alpaca
        macro_symbols = {
            'DXY': 'UUP',   # US Dollar Index - use UUP ETF as proxy
            'TNX': 'TNX',   # 10-Year Treasury Yield (CBOE)
            'CLF': 'CL',    # Crude Oil Futures (use CL as proxy)
            'GC': 'GLD',    # Gold - use GLD ETF as proxy
            'BTC': 'BTC-USD', # Bitcoin (if available)
            'ETH': 'ETH-USD'  # Ethereum (if available)
        }

        client = AlpacaClient(settings)

        # Use Yahoo Finance to get macro data
        macro_data = client.get_macro_data()

            # Add market session, sentiment, and sector performance from mock data
        # since these are not available from Yahoo Finance
        from .mock_market import mock_provider
        mock_data = await mock_provider.get_macro_data()
        macro_data['market_session'] = mock_data.get('market_session', 'US Regular')
        macro_data['economic_sentiment'] = mock_data.get('economic_sentiment', 'Neutral')
        macro_data['risk_appetite'] = mock_data.get('risk_appetite', 'Balanced')
        macro_data['sector_performance'] = mock_data.get('sector_performance', {})

        return MarketResponse(
            success=True,
            data=macro_data,
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error getting macro data: {e}")
        # Fallback to mock data
        try:
            from .mock_market import mock_provider
            mock_data = await mock_provider.get_macro_data()
            return MarketResponse(
                success=True,
                data=mock_data,
                timestamp=datetime.now().isoformat()
            )
        except:
            return MarketResponse(
                success=False,
                error=str(e),
                timestamp=datetime.now().isoformat()
            )

class ChatRequest(BaseModel):
    """Chat message request"""
    message: str
    context: Optional[Dict[str, Any]] = None
    symbol: Optional[str] = None
    conversation_history: Optional[List[Dict[str, str]]] = None

@app.post("/api/llm/chat", response_model=MarketResponse)
async def chat_with_llm(request: ChatRequest):
    """Chat with the LLM trading assistant"""
    try:
        llm_manager = LLMManager()

        # Build context-aware prompt
        context_info = ""
        if request.context:
            context_info = f"Current Market Context:\n{request.context}\n\n"

        if request.symbol:
            context_info += f"Primary Symbol: {request.symbol}\n"

        # Build conversation history
        conversation = []
        if request.conversation_history:
            conversation = request.conversation_history

        # Add current message
        conversation.append({
            'role': 'user',
            'content': request.message
        })

        # Get AI analysis
        response = await llm_manager.analyze_market(
            {'user_message': request.message, 'context': request.context},
            'chat'
        )

        return MarketResponse(
            success=True,
            data={'response': response},
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error in LLM chat: {e}")
        return MarketResponse(
            success=False,
            error=str(e),
            timestamp=datetime.now().isoformat()
        )

@app.websocket("/ws/market")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time market data"""
    await websocket.accept()
    logger.info("WebSocket connection established")

    try:
        # Send initial connection message
        await websocket.send_json({
            "type": "connection_established",
            "message": "Connected to MarketPulse WebSocket",
            "timestamp": datetime.now().isoformat()
        })

        # Send market data every 30 seconds
        message_count = 0
        while True:
            try:
                if collector:
                    internals = await collector.collect_market_internals()
                    await websocket.send_json({
                        "type": "market_update",
                        "data": internals,
                        "timestamp": datetime.now().isoformat(),
                        "message_id": message_count
                    })
                    message_count += 1
                else:
                    await websocket.send_json({
                        "type": "status",
                        "message": "Collector not initialized",
                        "timestamp": datetime.now().isoformat()
                    })

                await asyncio.sleep(30)
            except Exception as loop_error:
                logger.error(f"Error in WebSocket loop: {loop_error}")
                await websocket.send_json({
                    "type": "error",
                    "message": f"Error fetching data: {str(loop_error)}",
                    "timestamp": datetime.now().isoformat()
                })
                await asyncio.sleep(5)  # Wait before retrying

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": f"WebSocket error: {str(e)}",
                "timestamp": datetime.now().isoformat()
            })
        except:
            pass  # Connection already closed
    finally:
        logger.info("WebSocket connection closed")

@app.websocket("/ws/test")
async def websocket_test_endpoint(websocket: WebSocket):
    """Simple WebSocket test endpoint"""
    await websocket.accept()
    logger.info("Test WebSocket connection established")

    try:
        await websocket.send_json({
            "type": "test_connection",
            "message": "Test WebSocket is working!",
            "timestamp": datetime.now().isoformat()
        })

        # Echo back any messages received
        while True:
            try:
                data = await websocket.receive_json()
                await websocket.send_json({
                    "type": "echo",
                    "received": data,
                    "timestamp": datetime.now().isoformat()
                })
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"Error in test WebSocket: {e}")
                break

    except WebSocketDisconnect:
        logger.info("Test WebSocket disconnected")
    except Exception as e:
        logger.error(f"Test WebSocket error: {e}")
    finally:
        logger.info("Test WebSocket connection closed")

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

@app.get("/api/market/ohlc-analysis/{symbol}", response_model=MarketResponse)
async def get_ohlc_analysis(symbol: str):
    """Get comprehensive OHLC analysis for a symbol"""
    try:
        # Collect historical data for multiple timeframes
        historical_data = {}

        # Get data for each timeframe
        for tf_name, tf_config in ohlc_analyzer.timeframes.items():
            try:
                from src.api.yahoo_client import YahooFinanceClient as AlpacaClient
                client = AlpacaClient(settings)
                data = await client.get_bars(symbol, tf_config['period'], tf_config['limit'])

                if data is not None:
                        historical_data[tf_name] = {
                            'symbol': symbol,
                            'data': []
                        }

                        for _, row in data.iterrows():
                            historical_data[tf_name]['data'].append({
                                "timestamp": row.name.isoformat(),
                                "open": float(row['open']),
                                "high": float(row['high']),
                                "low": float(row['low']),
                                "close": float(row['close']),
                                "volume": int(row['volume'])
                            })
            except Exception as e:
                logger.warning(f"Could not fetch {tf_name} data for {symbol}: {e}")

        # Perform OHLC analysis
        analysis = ohlc_analyzer.analyze_symbol(
            {'historical_data': historical_data},
            symbol
        )

        return MarketResponse(
            success=True,
            data=analysis,
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error getting OHLC analysis for {symbol}: {e}")
        return MarketResponse(
            success=False,
            error=str(e),
            timestamp=datetime.now().isoformat()
        )

@app.get("/api/market/ohlc-dashboard", response_model=MarketResponse)
async def get_ohlc_dashboard():
    """Get OHLC analysis for major market symbols"""
    try:
        symbols = ['SPY', 'QQQ', 'BTC', 'ETH', 'VIX']
        dashboard_data = {
            'timestamp': datetime.now().isoformat(),
            'symbols': {},
            'market_summary': {
                'overall_trend': 'NEUTRAL',
                'trending_symbols': [],
                'key_levels': {},
                'patterns': []
            }
        }

        all_analyses = []

        for symbol in symbols:
            try:
                # Get historical data for this symbol
                historical_data = {}

                for tf_name, tf_config in ohlc_analyzer.timeframes.items():
                    try:
                        from src.api.yahoo_client import YahooFinanceClient as AlpacaClient
                        async with AlpacaClient(settings) as client:
                            data = await client.get_bars(symbol, tf_config['period'], tf_config['limit'])

                        if data is not None:
                                historical_data[tf_name] = {
                                    'symbol': symbol,
                                    'data': []
                                }

                                for _, row in data.iterrows():
                                    historical_data[tf_name]['data'].append({
                                        "timestamp": row.name.isoformat(),
                                        "open": float(row['open']),
                                        "high": float(row['high']),
                                        "low": float(row['low']),
                                        "close": float(row['close']),
                                        "volume": int(row['volume'])
                                    })
                    except Exception as e:
                        logger.warning(f"Could not fetch {tf_name} data for {symbol}: {e}")

                # Analyze the symbol
                analysis = ohlc_analyzer.analyze_symbol(
                    {'historical_data': historical_data},
                    symbol
                )

                dashboard_data['symbols'][symbol] = analysis
                all_analyses.append(analysis)

            except Exception as e:
                logger.warning(f"Could not analyze {symbol}: {e}")
                dashboard_data['symbols'][symbol] = {'error': str(e)}

        # Calculate market summary
        if all_analyses:
            # Determine overall market trend
            bullish_count = sum(1 for a in all_analyses if a.get('overall_trend') in ['BULLISH', 'STRONGLY_BULLISH'])
            bearish_count = sum(1 for a in all_analyses if a.get('overall_trend') in ['BEARISH', 'STRONGLY_BEARISH'])

            if bullish_count > bearish_count * 1.5:
                dashboard_data['market_summary']['overall_trend'] = 'STRONGLY_BULLISH'
            elif bullish_count > bearish_count:
                dashboard_data['market_summary']['overall_trend'] = 'BULLISH'
            elif bearish_count > bullish_count * 1.5:
                dashboard_data['market_summary']['overall_trend'] = 'STRONGLY_BEARISH'
            elif bearish_count > bullish_count:
                dashboard_data['market_summary']['overall_trend'] = 'BEARISH'
            else:
                dashboard_data['market_summary']['overall_trend'] = 'NEUTRAL'

            # Find trending symbols
            trending = []
            for analysis in all_analyses:
                if analysis.get('overall_trend') in ['BULLISH', 'STRONGLY_BULLISH', 'BEARISH', 'STRONGLY_BEARISH']:
                    trending.append({
                        'symbol': analysis['symbol'],
                        'trend': analysis['overall_trend'],
                        'strength': analysis.get('overall_strength', 0)
                    })

            dashboard_data['market_summary']['trending_symbols'] = trending

            # Aggregate patterns
            all_patterns = []
            for analysis in all_analyses:
                all_patterns.extend(analysis.get('patterns', []))

            # Sort by strength and get top patterns
            strength_order = {'STRONG': 3, 'MODERATE': 2, 'WEAK': 1}
            all_patterns.sort(key=lambda x: (strength_order.get(x.get('strength', 'WEAK'), 0), x.get('date', '')), reverse=True)
            dashboard_data['market_summary']['patterns'] = all_patterns[:10]

        return MarketResponse(
            success=True,
            data=dashboard_data,
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error getting OHLC dashboard: {e}")
        return MarketResponse(
            success=False,
            error=str(e),
            timestamp=datetime.now().isoformat()
        )

@app.get("/api/market/trends/{symbol}", response_model=MarketResponse)
async def get_trend_analysis(symbol: str):
    """Get focused trend analysis for a symbol"""
    try:
        # Get current market internals
        internals = await collector.collect_market_internals()

        # Get OHLC analysis for the symbol
        historical_data = {}

        for tf_name, tf_config in ohlc_analyzer.timeframes.items():
            try:
                from src.api.yahoo_client import YahooFinanceClient as AlpacaClient
                client = AlpacaClient(settings)
                data = await client.get_bars(symbol, tf_config['period'], tf_config['limit'])

                if data is not None:
                        historical_data[tf_name] = {
                            'symbol': symbol,
                            'data': []
                        }

                        for _, row in data.iterrows():
                            historical_data[tf_name]['data'].append({
                                "timestamp": row.name.isoformat(),
                                "open": float(row['open']),
                                "high": float(row['high']),
                                "low": float(row['low']),
                                "close": float(row['close']),
                                "volume": int(row['volume'])
                            })
            except Exception as e:
                logger.warning(f"Could not fetch {tf_name} data for {symbol}: {e}")

        ohlc_analysis = ohlc_analyzer.analyze_symbol(
            {'historical_data': historical_data},
            symbol
        )

        # Create focused trend report
        trend_report = {
            'symbol': symbol,
            'timestamp': datetime.now().isoformat(),
            'current_price': None,
            'market_bias': internals.get('market_bias', 'NEUTRAL'),
            'trend_analysis': {},
            'key_levels': {},
            'signals': [],
            'timeframe_consensus': {
                'bullish_timeframes': [],
                'bearish_timeframes': [],
                'neutral_timeframes': []
            }
        }

        # Extract trend information from each timeframe
        for tf_name, tf_data in ohlc_analysis.get('timeframes', {}).items():
            if 'current_price' in tf_data:
                if trend_report['current_price'] is None:
                    trend_report['current_price'] = tf_data['current_price']

            if 'trend' in tf_data:
                trend_direction = tf_data['trend'].get('direction', 'NEUTRAL')
                trend_strength = tf_data['trend'].get('strength', 'WEAK')

                trend_report['trend_analysis'][tf_name] = {
                    'direction': trend_direction,
                    'strength': trend_strength,
                    'momentum': tf_data['trend'].get('momentum_5d', 0),
                    'price_change_pct': tf_data.get('price_change_pct', 0),
                    'atr': tf_data.get('indicators', {}).get('atr', 0)
                }

                # Build consensus
                if trend_direction in ['BULLISH', 'STRONGLY_BULLISH']:
                    trend_report['timeframe_consensus']['bullish_timeframes'].append(tf_name)
                elif trend_direction in ['BEARISH', 'STRONGLY_BEARISH']:
                    trend_report['timeframe_consensus']['bearish_timeframes'].append(tf_name)
                else:
                    trend_report['timeframe_consensus']['neutral_timeframes'].append(tf_name)

        # Extract key levels
        trend_report['key_levels'] = ohlc_analysis.get('key_levels', {})

        # Extract signals
        trend_report['signals'] = ohlc_analysis.get('signals', [])

        # Add market context
        if symbol.lower() in ['spy', 'qqq']:
            trend_report['market_context'] = {
                'volatility_regime': internals.get('volatilityRegime', 'UNKNOWN'),
                'volume_flow': internals.get('volume_flow', {}),
                'correlation_strength': None
            }

            # Add SPY-QQQ correlation if analyzing SPY or QQQ
            if 'spy' in internals and 'qqq' in internals:
                spy_change = internals['spy'].get('change_pct', 0)
                qqq_change = internals['qqq'].get('change_pct', 0)

                if abs(spy_change) > 0.1 and abs(qqq_change) > 0.1:
                    correlation = (spy_change * qqq_change) / (abs(spy_change) * abs(qqq_change))
                    trend_report['market_context']['correlation_strength'] = max(min(correlation, 1.0), -1.0)

        return MarketResponse(
            success=True,
            data=trend_report,
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error getting trend analysis for {symbol}: {e}")
        return MarketResponse(
            success=False,
            error=str(e),
            timestamp=datetime.now().isoformat()
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)