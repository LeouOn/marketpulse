"""Market data endpoints"""

import asyncio
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks
from loguru import logger

from .deps import (
    MarketResponse,
    collector,
    settings,
)

router = APIRouter(prefix="/api/market", tags=["market"])

# Cache for AI analysis so dashboard returns immediately
_cached_ai_analysis: str | None = None
_ai_analysis_lock = asyncio.Lock()


async def _refresh_ai_analysis(internals: dict):
    """Background task to refresh AI analysis cache"""
    global _cached_ai_analysis
    try:
        analysis = await asyncio.wait_for(collector.analyze_with_ai(internals, "quick"), timeout=90.0)
        if analysis:
            _cached_ai_analysis = analysis
            logger.success("AI analysis cache refreshed")
    except TimeoutError:
        logger.warning("Background AI analysis timed out (90s)")
    except Exception as e:
        logger.warning(f"Background AI analysis failed: {e}")


@router.get("/internals", response_model=MarketResponse)
async def get_market_internals():
    """Get current market internals"""
    try:
        from .deps import MarketPulseCollector

        current_collector = MarketPulseCollector()
        init_result = await current_collector.initialize()
        logger.info(f"Collector initialization result: {init_result}")

        internals = await current_collector.collect_market_internals()

        if internals:
            logger.info(f"Successfully collected {len(internals)} data items")
            return MarketResponse(success=True, data=internals, timestamp=datetime.now().isoformat())
        else:
            return MarketResponse(
                success=False,
                error="No market data available - check data source connectivity",
                timestamp=datetime.now().isoformat(),
            )
    except Exception as e:
        logger.error(f"Error fetching market internals: {e}")
        return MarketResponse(success=False, error=str(e), timestamp=datetime.now().isoformat())


@router.get("/dashboard", response_model=MarketResponse)
async def get_dashboard_data(background_tasks: BackgroundTasks):
    """Get dashboard data — returns immediately with cached AI analysis,
    refreshes analysis in the background."""
    try:
        from .deps import collector

        internals = await collector.collect_market_internals()

        market_bias = "NEUTRAL"
        if "spy" in internals and "qqq" in internals:
            spy_trend = internals["spy"]["change"]
            qqq_trend = internals["qqq"]["change"]

            if spy_trend > 0 and qqq_trend > 0:
                market_bias = "BULLISH"
            elif spy_trend < 0 and qqq_trend < 0:
                market_bias = "BEARISH"
            else:
                market_bias = "MIXED"

        # Kick off background AI analysis refresh (non-blocking)
        background_tasks.add_task(_refresh_ai_analysis, internals)

        dashboard_data = {
            "timestamp": datetime.now().isoformat(),
            "marketBias": market_bias,
            "volatilityRegime": collector._classify_volatility(internals),
            "symbols": {"spy": internals.get("spy"), "qqq": internals.get("qqq"), "vix": internals.get("vix")},
            "volumeFlow": internals.get("volume_flow", {}),
            "aiAnalysis": _cached_ai_analysis,
            "dataSource": internals.get("data_source", "unknown"),
            "dataQuality": internals.get("data_quality", "unknown"),
            "qualityIssues": internals.get("quality_issues", []),
            "synthetic": internals.get("synthetic", False),
            "freshnessStatus": internals.get("freshness_status", "unknown"),
            "dataAgeSeconds": internals.get("spy", {}).get("data_age_seconds") if "spy" in internals else None,
        }

        try:
            from src.data.market_breadth import MarketBreadthCollector
            breadth_collector = MarketBreadthCollector()
            breadth = breadth_collector.get_market_internals()
            if breadth:
                dashboard_data["breadth"] = breadth
        except Exception:
            pass

        try:
            from src.core.cache import get_cache

            cache = await get_cache()
            if cache:
                gainers = await cache.get("screener:gainers")
                losers = await cache.get("screener:losers")
                dashboard_data["screener_summary"] = {
                    "top_gainers": (gainers or [])[:3],
                    "top_losers": (losers or [])[:3],
                }
        except Exception:
            dashboard_data["screener_summary"] = {"top_gainers": [], "top_losers": []}

        return MarketResponse(success=True, data=dashboard_data, timestamp=datetime.now().isoformat())
    except Exception as e:
        logger.error(f"Error fetching dashboard data: {e}")
        return MarketResponse(success=False, error=str(e), timestamp=datetime.now().isoformat())


@router.get("/historical", response_model=MarketResponse)
async def get_historical_data(symbol: str, timeframe: str = "1Min", limit: int = 100):
    """Get historical price data for a symbol"""
    try:
        from src.api.yahoo_client import YahooFinanceClient

        client = YahooFinanceClient(settings)
        data = client.get_bars(symbol, timeframe, limit)

        if data is not None:
            historical_data = []
            for _, row in data.iterrows():
                historical_data.append(
                    {
                        "timestamp": row.name.isoformat(),
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                        "volume": int(row["volume"]),
                    }
                )

            return MarketResponse(
                success=True, data={"symbol": symbol, "data": historical_data}, timestamp=datetime.now().isoformat()
            )
        else:
            return MarketResponse(success=False, error="No data available", timestamp=datetime.now().isoformat())
    except Exception as e:
        logger.error(f"Error fetching historical data: {e}")
        return MarketResponse(success=False, error=str(e), timestamp=datetime.now().isoformat())


@router.get("/historical/{symbol}", response_model=MarketResponse)
async def get_historical_by_path(symbol: str, timeframe: str = "1d", period: str = "1mo"):
    """Get historical price data by symbol path"""
    try:
        from src.api.yahoo_client import YahooFinanceClient

        client = YahooFinanceClient(settings)
        data = client.get_bars(symbol, period, timeframe)

        if data is not None:
            historical_data = []
            for _, row in data.iterrows():
                historical_data.append(
                    {
                        "timestamp": row.name.isoformat(),
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                        "volume": int(row["volume"]),
                    }
                )
            return MarketResponse(success=True, data={"symbol": symbol, "data": historical_data}, timestamp=datetime.now().isoformat())
        return MarketResponse(success=False, error="No data available", timestamp=datetime.now().isoformat())
    except Exception as e:
        logger.error(f"Error fetching historical data for {symbol}: {e}")
        return MarketResponse(success=False, error=str(e), timestamp=datetime.now().isoformat())


@router.get("/ai-analysis", response_model=MarketResponse)
async def get_ai_analysis():
    """Get AI analysis of current market conditions"""
    try:
        from .deps import collector

        internals = await collector.collect_market_internals()
        analysis = await collector.analyze_with_ai(internals, "quick")

        return MarketResponse(success=True, data={"analysis": analysis}, timestamp=datetime.now().isoformat())
    except Exception as e:
        logger.error(f"Error getting AI analysis: {e}")
        return MarketResponse(success=False, error=str(e), timestamp=datetime.now().isoformat())


@router.get("/macro", response_model=MarketResponse)
async def get_macro_data():
    """Get important macro economic indicators"""
    try:
        from src.api.mock_market import mock_provider
        from src.api.yahoo_client import YahooFinanceClient

        client = YahooFinanceClient(settings)
        macro_data = client.get_macro_data()

        mock_data = await mock_provider.get_macro_data()
        macro_data["market_session"] = mock_data.get("market_session", "US Regular")
        macro_data["economic_sentiment"] = mock_data.get("economic_sentiment", "Neutral")
        macro_data["risk_appetite"] = mock_data.get("risk_appetite", "Balanced")
        macro_data["sector_performance"] = mock_data.get("sector_performance", {})

        try:
            client_52w = YahooFinanceClient(settings)
            for indicator in ["DXY", "TNX", "GC", "BTC"]:
                if indicator in macro_data and isinstance(macro_data[indicator], dict) and "price" in macro_data[indicator]:
                    yahoo_sym = client_52w.macro_symbols.get(indicator, indicator)
                    range_data = client_52w.get_52w_range(yahoo_sym)
                    if range_data:
                        macro_data[indicator]["high_52w"] = range_data.get("high_52w")
                        macro_data[indicator]["low_52w"] = range_data.get("low_52w")
                        macro_data[indicator]["pct_from_52w_high"] = range_data.get("pct_from_high")
        except Exception as e:
            logger.debug(f"Could not enrich macro data with 52W ranges: {e}")

        return MarketResponse(success=True, data=macro_data, timestamp=datetime.now().isoformat())

    except Exception as e:
        logger.error(f"Error getting macro data: {e}")
        try:
            from src.api.mock_market import mock_provider

            mock_data = await mock_provider.get_macro_data()
            return MarketResponse(success=True, data=mock_data, timestamp=datetime.now().isoformat())
        except Exception:
            return MarketResponse(success=False, error=str(e), timestamp=datetime.now().isoformat())


@router.get("/breadth", response_model=MarketResponse)
async def get_market_breadth():
    """Get market breadth indicators (A/D, TICK, VOLD, McClellan)"""
    try:
        from src.core.cache import get_cache

        cache = await get_cache()
        if cache:
            cached = await cache.get("market:breadth")
            if cached:
                return MarketResponse(success=True, data=cached, timestamp=datetime.now().isoformat())

        from src.data.market_breadth import MarketBreadthCollector

        breadth_collector = MarketBreadthCollector()
        breadth_data = breadth_collector.get_market_internals()

        if cache and breadth_data:
            await cache.set("market:breadth", breadth_data, 60)

        return MarketResponse(success=True, data=breadth_data, timestamp=datetime.now().isoformat())

    except Exception as e:
        logger.error(f"Error getting market breadth data: {e}")
        return MarketResponse(success=False, error=str(e), timestamp=datetime.now().isoformat())


@router.get("/ohlc-analysis/{symbol}", response_model=MarketResponse)
async def get_ohlc_analysis(symbol: str):
    """Get comprehensive OHLC analysis for a symbol"""
    try:
        from src.api.yahoo_client import YahooFinanceClient

        from .deps import ohlc_analyzer, settings

        historical_data = {}
        client = YahooFinanceClient(settings)

        for tf_name, tf_config in ohlc_analyzer.timeframes.items():
            try:
                data = client.get_bars(symbol, tf_config["period"], tf_config.get("interval", "1d"))

                if data is not None:
                    historical_data[tf_name] = {"symbol": symbol, "data": []}

                    for _, row in data.iterrows():
                        historical_data[tf_name]["data"].append(
                            {
                                "timestamp": row.name.isoformat(),
                                "open": float(row["open"]),
                                "high": float(row["high"]),
                                "low": float(row["low"]),
                                "close": float(row["close"]),
                                "volume": int(row["volume"]),
                            }
                        )
                else:
                    logger.warning(f"No data returned for {symbol} {tf_name}")
            except Exception as e:
                logger.warning(f"Could not fetch {tf_name} data for {symbol}: {e}")

        analysis = ohlc_analyzer.analyze_symbol({"historical_data": historical_data}, symbol)

        return MarketResponse(success=True, data=analysis, timestamp=datetime.now().isoformat())

    except Exception as e:
        logger.error(f"Error getting OHLC analysis for {symbol}: {e}")
        return MarketResponse(success=False, error=str(e), timestamp=datetime.now().isoformat())


@router.get("/ohlc-dashboard", response_model=MarketResponse)
async def get_ohlc_dashboard():
    """Get OHLC analysis for major market symbols"""
    try:
        from src.api.yahoo_client import YahooFinanceClient

        from .deps import ohlc_analyzer, settings

        symbols = ["SPY", "QQQ", "BTC", "ETH", "VIX"]
        dashboard_data = {
            "timestamp": datetime.now().isoformat(),
            "symbols": {},
            "market_summary": {"overall_trend": "NEUTRAL", "trending_symbols": [], "key_levels": {}, "patterns": []},
        }

        all_analyses = []
        client = YahooFinanceClient(settings)

        for symbol in symbols:
            try:
                historical_data = {}

                for tf_name, tf_config in ohlc_analyzer.timeframes.items():
                    try:
                        data = client.get_bars(symbol, tf_config["period"], tf_config.get("interval", "1d"))

                        if data is not None:
                            historical_data[tf_name] = {"symbol": symbol, "data": []}

                            for _, row in data.iterrows():
                                historical_data[tf_name]["data"].append(
                                    {
                                        "timestamp": row.name.isoformat(),
                                        "open": float(row["open"]),
                                        "high": float(row["high"]),
                                        "low": float(row["low"]),
                                        "close": float(row["close"]),
                                        "volume": int(row["volume"]),
                                    }
                                )
                    except Exception as e:
                        logger.warning(f"Could not fetch {tf_name} data for {symbol}: {e}")

                analysis = ohlc_analyzer.analyze_symbol({"historical_data": historical_data}, symbol)

                dashboard_data["symbols"][symbol] = analysis
                all_analyses.append(analysis)

            except Exception as e:
                logger.warning(f"Could not analyze {symbol}: {e}")
                dashboard_data["symbols"][symbol] = {"error": str(e)}

        if all_analyses:
            bullish_count = sum(1 for a in all_analyses if a.get("overall_trend") in ["BULLISH", "STRONGLY_BULLISH"])
            bearish_count = sum(1 for a in all_analyses if a.get("overall_trend") in ["BEARISH", "STRONGLY_BEARISH"])

            if bullish_count > bearish_count * 1.5:
                dashboard_data["market_summary"]["overall_trend"] = "STRONGLY_BULLISH"
            elif bullish_count > bearish_count:
                dashboard_data["market_summary"]["overall_trend"] = "BULLISH"
            elif bearish_count > bullish_count * 1.5:
                dashboard_data["market_summary"]["overall_trend"] = "STRONGLY_BEARISH"
            elif bearish_count > bullish_count:
                dashboard_data["market_summary"]["overall_trend"] = "BEARISH"
            else:
                dashboard_data["market_summary"]["overall_trend"] = "NEUTRAL"

            trending = []
            for analysis in all_analyses:
                if analysis.get("overall_trend") in ["BULLISH", "STRONGLY_BULLISH", "BEARISH", "STRONGLY_BEARISH"]:
                    trending.append(
                        {
                            "symbol": analysis["symbol"],
                            "trend": analysis["overall_trend"],
                            "strength": analysis.get("overall_strength", 0),
                        }
                    )

            dashboard_data["market_summary"]["trending_symbols"] = trending

            all_patterns = []
            for analysis in all_analyses:
                all_patterns.extend(analysis.get("patterns", []))

            strength_order = {"STRONG": 3, "MODERATE": 2, "WEAK": 1}
            all_patterns.sort(
                key=lambda x: (strength_order.get(x.get("strength", "WEAK"), 0), x.get("date", "")), reverse=True
            )
            dashboard_data["market_summary"]["patterns"] = all_patterns[:10]

        return MarketResponse(success=True, data=dashboard_data, timestamp=datetime.now().isoformat())

    except Exception as e:
        logger.error(f"Error getting OHLC dashboard: {e}")
        return MarketResponse(success=False, error=str(e), timestamp=datetime.now().isoformat())


@router.get("/trends/{symbol}", response_model=MarketResponse)
async def get_trend_analysis(symbol: str):
    """Get focused trend analysis for a symbol"""
    try:
        from src.api.yahoo_client import YahooFinanceClient

        from .deps import collector, ohlc_analyzer, settings

        internals = await collector.collect_market_internals()
        historical_data = {}
        client = YahooFinanceClient(settings)

        for tf_name, tf_config in ohlc_analyzer.timeframes.items():
            try:
                data = client.get_bars(symbol, tf_config["period"], tf_config.get("interval", "1d"))

                if data is not None:
                    historical_data[tf_name] = {"symbol": symbol, "data": []}

                    for _, row in data.iterrows():
                        historical_data[tf_name]["data"].append(
                            {
                                "timestamp": row.name.isoformat(),
                                "open": float(row["open"]),
                                "high": float(row["high"]),
                                "low": float(row["low"]),
                                "close": float(row["close"]),
                                "volume": int(row["volume"]),
                            }
                        )
            except Exception as e:
                logger.warning(f"Could not fetch {tf_name} data for {symbol}: {e}")

        ohlc_analysis = ohlc_analyzer.analyze_symbol({"historical_data": historical_data}, symbol)

        trend_report = {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "current_price": None,
            "market_bias": internals.get("market_bias", "NEUTRAL"),
            "trend_analysis": {},
            "key_levels": {},
            "signals": [],
            "timeframe_consensus": {"bullish_timeframes": [], "bearish_timeframes": [], "neutral_timeframes": []},
        }

        for tf_name, tf_data in ohlc_analysis.get("timeframes", {}).items():
            if "current_price" in tf_data and trend_report["current_price"] is None:
                trend_report["current_price"] = tf_data["current_price"]

            if "trend" in tf_data:
                trend_direction = tf_data["trend"].get("direction", "NEUTRAL")
                trend_strength = tf_data["trend"].get("strength", "WEAK")

                trend_report["trend_analysis"][tf_name] = {
                    "direction": trend_direction,
                    "strength": trend_strength,
                    "momentum": tf_data["trend"].get("momentum_5d", 0),
                    "price_change_pct": tf_data.get("price_change_pct", 0),
                    "atr": tf_data.get("indicators", {}).get("atr", 0),
                }

                if trend_direction in ["BULLISH", "STRONGLY_BULLISH"]:
                    trend_report["timeframe_consensus"]["bullish_timeframes"].append(tf_name)
                elif trend_direction in ["BEARISH", "STRONGLY_BEARISH"]:
                    trend_report["timeframe_consensus"]["bearish_timeframes"].append(tf_name)
                else:
                    trend_report["timeframe_consensus"]["neutral_timeframes"].append(tf_name)

        trend_report["key_levels"] = ohlc_analysis.get("key_levels", {})
        trend_report["signals"] = ohlc_analysis.get("signals", [])

        if symbol.lower() in ["spy", "qqq"]:
            trend_report["market_context"] = {
                "volatility_regime": internals.get("volatilityRegime", "UNKNOWN"),
                "volume_flow": internals.get("volume_flow", {}),
                "correlation_strength": None,
            }

            if "spy" in internals and "qqq" in internals:
                spy_change = internals["spy"].get("change_pct", 0)
                qqq_change = internals["qqq"].get("change_pct", 0)

                if abs(spy_change) > 0.1 and abs(qqq_change) > 0.1:
                    correlation = (spy_change * qqq_change) / (abs(spy_change) * abs(qqq_change))
                    trend_report["market_context"]["correlation_strength"] = max(min(correlation, 1.0), -1.0)

        return MarketResponse(success=True, data=trend_report, timestamp=datetime.now().isoformat())

    except Exception as e:
        logger.error(f"Error getting trend analysis for {symbol}: {e}")
        return MarketResponse(success=False, error=str(e), timestamp=datetime.now().isoformat())
