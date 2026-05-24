"""
ICT and Order Flow API Endpoints

This module contains all ICT-related API endpoints for MarketPulse.
Import these into main.py to keep code organized.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Literal
from datetime import datetime
from loguru import logger

from ..analysis.ict_signal_generator import ICTSignalGenerator
from ..api.yahoo_client import YahooFinanceClient

# Create router for ICT endpoints
ict_router = APIRouter(prefix="/api/ict", tags=["ICT"])


class ICTAnalysisRequest(BaseModel):
    """Request model for ICT analysis"""
    symbol: str
    timeframe: str = "5m"  # 1m, 5m, 15m, 1h, 4h, 1d
    lookback: int = 100  # Number of candles to analyze


class MarketResponse(BaseModel):
    """Standard response model"""
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None
    timestamp: str


@ict_router.post("/analyze", response_model=MarketResponse)
async def analyze_ict_concepts(request: ICTAnalysisRequest):
    """
    Comprehensive ICT analysis for a symbol

    Returns all detected ICT concepts:
    - Fair Value Gaps
    - Order Blocks
    - Liquidity Pools
    - Market Structure
    - Order Flow Data
    """
    try:
        # Get candlestick data
        client = YahooFinanceClient()

        # Map timeframe to Yahoo Finance interval
        interval_map = {
            '1m': '1m',
            '5m': '5m',
            '15m': '15m',
            '30m': '30m',
            '1h': '1h',
            '4h': '1d',  # Yahoo doesn't have 4h
            '1d': '1d'
        }

        period_map = {
            '1m': '1d',
            '5m': '5d',
            '15m': '5d',
            '30m': '5d',
            '1h': '1mo',
            '4h': '1mo',
            '1d': '3mo'
        }

        interval = interval_map.get(request.timeframe, '5m')
        period = period_map.get(request.timeframe, '5d')

        candles = client.get_bars(request.symbol, period=period, interval=interval)

        if candles is None or candles.empty:
            return MarketResponse(
                success=False,
                error=f"No data available for {request.symbol}",
                timestamp=datetime.now().isoformat()
            )

        # Limit to requested lookback
        if len(candles) > request.lookback:
            candles = candles.iloc[-request.lookback:]

        # Initialize ICT signal generator
        generator = ICTSignalGenerator()

        # Analyze market
        analysis = generator.analyze_market(candles)

        # Format response
        result = {
            'symbol': request.symbol,
            'timeframe': request.timeframe,
            'candles_analyzed': len(candles),
            'fair_value_gaps': [
                {
                    'type': fvg.type,
                    'upper': float(fvg.upper),
                    'lower': float(fvg.lower),
                    'size': float(fvg.size),
                    'midpoint': float(fvg.midpoint()),
                    'filled': fvg.filled,
                    'fill_percentage': float(fvg.fill_percentage),
                    'timestamp': fvg.timestamp.isoformat() if isinstance(fvg.timestamp, datetime) else str(fvg.timestamp)
                }
                for fvg in analysis['fvgs']
            ],
            'order_blocks': [
                {
                    'type': ob.type,
                    'high': float(ob.high),
                    'low': float(ob.low),
                    'midpoint': float(ob.midpoint()),
                    'strength': float(ob.strength),
                    'tested': ob.tested,
                    'broken': ob.broken,
                    'timestamp': ob.timestamp.isoformat() if isinstance(ob.timestamp, datetime) else str(ob.timestamp)
                }
                for ob in analysis['order_blocks']
            ],
            'liquidity_pools': [
                {
                    'type': lp.type,
                    'price': float(lp.price),
                    'strength': float(lp.strength),
                    'swept': lp.swept,
                    'timestamp': lp.timestamp.isoformat() if isinstance(lp.timestamp, datetime) else str(lp.timestamp)
                }
                for lp in analysis['liquidity_pools']
            ],
            'market_structure': {
                'type': analysis['market_structure'].type,
                'swing_highs': [
                    {'timestamp': str(ts), 'price': float(price)}
                    for ts, price in analysis['market_structure'].swing_highs[-5:]  # Last 5
                ],
                'swing_lows': [
                    {'timestamp': str(ts), 'price': float(price)}
                    for ts, price in analysis['market_structure'].swing_lows[-5:]  # Last 5
                ]
            },
            'volume_profile': {
                'poc': float(analysis['volume_profile'].poc),
                'vah': float(analysis['volume_profile'].vah),
                'val': float(analysis['volume_profile'].val),
                'total_volume': float(analysis['volume_profile'].total_volume)
            },
            'current_price': float(candles.iloc[-1]['close']),
            'analysis_timestamp': analysis['timestamp'].isoformat()
        }

        return MarketResponse(
            success=True,
            data=result,
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error in ICT analysis: {e}")
        return MarketResponse(
            success=False,
            error=str(e),
            timestamp=datetime.now().isoformat()
        )


@ict_router.post("/signals", response_model=MarketResponse)
async def generate_ict_signals(request: ICTAnalysisRequest):
    """
    Generate ICT trading signals

    Combines FVG, Order Blocks, Liquidity, and Order Flow
    to generate high-probability trade signals
    """
    try:
        # Get candlestick data
        client = YahooFinanceClient()

        interval_map = {'1m': '1m', '5m': '5m', '15m': '15m', '30m': '30m', '1h': '1h', '4h': '1d', '1d': '1d'}
        period_map = {'1m': '1d', '5m': '5d', '15m': '5d', '30m': '5d', '1h': '1mo', '4h': '1mo', '1d': '3mo'}

        interval = interval_map.get(request.timeframe, '5m')
        period = period_map.get(request.timeframe, '5d')

        candles = client.get_bars(request.symbol, period=period, interval=interval)

        if candles is None or candles.empty:
            return MarketResponse(
                success=False,
                error=f"No data available for {request.symbol}",
                timestamp=datetime.now().isoformat()
            )

        if len(candles) > request.lookback:
            candles = candles.iloc[-request.lookback:]

        # Generate signals
        generator = ICTSignalGenerator()
        signals = generator.generate_signals(candles)

        # Format signals
        result = {
            'symbol': request.symbol,
            'timeframe': request.timeframe,
            'signals_count': len(signals),
            'signals': [
                {
                    'type': signal.type,
                    'confidence': float(signal.confidence),
                    'entry_price': float(signal.entry_price),
                    'stop_loss': float(signal.stop_loss),
                    'take_profit': [float(tp) for tp in signal.take_profit],
                    'risk': float(signal.risk),
                    'reward': float(signal.reward),
                    'risk_reward_ratio': float(signal.risk_reward_ratio),
                    'trigger': signal.trigger,
                    'ict_elements': signal.ict_elements,
                    'order_flow_confirmation': signal.order_flow_confirmation,
                    'market_structure': signal.market_structure,
                    'timestamp': signal.timestamp.isoformat() if isinstance(signal.timestamp, datetime) else str(signal.timestamp)
                }
                for signal in signals
            ],
            'top_signal': None
        }

        # Add top signal if any exist
        if signals:
            top = max(signals, key=lambda s: s.confidence)
            result['top_signal'] = {
                'type': top.type,
                'confidence': float(top.confidence),
                'entry': float(top.entry_price),
                'stop': float(top.stop_loss),
                'targets': [float(tp) for tp in top.take_profit],
                'trigger': top.trigger
            }

        return MarketResponse(
            success=True,
            data=result,
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error generating ICT signals: {e}")
        return MarketResponse(
            success=False,
            error=str(e),
            timestamp=datetime.now().isoformat()
        )


@ict_router.get("/quick-scan/{symbol}", response_model=MarketResponse)
async def quick_ict_scan(symbol: str):
    """
    Quick ICT scan - optimized for speed

    Returns only the most critical info:
    - Active unfilled FVGs
    - Untested Order Blocks
    - Unswept Liquidity
    - Current market structure
    """
    try:
        client = YahooFinanceClient()
        candles = client.get_bars(symbol, period='5d', interval='5m')

        if candles is None or candles.empty:
            return MarketResponse(
                success=False,
                error=f"No data for {symbol}",
                timestamp=datetime.now().isoformat()
            )

        # Quick analysis
        generator = ICTSignalGenerator()
        analysis = generator.analyze_market(candles.iloc[-50:])  # Last 50 candles only

        # Filter for actionable items only
        active_fvgs = [fvg for fvg in analysis['fvgs'] if not fvg.filled]
        active_obs = [ob for ob in analysis['order_blocks'] if not ob.broken]
        unswept_liq = [lp for lp in analysis['liquidity_pools'] if not lp.swept]

        result = {
            'symbol': symbol,
            'current_price': float(candles.iloc[-1]['close']),
            'market_structure': analysis['market_structure'].type,
            'active_fvgs_count': len(active_fvgs),
            'active_obs_count': len(active_obs),
            'unswept_liquidity_count': len(unswept_liq),
            'poc': float(analysis['volume_profile'].poc),
            'value_area': {
                'high': float(analysis['volume_profile'].vah),
                'low': float(analysis['volume_profile'].val)
            },
            'quick_bias': 'bullish' if analysis['market_structure'].type == 'bullish' else 'bearish' if analysis['market_structure'].type == 'bearish' else 'neutral'
        }

        return MarketResponse(
            success=True,
            data=result,
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error in quick ICT scan: {e}")
        return MarketResponse(
            success=False,
            error=str(e),
            timestamp=datetime.now().isoformat()
        )
