#!/usr/bin/env python3
"""
MarketPulse FastAPI Application
Real-time market internals analysis API
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from src.api.routers import llm, market, test, websocket, screeners, symbols, data_quality
from src.api.routers.deps import (
    MarketPulseCollector,
    OHLCAnalyzer,
)
from src.scheduler.scheduler import MarketScheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    logger.info("Starting MarketPulse API...")
    global collector, ohlc_analyzer

    logger.info("Initializing global components...")

    if MarketPulseCollector:
        from src.api.routers import deps

        deps.collector = MarketPulseCollector()
        logger.info(f"Created collector: {type(deps.collector)}")
        try:
            await deps.collector.initialize()
            logger.success("MarketPulse collector initialized successfully")
        except Exception as e:
            logger.warning(f"Collector initialization failed: {e}")
    else:
        logger.warning("MarketPulseCollector not available - running in limited mode")

    if OHLCAnalyzer:
        from src.api.routers import deps

        deps.ohlc_analyzer = OHLCAnalyzer()
        logger.success("OHLC Analyzer initialized")
    else:
        logger.warning("OHLCAnalyzer not available - OHLC features disabled")

    scheduler = MarketScheduler()
    try:
        await scheduler.start()
    except Exception as e:
        logger.warning(f"Scheduler initialization failed: {e}")

    yield

    await scheduler.stop()
    logger.info("Shutting down MarketPulse API...")


app = FastAPI(
    title="MarketPulse API", description="Real-time market internals analysis API", version="0.1.0", lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000", "http://127.0.0.1:3001"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(market.router)
app.include_router(llm.router)
app.include_router(test.router)
app.include_router(websocket.router)
app.include_router(screeners.router)
app.include_router(symbols.router)
app.include_router(data_quality.router)


@app.get("/")
async def root():
    """API health check"""
    return {"message": "MarketPulse API is running", "version": "0.1.0", "timestamp": datetime.now().isoformat()}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
