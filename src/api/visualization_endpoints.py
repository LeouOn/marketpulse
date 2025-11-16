"""
Visualization API Endpoints

Serves interactive charts and visualizations:
- Candlestick charts with indicators
- Technical indicator panels
- ICT overlays
- Volume profiles
- Market heatmaps
- Risk dashboards
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
from loguru import logger
import pandas as pd

from src.visualization.chart_generator import ChartGenerator
from src.api.yahoo_client import YahooFinanceClient
from src.analysis.technical_indicators import TechnicalIndicators, identify_trends, get_support_resistance

# Initialize router
viz_router = APIRouter(prefix="/api/viz", tags=["Visualizations"])

# Initialize services
chart_gen = ChartGenerator(theme='dark')
yahoo_client = YahooFinanceClient()


class ChartRequest(BaseModel):
    """Request for chart generation"""
    symbol: str
    timeframe: str = "1d"  # 1m, 5m, 15m, 1h, 1d
    period: str = "1mo"  # 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, max
    indicators: Optional[List[str]] = None
    show_volume: bool = True
    height: int = 800


@viz_router.post("/candlestick")
async def get_candlestick_chart(request: ChartRequest):
    """
    Get interactive candlestick chart with indicators

    Available indicators:
    - sma_20, sma_50, sma_200
    - ema_9, ema_21, ema_50
    - rsi, macd, bollinger
    - atr, stochastic, vwap
    - obv, adx, supertrend

    Returns HTML with embedded Plotly chart
    """
    try:
        # Get historical data
        df = yahoo_client.get_historical_data(
            symbol=request.symbol,
            period=request.period,
            interval=request.timeframe
        )

        if df.empty:
            raise HTTPException(status_code=404, detail=f"No data found for {request.symbol}")

        # Generate chart
        fig = chart_gen.create_candlestick_chart(
            df=df,
            title=f"{request.symbol} - {request.timeframe}",
            indicators=request.indicators,
            show_volume=request.show_volume,
            height=request.height
        )

        # Return as HTML
        html = fig.to_html(
            include_plotlyjs='cdn',
            config={'displayModeBar': True, 'responsive': True}
        )

        return HTMLResponse(content=html)

    except Exception as e:
        logger.error(f"Error generating candlestick chart: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@viz_router.get("/candlestick/{symbol}")
async def get_candlestick_chart_simple(
    symbol: str,
    timeframe: str = Query("1d"),
    period: str = Query("1mo"),
    indicators: Optional[str] = Query(None),  # Comma-separated
    height: int = Query(800)
):
    """
    Get candlestick chart (simple GET endpoint)

    Args:
        symbol: Stock symbol
        timeframe: 1m, 5m, 15m, 1h, 1d
        period: 1d, 5d, 1mo, 3mo, 6mo, 1y
        indicators: Comma-separated list (e.g., "sma_20,ema_50,rsi")
        height: Chart height in pixels

    Returns:
        HTML page with interactive chart
    """
    indicator_list = indicators.split(',') if indicators else None

    request = ChartRequest(
        symbol=symbol,
        timeframe=timeframe,
        period=period,
        indicators=indicator_list,
        height=height
    )

    return await get_candlestick_chart(request)


@viz_router.get("/indicators/{symbol}")
async def get_indicator_panel(
    symbol: str,
    timeframe: str = Query("1d"),
    period: str = Query("1mo")
):
    """
    Get technical indicator panel

    Shows RSI, MACD, and Stochastic in separate subplots

    Returns HTML with embedded chart
    """
    try:
        # Get historical data
        df = yahoo_client.get_historical_data(
            symbol=symbol,
            period=period,
            interval=timeframe
        )

        if df.empty:
            raise HTTPException(status_code=404, detail=f"No data found for {symbol}")

        # Generate indicator panel
        fig = chart_gen.create_indicator_panel(
            df=df,
            title=f"{symbol} - Technical Indicators"
        )

        # Return as HTML
        html = fig.to_html(
            include_plotlyjs='cdn',
            config={'displayModeBar': True, 'responsive': True}
        )

        return HTMLResponse(content=html)

    except Exception as e:
        logger.error(f"Error generating indicator panel: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@viz_router.get("/volume-profile/{symbol}")
async def get_volume_profile(
    symbol: str,
    timeframe: str = Query("1d"),
    period: str = Query("1mo"),
    bins: int = Query(50)
):
    """
    Get volume profile chart

    Shows horizontal volume distribution with POC, VAH, VAL

    Returns HTML with embedded chart
    """
    try:
        # Get historical data
        df = yahoo_client.get_historical_data(
            symbol=symbol,
            period=period,
            interval=timeframe
        )

        if df.empty:
            raise HTTPException(status_code=404, detail=f"No data found for {symbol}")

        # Generate volume profile
        fig = chart_gen.create_volume_profile(
            df=df,
            bins=bins,
            title=f"{symbol} - Volume Profile"
        )

        # Return as HTML
        html = fig.to_html(
            include_plotlyjs='cdn',
            config={'displayModeBar': True, 'responsive': True}
        )

        return HTMLResponse(content=html)

    except Exception as e:
        logger.error(f"Error generating volume profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@viz_router.get("/market-heatmap")
async def get_market_heatmap(
    sector: bool = Query(True, description="Show sector heatmap")
):
    """
    Get market heatmap

    Shows color-coded performance of sectors or individual stocks

    Returns HTML with embedded chart
    """
    try:
        if sector:
            # Get sector ETF performance
            sector_etfs = {
                'Technology': 'XLK',
                'Financials': 'XLF',
                'Healthcare': 'XLV',
                'Consumer Discretionary': 'XLY',
                'Communication': 'XLC',
                'Industrials': 'XLI',
                'Consumer Staples': 'XLP',
                'Energy': 'XLE',
                'Utilities': 'XLU',
                'Real Estate': 'XLRE',
                'Materials': 'XLB'
            }

            performance = {}
            for name, symbol in sector_etfs.items():
                try:
                    df = yahoo_client.get_historical_data(symbol, period='5d', interval='1d')
                    if not df.empty and len(df) >= 2:
                        # Calculate daily change
                        change = ((df['close'].iloc[-1] - df['close'].iloc[-2]) / df['close'].iloc[-2]) * 100
                        performance[name] = change
                except:
                    continue

            title = "Sector Performance Heatmap"
        else:
            # Get major indices
            indices = {
                'S&P 500': '^GSPC',
                'Nasdaq': '^IXIC',
                'Dow Jones': '^DJI',
                'Russell 2000': '^RUT',
                'VIX': '^VIX'
            }

            performance = {}
            for name, symbol in indices.items():
                try:
                    df = yahoo_client.get_historical_data(symbol, period='5d', interval='1d')
                    if not df.empty and len(df) >= 2:
                        change = ((df['close'].iloc[-1] - df['close'].iloc[-2]) / df['close'].iloc[-2]) * 100
                        performance[name] = change
                except:
                    continue

            title = "Market Indices Heatmap"

        if not performance:
            raise HTTPException(status_code=404, detail="No data available for heatmap")

        # Generate heatmap
        fig = chart_gen.create_market_heatmap(
            data=performance,
            title=title
        )

        # Return as HTML
        html = fig.to_html(
            include_plotlyjs='cdn',
            config={'displayModeBar': True, 'responsive': True}
        )

        return HTMLResponse(content=html)

    except Exception as e:
        logger.error(f"Error generating market heatmap: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@viz_router.get("/analysis/{symbol}")
async def get_technical_analysis(
    symbol: str,
    timeframe: str = Query("1d"),
    period: str = Query("1mo")
):
    """
    Get comprehensive technical analysis

    Returns JSON with:
    - Current trends (SMA, RSI, MACD, Supertrend)
    - Support and resistance levels
    - Indicator values
    - Trade signals

    Returns JSON response
    """
    try:
        # Get historical data
        df = yahoo_client.get_historical_data(
            symbol=symbol,
            period=period,
            interval=timeframe
        )

        if df.empty:
            raise HTTPException(status_code=404, detail=f"No data found for {symbol}")

        # Calculate indicators
        df_with_indicators = TechnicalIndicators.calculate_all(df)

        # Get latest values
        latest = df_with_indicators.iloc[-1]

        # Identify trends
        trends = identify_trends(df_with_indicators)

        # Get support/resistance
        sr_levels = get_support_resistance(df_with_indicators)

        # Build response
        analysis = {
            'symbol': symbol,
            'timestamp': datetime.now().isoformat(),
            'current_price': float(latest['close']),
            'trends': trends,
            'support_resistance': {
                'resistance': [float(x) for x in sr_levels['resistance']],
                'support': [float(x) for x in sr_levels['support']]
            },
            'indicators': {
                'sma_20': float(latest['sma_20']) if 'sma_20' in latest else None,
                'sma_50': float(latest['sma_50']) if 'sma_50' in latest else None,
                'sma_200': float(latest['sma_200']) if 'sma_200' in latest else None,
                'ema_21': float(latest['ema_21']) if 'ema_21' in latest else None,
                'rsi': float(latest['rsi']) if 'rsi' in latest else None,
                'macd': float(latest['macd']) if 'macd' in latest else None,
                'macd_signal': float(latest['macd_signal']) if 'macd_signal' in latest else None,
                'bb_upper': float(latest['bb_upper']) if 'bb_upper' in latest else None,
                'bb_lower': float(latest['bb_lower']) if 'bb_lower' in latest else None,
                'atr': float(latest['atr']) if 'atr' in latest else None,
                'adx': float(latest['adx']) if 'adx' in latest else None
            },
            'signals': {
                'overall': 'bullish' if sum(1 for t in trends.values() if 'bullish' in t) > sum(1 for t in trends.values() if 'bearish' in t) else 'bearish',
                'strength': len([t for t in trends.values() if 'strong' in t])
            }
        }

        return JSONResponse(content={"success": True, "data": analysis})

    except Exception as e:
        logger.error(f"Error generating technical analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@viz_router.get("/dashboard/{symbol}")
async def get_trading_dashboard(
    symbol: str,
    timeframe: str = Query("1d"),
    period: str = Query("3mo")
):
    """
    Get complete trading dashboard

    Combines price chart, indicators, and analysis into one page

    Returns HTML with full dashboard
    """
    try:
        # Get data
        df = yahoo_client.get_historical_data(
            symbol=symbol,
            period=period,
            interval=timeframe
        )

        if df.empty:
            raise HTTPException(status_code=404, detail=f"No data found for {symbol}")

        # Generate charts
        price_chart = chart_gen.create_candlestick_chart(
            df=df,
            title=f"{symbol} Price Chart",
            indicators=['sma_20', 'sma_50', 'ema_21', 'vwap', 'bollinger'],
            show_volume=True,
            height=600
        )

        indicator_panel = chart_gen.create_indicator_panel(
            df=df,
            title=f"{symbol} Indicators"
        )

        # Calculate analysis
        df_with_indicators = TechnicalIndicators.calculate_all(df)
        trends = identify_trends(df_with_indicators)
        sr_levels = get_support_resistance(df_with_indicators)
        latest = df_with_indicators.iloc[-1]

        # Build HTML dashboard
        html_template = f"""
<!DOCTYPE html>
<html>
<head>
    <title>{symbol} Trading Dashboard</title>
    <script src="https://cdn.plotly.com/plotly-latest.min.js"></script>
    <style>
        body {{
            font-family: Arial, sans-serif;
            background-color: #1e1e1e;
            color: #e0e0e0;
            margin: 0;
            padding: 20px;
        }}
        .dashboard {{
            max-width: 1600px;
            margin: 0 auto;
        }}
        .header {{
            text-align: center;
            padding: 20px;
            background-color: #2d2d2d;
            border-radius: 10px;
            margin-bottom: 20px;
        }}
        .header h1 {{
            margin: 0;
            color: #26a69a;
        }}
        .metrics {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }}
        .metric-card {{
            background-color: #2d2d2d;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }}
        .metric-label {{
            font-size: 12px;
            color: #888;
            margin-bottom: 5px;
        }}
        .metric-value {{
            font-size: 24px;
            font-weight: bold;
        }}
        .bullish {{ color: #26a69a; }}
        .bearish {{ color: #ef5350; }}
        .neutral {{ color: #78909c; }}
        .chart-container {{
            background-color: #2d2d2d;
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 20px;
        }}
        .analysis {{
            background-color: #2d2d2d;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
        }}
        .analysis h3 {{
            margin-top: 0;
            color: #26a69a;
        }}
        .signal-list {{
            list-style: none;
            padding: 0;
        }}
        .signal-list li {{
            padding: 8px;
            margin: 5px 0;
            background-color: #1e1e1e;
            border-radius: 5px;
        }}
    </style>
</head>
<body>
    <div class="dashboard">
        <div class="header">
            <h1>{symbol} Trading Dashboard</h1>
            <p>Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>

        <div class="metrics">
            <div class="metric-card">
                <div class="metric-label">Current Price</div>
                <div class="metric-value">${latest['close']:.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">RSI (14)</div>
                <div class="metric-value {'bullish' if latest.get('rsi', 50) < 30 else 'bearish' if latest.get('rsi', 50) > 70 else 'neutral'}">
                    {latest.get('rsi', 0):.1f}
                </div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Trend</div>
                <div class="metric-value {trends.get('sma_trend', 'neutral').replace('_', ' ')}">
                    {trends.get('sma_trend', 'neutral').replace('_', ' ').title()}
                </div>
            </div>
            <div class="metric-card">
                <div class="metric-label">MACD Signal</div>
                <div class="metric-value {trends.get('macd_signal', 'neutral')}">
                    {trends.get('macd_signal', 'neutral').title()}
                </div>
            </div>
            <div class="metric-card">
                <div class="metric-label">ATR</div>
                <div class="metric-value">{latest.get('atr', 0):.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Volume</div>
                <div class="metric-value">{latest.get('volume', 0):,.0f}</div>
            </div>
        </div>

        <div class="chart-container">
            {price_chart.to_html(include_plotlyjs=False, div_id="price-chart")}
        </div>

        <div class="chart-container">
            {indicator_panel.to_html(include_plotlyjs=False, div_id="indicator-panel")}
        </div>

        <div class="analysis">
            <h3>Support & Resistance</h3>
            <p><strong>Resistance:</strong> {', '.join([f'${x:.2f}' for x in sr_levels['resistance']])}</p>
            <p><strong>Support:</strong> {', '.join([f'${x:.2f}' for x in sr_levels['support']])}</p>

            <h3>Trend Analysis</h3>
            <ul class="signal-list">
                {''.join([f'<li><strong>{k.replace("_", " ").title()}:</strong> <span class="{v}">{v.replace("_", " ").title()}</span></li>' for k, v in trends.items()])}
            </ul>
        </div>
    </div>
</body>
</html>
        """

        return HTMLResponse(content=html_template)

    except Exception as e:
        logger.error(f"Error generating dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@viz_router.get("/")
async def visualization_home():
    """
    Visualization home page with links to all visualizations
    """
    html = """
<!DOCTYPE html>
<html>
<head>
    <title>MarketPulse Visualizations</title>
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
        .endpoint-list {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-top: 40px;
        }
        .endpoint-card {
            background-color: #2d2d2d;
            padding: 20px;
            border-radius: 10px;
            transition: transform 0.2s;
        }
        .endpoint-card:hover {
            transform: translateY(-5px);
            background-color: #363636;
        }
        .endpoint-card h3 {
            color: #26a69a;
            margin-top: 0;
        }
        .endpoint-card a {
            color: #64b5f6;
            text-decoration: none;
        }
        .endpoint-card a:hover {
            text-decoration: underline;
        }
        .example {
            background-color: #1e1e1e;
            padding: 10px;
            border-radius: 5px;
            margin-top: 10px;
            font-family: monospace;
            font-size: 12px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 MarketPulse Visualizations</h1>
        <p style="text-align: center;">Interactive charts and market analysis tools</p>

        <div class="endpoint-list">
            <div class="endpoint-card">
                <h3>📈 Candlestick Chart</h3>
                <p>Interactive price chart with technical indicators</p>
                <div class="example">
                    <a href="/api/viz/candlestick/AAPL?indicators=sma_20,ema_50,vwap&period=3mo" target="_blank">
                        /api/viz/candlestick/AAPL
                    </a>
                </div>
            </div>

            <div class="endpoint-card">
                <h3>📊 Indicator Panel</h3>
                <p>RSI, MACD, and Stochastic indicators</p>
                <div class="example">
                    <a href="/api/viz/indicators/AAPL?period=3mo" target="_blank">
                        /api/viz/indicators/AAPL
                    </a>
                </div>
            </div>

            <div class="endpoint-card">
                <h3>🔊 Volume Profile</h3>
                <p>Horizontal volume distribution with POC</p>
                <div class="example">
                    <a href="/api/viz/volume-profile/AAPL?period=1mo" target="_blank">
                        /api/viz/volume-profile/AAPL
                    </a>
                </div>
            </div>

            <div class="endpoint-card">
                <h3>🗺️ Market Heatmap</h3>
                <p>Sector or index performance heatmap</p>
                <div class="example">
                    <a href="/api/viz/market-heatmap?sector=true" target="_blank">
                        /api/viz/market-heatmap
                    </a>
                </div>
            </div>

            <div class="endpoint-card">
                <h3>🎯 Technical Analysis</h3>
                <p>Comprehensive analysis with signals (JSON)</p>
                <div class="example">
                    <a href="/api/viz/analysis/AAPL?period=3mo" target="_blank">
                        /api/viz/analysis/AAPL
                    </a>
                </div>
            </div>

            <div class="endpoint-card">
                <h3>🎛️ Trading Dashboard</h3>
                <p>Complete dashboard with all analysis</p>
                <div class="example">
                    <a href="/api/viz/dashboard/AAPL?period=3mo" target="_blank">
                        /api/viz/dashboard/AAPL
                    </a>
                </div>
            </div>
        </div>

        <div style="margin-top: 40px; padding: 20px; background-color: #2d2d2d; border-radius: 10px;">
            <h3 style="color: #26a69a;">Available Indicators:</h3>
            <p>sma_20, sma_50, sma_200, ema_9, ema_21, ema_50, rsi, macd, bollinger, atr, stochastic, vwap, obv, adx, supertrend</p>

            <h3 style="color: #26a69a; margin-top: 20px;">Example URLs:</h3>
            <ul>
                <li><code>/api/viz/candlestick/MNQ?timeframe=5m&period=1d&indicators=sma_20,vwap,supertrend</code></li>
                <li><code>/api/viz/dashboard/TSLA?period=6mo</code></li>
                <li><code>/api/viz/analysis/SPY?period=1y</code></li>
            </ul>
        </div>
    </div>
</body>
</html>
    """
    return HTMLResponse(content=html)
