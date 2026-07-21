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

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional, List
from datetime import datetime
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

class MarketResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: str


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


# ==================== PHASE A1: MOUNT ROUTERS ====================
# These routers used to live as inline handlers in this file. Mount them
# here so /api/llm/*, /api/market/*, /api/test/*, /ws/*, etc. are served
# from src/api/routers/. Inline duplicates were deleted alongside this block.
try:
    from src.api.routers import data_quality as data_quality_router_module
    from src.api.routers import llm as llm_router_module
    from src.api.routers import market as market_router_module
    from src.api.routers import screeners as screeners_router_module
    from src.api.routers import symbols as symbols_router_module
    from src.api.routers import test as test_router_module
    from src.api.routers import websocket as websocket_router_module

    app.include_router(llm_router_module.router)
    app.include_router(market_router_module.router)
    app.include_router(symbols_router_module.router)
    app.include_router(screeners_router_module.router)
    app.include_router(websocket_router_module.router)
    app.include_router(data_quality_router_module.router)
    app.include_router(test_router_module.router)
    logger.info("Phase A1 routers mounted (llm/market/symbols/screeners/websocket/data_quality/test)")
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
