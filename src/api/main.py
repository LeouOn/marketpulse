#!/usr/bin/env python3
"""
MarketPulse FastAPI Application
Real-time market internals analysis API
"""

import sys
from pathlib import Path

# Add the project root to Python path for absolute imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

# Module-scope (not lazy in lifespan) so circular imports surface at import time.
from src.api.routers import deps as router_deps

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
    from src.analysis.ohlc_analyzer import OHLCAnalyzer
except Exception as e:
    logger.warning(f"Could not import OHLCAnalyzer: {e}")
    OHLCAnalyzer = None

# Global variables (populated by lifespan; published to routers via deps.init_state)
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
    router_deps.init_state(collector=collector, ohlc_analyzer=ohlc_analyzer, db_manager=db_manager)
    logger.info("Router deps state published")
    yield

    # Shutdown
    logger.info("Shutting down MarketPulse API...")

app = FastAPI(
    title="MarketPulse API",
    description="Real-time market internals analysis API",
    version="0.1.0",
    lifespan=lifespan
)

# Global exception handler to ensure JSON responses
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception handler caught: {exc}")
    logger.error(f"Request: {request.method} {request.url}")
    import traceback
    logger.error(f"Traceback: {traceback.format_exc()}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": str(exc),
            "detail": "Internal server error",
            "timestamp": datetime.now().isoformat()
        }
    )

# CORS middleware - more permissive for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

db_manager = DatabaseManager(settings.database_url) if settings and DatabaseManager else None


@app.get("/")
async def root():
    """API health check"""
    return {
        "message": "MarketPulse API is running",
        "version": "0.1.0",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/debug/routes")
async def debug_routes():
    """Debug endpoint to list all registered routes"""
    routes = []
    for route in app.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            routes.append({
                "path": route.path,
                "methods": list(route.methods) if route.methods else []
            })
        elif hasattr(route, 'path'):
            routes.append({
                "path": route.path,
                "methods": ["WebSocket" if "ws" in route.path else "Unknown"]
            })
    return {
        "total_routes": len(routes),
        "routes": sorted(routes, key=lambda x: x["path"]),
        "market_routes": [r for r in routes if "/api/market" in r["path"]],
        "llm_routes": [r for r in routes if "/api/llm" in r["path"]]
    }


# ==================== PHASE A1: MOUNT ROUTERS ====================
# These routers used to live as inline handlers in this file. Mount them
# here so /api/llm/*, /api/market/*, /api/test/*, /ws/*, etc. are served
# from src/api/routers/. Inline duplicates were deleted alongside this block.
try:
    from src.api.routers import data_quality as data_quality_router_module
    from src.api.routers import llm as llm_router_module
    from src.api.routers import market as market_router_module
    from src.api.routers import options as options_router_module
    from src.api.routers import screeners as screeners_router_module
    from src.api.routers import symbols as symbols_router_module
    from src.api.routers import test as test_router_module
    from src.api.routers import websocket as websocket_router_module

    app.include_router(llm_router_module.router)
    app.include_router(market_router_module.router)
    app.include_router(options_router_module.router)
    app.include_router(symbols_router_module.router)
    app.include_router(screeners_router_module.router)
    app.include_router(websocket_router_module.router)
    app.include_router(data_quality_router_module.router)
    app.include_router(test_router_module.router)
    logger.info("Phase A1 routers mounted (llm/market/options/symbols/screeners/websocket/data_quality/test)")
except Exception as e:
    logger.warning(f"Could not load Phase A1 routers: {e}")


# ==================== ICT & ORDER FLOW ENDPOINTS ====================
# Include ICT router
try:
    from .ict_endpoints import ict_router
    app.include_router(ict_router)
    logger.info("ICT endpoints loaded successfully")
except Exception as e:
    logger.warning(f"Could not load ICT endpoints: {e}")


# ==================== BTC RESEARCH LAB (B7) ====================
# Exposes the Bitcoin long-term research tools (backtest, monte carlo,
# strategy/scaling registries, agentic chat) at /api/research/*.
try:
    from .research_router import router as research_router
    app.include_router(research_router)
    logger.info("Research lab endpoints loaded successfully")
except Exception as e:
    logger.warning(f"Could not load research endpoints: {e}")


# ==================== RISK MANAGEMENT & JOURNAL ENDPOINTS ====================
# Include risk management, journaling, and alert routers
try:
    from .risk_endpoints import alerts_router, journal_router, risk_router
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


# ==================== AI TRADING ANALYST ENDPOINTS ====================
# Include AI trading analyst router
try:
    from .ai_endpoints import ai_router
    app.include_router(ai_router)
    logger.info("AI Trading Analyst endpoints loaded successfully")
except Exception as e:
    logger.warning(f"Could not load AI endpoints: {e}")


# ==================== BACKTESTING & OPTIMIZATION ENDPOINTS ====================
# Include backtesting & optimization router
try:
    from .backtest_endpoints import backtest_router
    app.include_router(backtest_router)
    logger.info("Backtesting & optimization endpoints loaded successfully")
except Exception as e:
    logger.warning(f"Could not load backtest endpoints: {e}")


# ==================== YIELD CURVE MONITOR ====================
# REST endpoints at /api/yield-curve/* for the daily Treasury pipeline.
try:
    from .routers.yield_curve import router as yield_curve_router
    app.include_router(yield_curve_router)
    logger.info("Yield curve endpoints loaded successfully")
except Exception as e:
    logger.warning(f"Could not load yield curve endpoints: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
