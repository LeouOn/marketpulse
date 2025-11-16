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
model_cache = {"models": None, "timestamp": None, "cache_duration": 300}  # 5 minutes cache

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

@app.get("/api/market/breadth", response_model=MarketResponse)
async def get_market_breadth():
    """Get market breadth indicators (A/D, TICK, VOLD, McClellan)"""
    try:
        from src.data.market_breadth import MarketBreadthCollector

        collector = MarketBreadthCollector()
        breadth_data = collector.get_market_internals()

        return MarketResponse(
            success=True,
            data=breadth_data,
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error getting market breadth data: {e}")
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
        # Add system prompt for trading assistant
        system_prompt = """You are a professional AI trading assistant. You help users analyze market conditions,
        understand trading strategies, and provide insights about financial markets. Always be helpful,
        educational, and responsible with your advice. Never provide guaranteed financial advice.

        When users ask about market data, reference the provided context. When you don't have specific data,
        acknowledge the limitations and provide general guidance."""

        # Build enhanced context-aware prompt
        context_info = ""
        if request.context:
            # Handle enhanced context with symbol detection
            context_data = request.context
            context_info = f"Current Market Context:\n{json.dumps(context_data, indent=2)}\n\n"

            # Add symbol-specific context information
            if 'detected_symbols' in context_data and context_data['detected_symbols']:
                detected_syms = context_data['detected_symbols']
                context_info += f"Symbols Mentioned: {', '.join(detected_syms)}\n"

            # Add query type context
            if 'query_type' in context_data:
                query_type = context_data['query_type']
                context_info += f"Query Type: {query_type}\n"

                # Add specialized instructions based on query type
                if query_type == 'trend_analysis':
                    context_info += "Focus on trend direction, momentum, and price patterns.\n"
                elif query_type == 'technical_levels':
                    context_info += "Focus on support/resistance levels and price targets.\n"
                elif query_type == 'volatility_analysis':
                    context_info += "Focus on volatility patterns, risk assessment, and timing.\n"
                elif query_type == 'trading_strategy':
                    context_info += "Focus on actionable strategies, entries, exits, and risk management.\n"
                elif query_type == 'symbol_specific':
                    context_info += "Focus analysis on the detected symbols mentioned.\n"

        if request.symbol:
            context_info += f"Primary Symbol: {request.symbol}\n"

        # Build conversation history in OpenAI format
        messages = []

        # Add system message
        messages.append({
            'role': 'system',
            'content': system_prompt
        })

        # Add conversation history (excluding the last user message as we'll add it separately)
        if request.conversation_history:
            for msg in request.conversation_history[-6:]:  # Keep last 6 messages for context
                messages.append({
                    'role': msg['role'],
                    'content': msg['content']
                })

        # Add context as a system message if available
        if context_info:
            messages.append({
                'role': 'system',
                'content': context_info
            })

        # Add current user message
        messages.append({
            'role': 'user',
            'content': request.message
        })

        # Try to get response from LM Studio with longer timeout
        response_text = None

        try:
            # Use asyncio.wait_for to handle timeout
            async with LMStudioClient() as client:
                # Get the preferred model or use default
                selected_model = getattr(LMStudioClient, 'default_model', 'aquif-3.5-max-42b-a3b-i1')

                response = await asyncio.wait_for(
                    client.generate_completion(
                        model=selected_model,  # Use the selected model
                        messages=messages,
                        max_tokens=500,  # Allow longer responses for chat
                        temperature=0.7  # More conversational temperature
                    ),
                    timeout=180.0  # 3 minutes timeout
                )

                if response and 'choices' in response and len(response['choices']) > 0:
                    response_text = response['choices'][0]['message']['content']
                    logger.info(f"Successfully got response from LM Studio")

        except asyncio.TimeoutError:
            logger.error("LM Studio request timed out after 3 minutes")
            return MarketResponse(
                success=False,
                error="The AI request timed out after 3 minutes. The query might be too complex or the AI service is overloaded. Please try again with a simpler question.",
                timestamp=datetime.now().isoformat()
            )
        except Exception as e:
            logger.error(f"LM Studio error: {e}")

        # If LM Studio failed, try to provide a helpful fallback response
        if not response_text:
            logger.warning("LM Studio failed, providing fallback response")

            # Simple fallback responses based on common patterns
            message_lower = request.message.lower()

            if "trend" in message_lower and request.symbol:
                response_text = f"I apologize, but I'm having trouble connecting to my AI analysis service right now. However, I can tell you that for {request.symbol}, you should look at multiple timeframes to determine the current trend. Check for higher highs and higher lows for an uptrend, or lower highs and lower lows for a downtrend."
            elif "market" in message_lower:
                response_text = "I apologize, but I'm having trouble connecting to my AI analysis service right now. For general market analysis, I recommend looking at the major indices (SPY, QQQ), volatility (VIX), and market breadth indicators to get a complete picture of market conditions."
            elif "buy" in message_lower or "sell" in message_lower:
                response_text = "I apologize, but I'm having trouble connecting to my AI analysis service right now. Remember that trading decisions should be based on your own analysis, risk tolerance, and strategy. Always use proper risk management and never risk more than you're willing to lose."
            else:
                response_text = "I apologize, but I'm having trouble connecting to my AI analysis service right now. This could be due to technical difficulties with the LM Studio service. Please check if LM Studio is running and try again in a moment."

        return MarketResponse(
            success=True,
            data={'response': response_text},
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error in LLM chat: {e}")
        return MarketResponse(
            success=False,
            error=f"An error occurred while processing your request: {str(e)}",
            timestamp=datetime.now().isoformat()
        )

class ModelSelectionRequest(BaseModel):
    """Model selection request"""
    model_id: str
    provider: str = "lm_studio"  # lm_studio or openrouter

@app.get("/api/llm/models", response_model=MarketResponse)
async def get_available_models():
    """Get available models from LM Studio and cache them"""
    try:
        current_time = datetime.now().timestamp()

        # Check if cache is valid
        if (model_cache["models"] and
            model_cache["timestamp"] and
            current_time - model_cache["timestamp"] < model_cache["cache_duration"]):

            return MarketResponse(
                success=True,
                data={
                    "models": model_cache["models"],
                    "cached": True,
                    "cache_age": int(current_time - model_cache["timestamp"]),
                    "provider": "lm_studio"
                },
                timestamp=datetime.now().isoformat()
            )

        # Fetch fresh models from LM Studio
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("http://localhost:1234/v1/models", timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        models_data = await response.json()

                        # Extract model information
                        models = []
                        for model in models_data.get("data", []):
                            model_info = {
                                "id": model.get("id"),
                                "object": model.get("object"),
                                "owned_by": model.get("owned_by"),
                                "size": _estimate_model_size(model.get("id", "")),
                                "recommended": model.get("id") == "aquif-3.5-max-42b-a3b-i1"
                            }
                            models.append(model_info)

                        # Update cache
                        model_cache["models"] = models
                        model_cache["timestamp"] = current_time

                        return MarketResponse(
                            success=True,
                            data={
                                "models": models,
                                "cached": False,
                                "cache_age": 0,
                                "provider": "lm_studio",
                                "total_count": len(models)
                            },
                            timestamp=datetime.now().isoformat()
                        )
                    else:
                        raise Exception(f"LM Studio API returned status {response.status}")

        except Exception as lm_error:
            logger.warning(f"Could not fetch models from LM Studio: {lm_error}")

            # Return cached models if available, even if expired
            if model_cache["models"]:
                return MarketResponse(
                    success=True,
                    data={
                        "models": model_cache["models"],
                        "cached": True,
                        "cache_age": int(current_time - model_cache["timestamp"]) if model_cache["timestamp"] else 999999,
                        "provider": "lm_studio",
                        "warning": "Using stale cache - LM Studio unavailable"
                    },
                    timestamp=datetime.now().isoformat()
                )

            # Fallback models if no cache available
            fallback_models = [
                {
                    "id": "aquif-3.5-max-42b-a3b-i1",
                    "object": "model",
                    "owned_by": "organization_owner",
                    "size": "42B",
                    "recommended": True
                }
            ]

            return MarketResponse(
                success=True,
                data={
                    "models": fallback_models,
                    "cached": False,
                    "cache_age": 0,
                    "provider": "fallback",
                    "warning": "LM Studio unavailable - using fallback models"
                },
                timestamp=datetime.now().isoformat()
            )

    except Exception as e:
        logger.error(f"Error fetching models: {e}")
        return MarketResponse(
            success=False,
            error=str(e),
            timestamp=datetime.now().isoformat()
        )

def _estimate_model_size(model_id: str) -> str:
    """Estimate model size from model ID"""
    model_id_lower = model_id.lower()

    if "42b" in model_id_lower or "70b" in model_id_lower:
        return "42B-70B"
    elif "32b" in model_id_lower or "36b" in model_id_lower:
        return "32B-36B"
    elif "24b" in model_id_lower or "27b" in model_id_lower:
        return "24B-27B"
    elif "18b" in model_id_lower:
        return "18B"
    elif "14b" in model_id_lower or "12b" in model_id_lower:
        return "12B-14B"
    elif "8b" in model_id_lower:
        return "8B"
    else:
        return "Unknown"

@app.post("/api/llm/select-model", response_model=MarketResponse)
async def select_model(request: ModelSelectionRequest):
    """Select a specific model for LLM chat"""
    try:
        # Validate model is available
        models_response = await get_available_models()
        if models_response.success and models_response.data:
            available_models = models_response.data.get("models", [])
            model_ids = [model["id"] for model in available_models]

            if request.model_id not in model_ids:
                return MarketResponse(
                    success=False,
                    error=f"Model '{request.model_id}' not available. Available models: {', '.join(model_ids[:5])}...",
                    timestamp=datetime.now().isoformat()
                )

        # Update the LM Studio client default model
        if hasattr(LMStudioClient, 'default_model'):
            LMStudioClient.default_model = request.model_id

        return MarketResponse(
            success=True,
            data={
                "selected_model": request.model_id,
                "provider": request.provider,
                "message": f"Model '{request.model_id}' selected successfully"
            },
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error selecting model: {e}")
        return MarketResponse(
            success=False,
            error=str(e),
            timestamp=datetime.now().isoformat()
        )

@app.get("/api/llm/model-status", response_model=MarketResponse)
async def get_model_status():
    """Get current model status and LM Studio connection"""
    try:
        import aiohttp

        status_info = {
            "lm_studio_connected": False,
            "current_model": getattr(LMStudioClient, 'default_model', 'aquif-3.5-max-42b-a3b-i1'),
            "last_check": datetime.now().isoformat(),
            "response_time_ms": None
        }

        # Test LM Studio connection
        try:
            start_time = datetime.now().timestamp()
            async with aiohttp.ClientSession() as session:
                async with session.get("http://localhost:1234/v1/models", timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        status_info["lm_studio_connected"] = True
                        status_info["response_time_ms"] = int((datetime.now().timestamp() - start_time) * 1000)
        except Exception as connection_error:
            logger.warning(f"LM Studio connection test failed: {connection_error}")
            status_info["connection_error"] = str(connection_error)

        return MarketResponse(
            success=True,
            data=status_info,
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error getting model status: {e}")
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
                from src.api.yahoo_client import YahooFinanceClient
                client = YahooFinanceClient(settings)
                data = client.get_bars(symbol, tf_config['period'], tf_config.get('interval', '1d'))

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
                else:
                    logger.warning(f"No data returned for {symbol} {tf_name}")
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
                        from src.api.yahoo_client import YahooFinanceClient
                        client = YahooFinanceClient(settings)
                        data = client.get_bars(symbol, tf_config['period'], tf_config.get('interval', '1d'))

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
                from src.api.yahoo_client import YahooFinanceClient
                client = YahooFinanceClient(settings)
                data = client.get_bars(symbol, tf_config['period'], tf_config.get('interval', '1d'))

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

# ==================== OPTIONS ENDPOINTS ====================

@app.get("/api/options/expirations/{symbol}", response_model=MarketResponse)
async def get_options_expirations(symbol: str):
    """Get available options expiration dates for a symbol"""
    try:
        from ..api.yahoo_client import YahooFinanceClient

        client = YahooFinanceClient(settings)
        expirations = client.get_options_expirations(symbol.upper())

        return MarketResponse(
            success=True,
            data={
                'symbol': symbol.upper(),
                'expirations': expirations,
                'count': len(expirations)
            },
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error fetching options expirations for {symbol}: {e}")
        return MarketResponse(
            success=False,
            error=str(e),
            timestamp=datetime.now().isoformat()
        )


@app.get("/api/options/chain/{symbol}/{expiration}", response_model=MarketResponse)
async def get_options_chain(symbol: str, expiration: str, include_greeks: bool = True):
    """Get options chain with calculated Greeks for specific expiration"""
    try:
        from ..api.yahoo_client import YahooFinanceClient
        from ..analysis.options_pricing import BlackScholesCalculator

        client = YahooFinanceClient(settings)

        # Get options chain
        chain_data = client.get_options_chain(symbol.upper(), expiration)

        if 'error' in chain_data:
            return MarketResponse(
                success=False,
                error=chain_data['error'],
                timestamp=datetime.now().isoformat()
            )

        # Calculate Greeks if requested
        if include_greeks and chain_data['underlying_price']:
            risk_free_rate = client.get_risk_free_rate()
            dividend_yield = client.get_dividend_yield(symbol.upper())
            T = BlackScholesCalculator.days_to_expiration(expiration)
            S = chain_data['underlying_price']

            # Enhance calls with Greeks
            for call in chain_data['calls']:
                if call.get('impliedVolatility', 0) > 0:
                    result = BlackScholesCalculator.calculate_option_with_greeks(
                        S=S,
                        K=call['strike'],
                        T=T,
                        r=risk_free_rate,
                        sigma=call['impliedVolatility'],
                        q=dividend_yield,
                        option_type='call'
                    )
                    call['theoretical_price'] = round(result.price, 4)
                    call['greeks'] = {
                        'delta': round(result.greeks.delta, 4),
                        'gamma': round(result.greeks.gamma, 6),
                        'theta': round(result.greeks.theta, 4),
                        'vega': round(result.greeks.vega, 4),
                        'rho': round(result.greeks.rho, 4)
                    }

            # Enhance puts with Greeks
            for put in chain_data['puts']:
                if put.get('impliedVolatility', 0) > 0:
                    result = BlackScholesCalculator.calculate_option_with_greeks(
                        S=S,
                        K=put['strike'],
                        T=T,
                        r=risk_free_rate,
                        sigma=put['impliedVolatility'],
                        q=dividend_yield,
                        option_type='put'
                    )
                    put['theoretical_price'] = round(result.price, 4)
                    put['greeks'] = {
                        'delta': round(result.greeks.delta, 4),
                        'gamma': round(result.greeks.gamma, 6),
                        'theta': round(result.greeks.theta, 4),
                        'vega': round(result.greeks.vega, 4),
                        'rho': round(result.greeks.rho, 4)
                    }

        return MarketResponse(
            success=True,
            data=chain_data,
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error fetching options chain for {symbol} {expiration}: {e}")
        return MarketResponse(
            success=False,
            error=str(e),
            timestamp=datetime.now().isoformat()
        )


class SingleLegRequest(BaseModel):
    """Request model for single leg analysis"""
    symbol: str
    strike: float
    expiration: str
    option_type: str  # 'call' or 'put'
    position_type: str = 'long'  # 'long' or 'short'
    contracts: int = 1


@app.post("/api/options/analyze/single-leg", response_model=MarketResponse)
async def analyze_single_leg(request: SingleLegRequest):
    """Analyze a single options leg with full risk metrics"""
    try:
        from ..api.yahoo_client import YahooFinanceClient
        from ..analysis.options_analyzer import OptionsAnalyzer

        client = YahooFinanceClient(settings)
        analyzer = OptionsAnalyzer(client)

        # Perform analysis
        analysis = analyzer.analyze_single_leg(
            symbol=request.symbol.upper(),
            strike=request.strike,
            expiration=request.expiration,
            option_type=request.option_type.lower(),
            position_type=request.position_type.lower(),
            contracts=request.contracts
        )

        if not analysis:
            return MarketResponse(
                success=False,
                error="Could not analyze option - check symbol, strike, and expiration",
                timestamp=datetime.now().isoformat()
            )

        # Generate P&L chart data
        pnl_chart = analyzer.generate_pnl_chart_data(analysis)

        # Convert to dictionary
        result = {
            'symbol': analysis.symbol,
            'option_type': analysis.option_type,
            'strike': analysis.strike,
            'expiration': analysis.expiration,
            'underlying_price': analysis.underlying_price,
            'pricing': {
                'theoretical_price': round(analysis.theoretical_price, 4),
                'market_price': round(analysis.market_price, 4),
                'bid': round(analysis.bid, 4),
                'ask': round(analysis.ask, 4),
                'mid_price': round(analysis.mid_price, 4),
                'implied_volatility': round(analysis.implied_volatility, 4)
            },
            'greeks': {
                'delta': round(analysis.greeks.delta, 4),
                'gamma': round(analysis.greeks.gamma, 6),
                'theta': round(analysis.greeks.theta, 4),
                'vega': round(analysis.greeks.vega, 4),
                'rho': round(analysis.greeks.rho, 4)
            },
            'position': {
                'type': analysis.position_type,
                'contracts': analysis.contracts,
                'cost_basis': round(analysis.cost_basis, 2),
                'theta_decay_per_day': round(analysis.theta_decay_per_day, 2)
            },
            'risk_metrics': {
                'breakeven': round(analysis.breakeven, 2),
                'max_profit': round(analysis.max_profit, 2) if analysis.max_profit else None,
                'max_loss': round(analysis.max_loss, 2) if analysis.max_loss else None,
                'risk_reward_ratio': round(analysis.risk_reward_ratio, 2) if analysis.risk_reward_ratio else None,
                'probability_profit': round(analysis.probability_profit, 2)
            },
            'time_metrics': {
                'days_to_expiration': analysis.days_to_expiration,
                'expiration_date': analysis.expiration
            },
            'pnl_chart': pnl_chart
        }

        return MarketResponse(
            success=True,
            data=result,
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error analyzing single leg: {e}")
        return MarketResponse(
            success=False,
            error=str(e),
            timestamp=datetime.now().isoformat()
        )


class ScreenOptionsRequest(BaseModel):
    """Request model for options screening"""
    screen_type: str = 'otm_calls'  # 'otm_calls', 'otm_puts', 'high_iv', etc.
    symbols: Optional[List[str]] = None  # If None, uses default watchlist
    min_delta: float = 0.20
    max_delta: float = 0.45
    min_days_to_expiry: int = 14
    max_days_to_expiry: int = 60
    min_volume: int = 100
    min_open_interest: int = 100


@app.post("/api/options/screen", response_model=MarketResponse)
async def screen_options(request: ScreenOptionsRequest):
    """Screen for options opportunities based on criteria"""
    try:
        from ..api.yahoo_client import YahooFinanceClient
        from ..analysis.options_analyzer import OptionsAnalyzer

        client = YahooFinanceClient(settings)
        analyzer = OptionsAnalyzer(client)

        # Use default symbols if none provided
        symbols = request.symbols or ['SPY', 'QQQ', 'AAPL', 'TSLA', 'NVDA', 'MSFT']

        opportunities = []

        for symbol in symbols:
            try:
                # Get available expirations
                expirations = client.get_options_expirations(symbol)

                # Filter expirations by date range
                from datetime import date, timedelta
                today = date.today()
                min_date = today + timedelta(days=request.min_days_to_expiry)
                max_date = today + timedelta(days=request.max_days_to_expiry)

                valid_expirations = [
                    exp for exp in expirations
                    if min_date <= datetime.strptime(exp, '%Y-%m-%d').date() <= max_date
                ]

                # Screen each expiration
                for expiration in valid_expirations[:3]:  # Limit to first 3 expirations
                    chain_data = client.get_options_chain(symbol, expiration)

                    if 'error' in chain_data or not chain_data['underlying_price']:
                        continue

                    # Filter options based on criteria
                    options_to_check = chain_data['calls'] if request.screen_type == 'otm_calls' else chain_data['puts']

                    for opt in options_to_check:
                        # Check volume and OI filters
                        if opt.get('volume', 0) < request.min_volume:
                            continue
                        if opt.get('openInterest', 0) < request.min_open_interest:
                            continue

                        # Analyze this option
                        analysis = analyzer.analyze_single_leg(
                            symbol=symbol,
                            strike=opt['strike'],
                            expiration=expiration,
                            option_type='call' if request.screen_type == 'otm_calls' else 'put',
                            position_type='long',
                            contracts=1
                        )

                        if analysis:
                            # Check delta filter
                            delta_abs = abs(analysis.greeks.delta)
                            if request.min_delta <= delta_abs <= request.max_delta:
                                opportunities.append({
                                    'symbol': symbol,
                                    'strike': analysis.strike,
                                    'expiration': expiration,
                                    'option_type': analysis.option_type,
                                    'underlying_price': analysis.underlying_price,
                                    'market_price': round(analysis.market_price, 2),
                                    'delta': round(analysis.greeks.delta, 3),
                                    'gamma': round(analysis.greeks.gamma, 4),
                                    'theta': round(analysis.greeks.theta, 2),
                                    'implied_volatility': round(analysis.implied_volatility, 3),
                                    'volume': opt.get('volume', 0),
                                    'open_interest': opt.get('openInterest', 0),
                                    'days_to_expiration': analysis.days_to_expiration,
                                    'breakeven': round(analysis.breakeven, 2),
                                    'probability_profit': round(analysis.probability_profit, 1)
                                })

            except Exception as e:
                logger.warning(f"Error screening {symbol}: {e}")
                continue

        # Sort by probability of profit (or other criteria)
        opportunities.sort(key=lambda x: x['probability_profit'], reverse=True)

        return MarketResponse(
            success=True,
            data={
                'screen_type': request.screen_type,
                'criteria': request.dict(),
                'opportunities': opportunities[:20],  # Return top 20
                'total_found': len(opportunities)
            },
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error screening options: {e}")
        return MarketResponse(
            success=False,
            error=str(e),
            timestamp=datetime.now().isoformat()
        )


class CoveredCallRequest(BaseModel):
    """Request model for covered call analysis"""
    symbol: str
    shares_owned: int
    strike: float
    expiration: str
    contracts: Optional[int] = None


@app.post("/api/options/strategy/covered-call", response_model=MarketResponse)
async def analyze_covered_call_strategy(request: CoveredCallRequest):
    """Analyze a covered call strategy"""
    try:
        from ..api.yahoo_client import YahooFinanceClient
        from ..analysis.strategy_builder import StrategyBuilder

        client = YahooFinanceClient(settings)
        builder = StrategyBuilder(client)

        analysis = builder.analyze_covered_call(
            symbol=request.symbol.upper(),
            shares_owned=request.shares_owned,
            strike=request.strike,
            expiration=request.expiration,
            contracts=request.contracts
        )

        if not analysis:
            return MarketResponse(
                success=False,
                error="Could not analyze covered call strategy",
                timestamp=datetime.now().isoformat()
            )

        result = {
            'symbol': analysis.symbol,
            'strategy_type': 'covered_call',
            'position': {
                'shares_owned': analysis.shares_owned,
                'contracts': analysis.contracts,
                'stock_price': round(analysis.stock_price, 2)
            },
            'short_call': {
                'strike': analysis.strike,
                'expiration': analysis.expiration,
                'premium_received': round(analysis.premium_received, 2),
                'total_premium': round(analysis.total_premium, 2)
            },
            'metrics': {
                'cost_basis_reduction': round(analysis.cost_basis_reduction, 2),
                'downside_protection_pct': round(analysis.downside_protection, 2),
                'upside_cap': round(analysis.upside_cap, 2),
                'breakeven': round(analysis.breakeven, 2)
            },
            'returns': {
                'max_profit': round(analysis.max_profit, 2),
                'max_loss': round(analysis.max_loss, 2),
                'return_if_called_pct': round(analysis.return_if_called, 2),
                'annualized_return_pct': round(analysis.annualized_return, 2)
            },
            'greeks': {
                'delta': round(analysis.delta, 4),
                'theta': round(analysis.theta, 4)
            },
            'probability': {
                'max_profit': round(analysis.probability_max_profit, 1)
            },
            'days_to_expiration': analysis.days_to_expiration
        }

        return MarketResponse(
            success=True,
            data=result,
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error analyzing covered call: {e}")
        return MarketResponse(
            success=False,
            error=str(e),
            timestamp=datetime.now().isoformat()
        )


class SpreadRequest(BaseModel):
    """Request model for spread analysis"""
    symbol: str
    long_strike: float
    short_strike: float
    expiration: str
    contracts: int = 1


@app.post("/api/options/strategy/bull-call-spread", response_model=MarketResponse)
async def analyze_bull_call_spread_strategy(request: SpreadRequest):
    """Analyze a bull call spread strategy"""
    try:
        from ..api.yahoo_client import YahooFinanceClient
        from ..analysis.strategy_builder import StrategyBuilder

        client = YahooFinanceClient(settings)
        builder = StrategyBuilder(client)

        analysis = builder.analyze_bull_call_spread(
            symbol=request.symbol.upper(),
            long_strike=request.long_strike,
            short_strike=request.short_strike,
            expiration=request.expiration,
            contracts=request.contracts
        )

        if not analysis:
            return MarketResponse(
                success=False,
                error="Could not analyze bull call spread",
                timestamp=datetime.now().isoformat()
            )

        result = {
            'symbol': analysis.symbol,
            'strategy_type': 'bull_call_spread',
            'legs': {
                'long_call': {
                    'strike': analysis.long_strike,
                    'premium': round(analysis.long_premium, 2)
                },
                'short_call': {
                    'strike': analysis.short_strike,
                    'premium': round(analysis.short_premium, 2)
                }
            },
            'pricing': {
                'net_debit': round(analysis.net_debit, 2),
                'total_cost': round(analysis.total_cost, 2),
                'spread_width': analysis.spread_width
            },
            'risk_metrics': {
                'max_profit': round(analysis.max_profit, 2),
                'max_loss': round(analysis.max_loss, 2),
                'breakeven': round(analysis.breakeven, 2),
                'risk_reward_ratio': round(analysis.risk_reward_ratio, 2),
                'max_return_pct': round(analysis.max_return_pct, 1)
            },
            'greeks': {
                'net_delta': round(analysis.net_delta, 4),
                'net_theta': round(analysis.net_theta, 4),
                'net_vega': round(analysis.net_vega, 4)
            },
            'probability': {
                'profit': round(analysis.probability_profit, 1)
            },
            'expiration': analysis.expiration,
            'days_to_expiration': analysis.days_to_expiration,
            'contracts': analysis.contracts
        }

        return MarketResponse(
            success=True,
            data=result,
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error analyzing bull call spread: {e}")
        return MarketResponse(
            success=False,
            error=str(e),
            timestamp=datetime.now().isoformat()
        )


@app.post("/api/options/strategy/bear-put-spread", response_model=MarketResponse)
async def analyze_bear_put_spread_strategy(request: SpreadRequest):
    """Analyze a bear put spread strategy"""
    try:
        from ..api.yahoo_client import YahooFinanceClient
        from ..analysis.strategy_builder import StrategyBuilder

        client = YahooFinanceClient(settings)
        builder = StrategyBuilder(client)

        analysis = builder.analyze_bear_put_spread(
            symbol=request.symbol.upper(),
            long_strike=request.long_strike,
            short_strike=request.short_strike,
            expiration=request.expiration,
            contracts=request.contracts
        )

        if not analysis:
            return MarketResponse(
                success=False,
                error="Could not analyze bear put spread",
                timestamp=datetime.now().isoformat()
            )

        result = {
            'symbol': analysis.symbol,
            'strategy_type': 'bear_put_spread',
            'legs': {
                'long_put': {
                    'strike': analysis.long_strike,
                    'premium': round(analysis.long_premium, 2)
                },
                'short_put': {
                    'strike': analysis.short_strike,
                    'premium': round(analysis.short_premium, 2)
                }
            },
            'pricing': {
                'net_debit': round(analysis.net_debit, 2),
                'total_cost': round(analysis.total_cost, 2),
                'spread_width': analysis.spread_width
            },
            'risk_metrics': {
                'max_profit': round(analysis.max_profit, 2),
                'max_loss': round(analysis.max_loss, 2),
                'breakeven': round(analysis.breakeven, 2),
                'risk_reward_ratio': round(analysis.risk_reward_ratio, 2),
                'max_return_pct': round(analysis.max_return_pct, 1)
            },
            'greeks': {
                'net_delta': round(analysis.net_delta, 4),
                'net_theta': round(analysis.net_theta, 4),
                'net_vega': round(analysis.net_vega, 4)
            },
            'probability': {
                'profit': round(analysis.probability_profit, 1)
            },
            'expiration': analysis.expiration,
            'days_to_expiration': analysis.days_to_expiration,
            'contracts': analysis.contracts
        }

        return MarketResponse(
            success=True,
            data=result,
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error analyzing bear put spread: {e}")
        return MarketResponse(
            success=False,
            error=str(e),
            timestamp=datetime.now().isoformat()
        )


@app.get("/api/options/macro-context", response_model=MarketResponse)
async def get_macro_context():
    """Get comprehensive macro context for options trading"""
    try:
        from ..api.yahoo_client import YahooFinanceClient
        from ..analysis.macro_context import MacroRegime

        client = YahooFinanceClient(settings)
        macro = MacroRegime(client)

        context = macro.get_comprehensive_context()

        return MarketResponse(
            success=True,
            data=context,
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error getting macro context: {e}")
        return MarketResponse(
            success=False,
            error=str(e),
            timestamp=datetime.now().isoformat()
        )


# ==================== ICT & ORDER FLOW ENDPOINTS ====================
# Include ICT router
try:
    from .ict_endpoints import ict_router
    app.include_router(ict_router)
    logger.info("ICT endpoints loaded successfully")
except Exception as e:
    logger.warning(f"Could not load ICT endpoints: {e}")


# ==================== RISK MANAGEMENT & JOURNAL ENDPOINTS ====================
# Include risk management, journaling, and alert routers
try:
    from .risk_endpoints import risk_router, journal_router, alerts_router
    app.include_router(risk_router)
    app.include_router(journal_router)
    app.include_router(alerts_router)
    logger.info("Risk management, journal, and alert endpoints loaded successfully")
except Exception as e:
    logger.warning(f"Could not load risk/journal/alert endpoints: {e}")


# ==================== VISUALIZATION ENDPOINTS ====================
# Include visualization router
try:
    from .visualization_endpoints import viz_router
    app.include_router(viz_router)
    logger.info("Visualization endpoints loaded successfully")
except Exception as e:
    logger.warning(f"Could not load visualization endpoints: {e}")


# ==================== DIVERGENCE DETECTION ENDPOINTS ====================
# Include divergence detection router
try:
    from .divergence_endpoints import divergence_router
    app.include_router(divergence_router)
    logger.info("Divergence detection endpoints loaded successfully")
except Exception as e:
    logger.warning(f"Could not load divergence endpoints: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)