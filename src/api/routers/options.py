"""Options analysis endpoints (extracted from main.py during Phase A1)."""

from datetime import datetime

from fastapi import APIRouter
from loguru import logger
from pydantic import BaseModel

from .deps import MarketResponse, settings

router = APIRouter(prefix="/api/options", tags=["options"])


class SingleLegRequest(BaseModel):
    """Request model for single leg analysis"""

    symbol: str
    strike: float
    expiration: str
    option_type: str  # 'call' or 'put'
    position_type: str = "long"  # 'long' or 'short'
    contracts: int = 1


class ScreenOptionsRequest(BaseModel):
    """Request model for options screening"""

    screen_type: str = "otm_calls"  # 'otm_calls', 'otm_puts', 'high_iv', etc.
    symbols: list[str] | None = None  # If None, uses default watchlist
    min_delta: float = 0.20
    max_delta: float = 0.45
    min_days_to_expiry: int = 14
    max_days_to_expiry: int = 60
    min_volume: int = 100
    min_open_interest: int = 100


class CoveredCallRequest(BaseModel):
    """Request model for covered call analysis"""

    symbol: str
    shares_owned: int
    strike: float
    expiration: str
    contracts: int | None = None


class SpreadRequest(BaseModel):
    """Request model for spread analysis"""

    symbol: str
    long_strike: float
    short_strike: float
    expiration: str
    contracts: int = 1


@router.get("/expirations/{symbol}", response_model=MarketResponse)
async def get_options_expirations(symbol: str):
    """Get available options expiration dates for a symbol"""
    try:
        from src.api.yahoo_client import YahooFinanceClient

        client = YahooFinanceClient(settings)
        expirations = client.get_options_expirations(symbol.upper())

        return MarketResponse(
            success=True,
            data={"symbol": symbol.upper(), "expirations": expirations, "count": len(expirations)},
            timestamp=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"Error fetching options expirations for {symbol}: {e}")
        return MarketResponse(success=False, error=str(e), timestamp=datetime.now().isoformat())


@router.get("/chain/{symbol}/{expiration}", response_model=MarketResponse)
async def get_options_chain(symbol: str, expiration: str, include_greeks: bool = True):
    """Get options chain with calculated Greeks for specific expiration"""
    try:
        from src.analysis.options_pricing import BlackScholesCalculator
        from src.api.yahoo_client import YahooFinanceClient

        client = YahooFinanceClient(settings)

        # Get options chain
        chain_data = client.get_options_chain(symbol.upper(), expiration)

        if "error" in chain_data:
            return MarketResponse(success=False, error=chain_data["error"], timestamp=datetime.now().isoformat())

        # Calculate Greeks if requested
        if include_greeks and chain_data["underlying_price"]:
            risk_free_rate = client.get_risk_free_rate()
            dividend_yield = client.get_dividend_yield(symbol.upper())
            T = BlackScholesCalculator.days_to_expiration(expiration)
            S = chain_data["underlying_price"]

            # Enhance calls with Greeks
            for call in chain_data["calls"]:
                if call.get("impliedVolatility", 0) > 0:
                    result = BlackScholesCalculator.calculate_option_with_greeks(
                        S=S,
                        K=call["strike"],
                        T=T,
                        r=risk_free_rate,
                        sigma=call["impliedVolatility"],
                        q=dividend_yield,
                        option_type="call",
                    )
                    call["theoretical_price"] = round(result.price, 4)
                    call["greeks"] = {
                        "delta": round(result.greeks.delta, 4),
                        "gamma": round(result.greeks.gamma, 6),
                        "theta": round(result.greeks.theta, 4),
                        "vega": round(result.greeks.vega, 4),
                        "rho": round(result.greeks.rho, 4),
                    }

            # Enhance puts with Greeks
            for put in chain_data["puts"]:
                if put.get("impliedVolatility", 0) > 0:
                    result = BlackScholesCalculator.calculate_option_with_greeks(
                        S=S,
                        K=put["strike"],
                        T=T,
                        r=risk_free_rate,
                        sigma=put["impliedVolatility"],
                        q=dividend_yield,
                        option_type="put",
                    )
                    put["theoretical_price"] = round(result.price, 4)
                    put["greeks"] = {
                        "delta": round(result.greeks.delta, 4),
                        "gamma": round(result.greeks.gamma, 6),
                        "theta": round(result.greeks.theta, 4),
                        "vega": round(result.greeks.vega, 4),
                        "rho": round(result.greeks.rho, 4),
                    }

        return MarketResponse(success=True, data=chain_data, timestamp=datetime.now().isoformat())

    except Exception as e:
        logger.error(f"Error fetching options chain for {symbol} {expiration}: {e}")
        return MarketResponse(success=False, error=str(e), timestamp=datetime.now().isoformat())


@router.post("/analyze/single-leg", response_model=MarketResponse)
async def analyze_single_leg(request: SingleLegRequest):
    """Analyze a single options leg with full risk metrics"""
    try:
        from src.analysis.options_analyzer import OptionsAnalyzer
        from src.api.yahoo_client import YahooFinanceClient

        client = YahooFinanceClient(settings)
        analyzer = OptionsAnalyzer(client)

        # Perform analysis
        analysis = analyzer.analyze_single_leg(
            symbol=request.symbol.upper(),
            strike=request.strike,
            expiration=request.expiration,
            option_type=request.option_type.lower(),
            position_type=request.position_type.lower(),
            contracts=request.contracts,
        )

        if not analysis:
            return MarketResponse(
                success=False,
                error="Could not analyze option - check symbol, strike, and expiration",
                timestamp=datetime.now().isoformat(),
            )

        # Generate P&L chart data
        pnl_chart = analyzer.generate_pnl_chart_data(analysis)

        # Convert to dictionary
        result = {
            "symbol": analysis.symbol,
            "option_type": analysis.option_type,
            "strike": analysis.strike,
            "expiration": analysis.expiration,
            "underlying_price": analysis.underlying_price,
            "pricing": {
                "theoretical_price": round(analysis.theoretical_price, 4),
                "market_price": round(analysis.market_price, 4),
                "bid": round(analysis.bid, 4),
                "ask": round(analysis.ask, 4),
                "mid_price": round(analysis.mid_price, 4),
                "implied_volatility": round(analysis.implied_volatility, 4),
            },
            "greeks": {
                "delta": round(analysis.greeks.delta, 4),
                "gamma": round(analysis.greeks.gamma, 6),
                "theta": round(analysis.greeks.theta, 4),
                "vega": round(analysis.greeks.vega, 4),
                "rho": round(analysis.greeks.rho, 4),
            },
            "position": {
                "type": analysis.position_type,
                "contracts": analysis.contracts,
                "cost_basis": round(analysis.cost_basis, 2),
                "theta_decay_per_day": round(analysis.theta_decay_per_day, 2),
            },
            "risk_metrics": {
                "breakeven": round(analysis.breakeven, 2),
                "max_profit": round(analysis.max_profit, 2) if analysis.max_profit else None,
                "max_loss": round(analysis.max_loss, 2) if analysis.max_loss else None,
                "risk_reward_ratio": round(analysis.risk_reward_ratio, 2) if analysis.risk_reward_ratio else None,
                "probability_profit": round(analysis.probability_profit, 2),
            },
            "time_metrics": {"days_to_expiration": analysis.days_to_expiration, "expiration_date": analysis.expiration},
            "pnl_chart": pnl_chart,
        }

        return MarketResponse(success=True, data=result, timestamp=datetime.now().isoformat())

    except Exception as e:
        logger.error(f"Error analyzing single leg: {e}")
        return MarketResponse(success=False, error=str(e), timestamp=datetime.now().isoformat())


@router.post("/screen", response_model=MarketResponse)
async def screen_options(request: ScreenOptionsRequest):
    """Screen for options opportunities based on criteria"""
    try:
        from src.analysis.options_analyzer import OptionsAnalyzer
        from src.api.yahoo_client import YahooFinanceClient

        client = YahooFinanceClient(settings)
        analyzer = OptionsAnalyzer(client)

        # Use default symbols if none provided
        symbols = request.symbols or ["SPY", "QQQ", "AAPL", "TSLA", "NVDA", "MSFT"]

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
                    exp for exp in expirations if min_date <= datetime.strptime(exp, "%Y-%m-%d").date() <= max_date
                ]

                # Screen each expiration
                for expiration in valid_expirations[:3]:  # Limit to first 3 expirations
                    chain_data = client.get_options_chain(symbol, expiration)

                    if "error" in chain_data or not chain_data["underlying_price"]:
                        continue

                    # Filter options based on criteria
                    options_to_check = chain_data["calls"] if request.screen_type == "otm_calls" else chain_data["puts"]

                    for opt in options_to_check:
                        # Check volume and OI filters
                        if opt.get("volume", 0) < request.min_volume:
                            continue
                        if opt.get("openInterest", 0) < request.min_open_interest:
                            continue

                        # Analyze this option
                        analysis = analyzer.analyze_single_leg(
                            symbol=symbol,
                            strike=opt["strike"],
                            expiration=expiration,
                            option_type="call" if request.screen_type == "otm_calls" else "put",
                            position_type="long",
                            contracts=1,
                        )

                        if analysis:
                            # Check delta filter
                            delta_abs = abs(analysis.greeks.delta)
                            if request.min_delta <= delta_abs <= request.max_delta:
                                opportunities.append(
                                    {
                                        "symbol": symbol,
                                        "strike": analysis.strike,
                                        "expiration": expiration,
                                        "option_type": analysis.option_type,
                                        "underlying_price": analysis.underlying_price,
                                        "market_price": round(analysis.market_price, 2),
                                        "delta": round(analysis.greeks.delta, 3),
                                        "gamma": round(analysis.greeks.gamma, 4),
                                        "theta": round(analysis.greeks.theta, 2),
                                        "implied_volatility": round(analysis.implied_volatility, 3),
                                        "volume": opt.get("volume", 0),
                                        "open_interest": opt.get("openInterest", 0),
                                        "days_to_expiration": analysis.days_to_expiration,
                                        "breakeven": round(analysis.breakeven, 2),
                                        "probability_profit": round(analysis.probability_profit, 1),
                                    }
                                )

            except Exception as e:
                logger.warning(f"Error screening {symbol}: {e}")
                continue

        # Sort by probability of profit (or other criteria)
        opportunities.sort(key=lambda x: x["probability_profit"], reverse=True)

        return MarketResponse(
            success=True,
            data={
                "screen_type": request.screen_type,
                "criteria": request.dict(),
                "opportunities": opportunities[:20],  # Return top 20
                "total_found": len(opportunities),
            },
            timestamp=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"Error screening options: {e}")
        return MarketResponse(success=False, error=str(e), timestamp=datetime.now().isoformat())


@router.post("/strategy/covered-call", response_model=MarketResponse)
async def analyze_covered_call_strategy(request: CoveredCallRequest):
    """Analyze a covered call strategy"""
    try:
        from src.analysis.strategy_builder import StrategyBuilder
        from src.api.yahoo_client import YahooFinanceClient

        client = YahooFinanceClient(settings)
        builder = StrategyBuilder(client)

        analysis = builder.analyze_covered_call(
            symbol=request.symbol.upper(),
            shares_owned=request.shares_owned,
            strike=request.strike,
            expiration=request.expiration,
            contracts=request.contracts,
        )

        if not analysis:
            return MarketResponse(
                success=False, error="Could not analyze covered call strategy", timestamp=datetime.now().isoformat()
            )

        result = {
            "symbol": analysis.symbol,
            "strategy_type": "covered_call",
            "position": {
                "shares_owned": analysis.shares_owned,
                "contracts": analysis.contracts,
                "stock_price": round(analysis.stock_price, 2),
            },
            "short_call": {
                "strike": analysis.strike,
                "expiration": analysis.expiration,
                "premium_received": round(analysis.premium_received, 2),
                "total_premium": round(analysis.total_premium, 2),
            },
            "metrics": {
                "cost_basis_reduction": round(analysis.cost_basis_reduction, 2),
                "downside_protection_pct": round(analysis.downside_protection, 2),
                "upside_cap": round(analysis.upside_cap, 2),
                "breakeven": round(analysis.breakeven, 2),
            },
            "returns": {
                "max_profit": round(analysis.max_profit, 2),
                "max_loss": round(analysis.max_loss, 2),
                "return_if_called_pct": round(analysis.return_if_called, 2),
                "annualized_return_pct": round(analysis.annualized_return, 2),
            },
            "greeks": {"delta": round(analysis.delta, 4), "theta": round(analysis.theta, 4)},
            "probability": {"max_profit": round(analysis.probability_max_profit, 1)},
            "days_to_expiration": analysis.days_to_expiration,
        }

        return MarketResponse(success=True, data=result, timestamp=datetime.now().isoformat())

    except Exception as e:
        logger.error(f"Error analyzing covered call: {e}")
        return MarketResponse(success=False, error=str(e), timestamp=datetime.now().isoformat())


@router.post("/strategy/bull-call-spread", response_model=MarketResponse)
async def analyze_bull_call_spread_strategy(request: SpreadRequest):
    """Analyze a bull call spread strategy"""
    try:
        from src.analysis.strategy_builder import StrategyBuilder
        from src.api.yahoo_client import YahooFinanceClient

        client = YahooFinanceClient(settings)
        builder = StrategyBuilder(client)

        analysis = builder.analyze_bull_call_spread(
            symbol=request.symbol.upper(),
            long_strike=request.long_strike,
            short_strike=request.short_strike,
            expiration=request.expiration,
            contracts=request.contracts,
        )

        if not analysis:
            return MarketResponse(
                success=False, error="Could not analyze bull call spread", timestamp=datetime.now().isoformat()
            )

        result = {
            "symbol": analysis.symbol,
            "strategy_type": "bull_call_spread",
            "legs": {
                "long_call": {"strike": analysis.long_strike, "premium": round(analysis.long_premium, 2)},
                "short_call": {"strike": analysis.short_strike, "premium": round(analysis.short_premium, 2)},
            },
            "pricing": {
                "net_debit": round(analysis.net_debit, 2),
                "total_cost": round(analysis.total_cost, 2),
                "spread_width": analysis.spread_width,
            },
            "risk_metrics": {
                "max_profit": round(analysis.max_profit, 2),
                "max_loss": round(analysis.max_loss, 2),
                "breakeven": round(analysis.breakeven, 2),
                "risk_reward_ratio": round(analysis.risk_reward_ratio, 2),
                "max_return_pct": round(analysis.max_return_pct, 1),
            },
            "greeks": {
                "net_delta": round(analysis.net_delta, 4),
                "net_theta": round(analysis.net_theta, 4),
                "net_vega": round(analysis.net_vega, 4),
            },
            "probability": {"profit": round(analysis.probability_profit, 1)},
            "expiration": analysis.expiration,
            "days_to_expiration": analysis.days_to_expiration,
            "contracts": analysis.contracts,
        }

        return MarketResponse(success=True, data=result, timestamp=datetime.now().isoformat())

    except Exception as e:
        logger.error(f"Error analyzing bull call spread: {e}")
        return MarketResponse(success=False, error=str(e), timestamp=datetime.now().isoformat())


@router.post("/strategy/bear-put-spread", response_model=MarketResponse)
async def analyze_bear_put_spread_strategy(request: SpreadRequest):
    """Analyze a bear put spread strategy"""
    try:
        from src.analysis.strategy_builder import StrategyBuilder
        from src.api.yahoo_client import YahooFinanceClient

        client = YahooFinanceClient(settings)
        builder = StrategyBuilder(client)

        analysis = builder.analyze_bear_put_spread(
            symbol=request.symbol.upper(),
            long_strike=request.long_strike,
            short_strike=request.short_strike,
            expiration=request.expiration,
            contracts=request.contracts,
        )

        if not analysis:
            return MarketResponse(
                success=False, error="Could not analyze bear put spread", timestamp=datetime.now().isoformat()
            )

        result = {
            "symbol": analysis.symbol,
            "strategy_type": "bear_put_spread",
            "legs": {
                "long_put": {"strike": analysis.long_strike, "premium": round(analysis.long_premium, 2)},
                "short_put": {"strike": analysis.short_strike, "premium": round(analysis.short_premium, 2)},
            },
            "pricing": {
                "net_debit": round(analysis.net_debit, 2),
                "total_cost": round(analysis.total_cost, 2),
                "spread_width": analysis.spread_width,
            },
            "risk_metrics": {
                "max_profit": round(analysis.max_profit, 2),
                "max_loss": round(analysis.max_loss, 2),
                "breakeven": round(analysis.breakeven, 2),
                "risk_reward_ratio": round(analysis.risk_reward_ratio, 2),
                "max_return_pct": round(analysis.max_return_pct, 1),
            },
            "greeks": {
                "net_delta": round(analysis.net_delta, 4),
                "net_theta": round(analysis.net_theta, 4),
                "net_vega": round(analysis.net_vega, 4),
            },
            "probability": {"profit": round(analysis.probability_profit, 1)},
            "expiration": analysis.expiration,
            "days_to_expiration": analysis.days_to_expiration,
            "contracts": analysis.contracts,
        }

        return MarketResponse(success=True, data=result, timestamp=datetime.now().isoformat())

    except Exception as e:
        logger.error(f"Error analyzing bear put spread: {e}")
        return MarketResponse(success=False, error=str(e), timestamp=datetime.now().isoformat())


@router.get("/macro-context", response_model=MarketResponse)
async def get_macro_context():
    """Get comprehensive macro context for options trading"""
    try:
        from src.analysis.macro_context import MacroRegime
        from src.api.yahoo_client import YahooFinanceClient

        client = YahooFinanceClient(settings)
        macro = MacroRegime(client)

        context = macro.get_comprehensive_context()

        return MarketResponse(success=True, data=context, timestamp=datetime.now().isoformat())

    except Exception as e:
        logger.error(f"Error getting macro context: {e}")
        return MarketResponse(success=False, error=str(e), timestamp=datetime.now().isoformat())
