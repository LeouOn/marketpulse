"""
Divergence Detection API Endpoints

Scan for and visualize divergences:
- RSI, MACD, Stochastic, Volume divergences
- Regular and hidden divergences
- Interactive charts with divergence overlays
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from loguru import logger

from src.analysis.divergence_detector import DivergenceDetector, scan_for_divergences
from src.visualization.chart_generator import ChartGenerator
from src.api.yahoo_client import YahooFinanceClient

# Initialize router
divergence_router = APIRouter(prefix="/api/divergence", tags=["Divergence Detection"])

# Initialize services
detector = DivergenceDetector(min_strength=60.0)
chart_gen = ChartGenerator(theme='dark')
yahoo_client = YahooFinanceClient()


class DivergenceScanRequest(BaseModel):
    """Request for divergence scan"""
    symbol: str
    timeframe: str = "1d"
    period: str = "3mo"
    min_strength: float = 60.0
    indicators: Optional[List[str]] = None  # None = all


@divergence_router.post("/scan")
async def scan_divergences(request: DivergenceScanRequest):
    """
    Scan for all divergences

    Returns JSON with detected divergences and overall signal
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

        # Scan for divergences
        result = scan_for_divergences(df, min_strength=request.min_strength)

        # Add symbol and timestamp
        result['symbol'] = request.symbol
        result['timestamp'] = datetime.now().isoformat()

        return JSONResponse(content={"success": True, "data": result})

    except Exception as e:
        logger.error(f"Error scanning divergences: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@divergence_router.get("/scan/{symbol}")
async def scan_divergences_simple(
    symbol: str,
    timeframe: str = Query("1d"),
    period: str = Query("3mo"),
    min_strength: float = Query(60.0)
):
    """
    Scan for divergences (simple GET endpoint)

    Args:
        symbol: Stock symbol
        timeframe: 1m, 5m, 15m, 1h, 1d
        period: 1d, 5d, 1mo, 3mo, 6mo, 1y
        min_strength: Minimum strength (0-100)

    Returns:
        JSON with divergences
    """
    request = DivergenceScanRequest(
        symbol=symbol,
        timeframe=timeframe,
        period=period,
        min_strength=min_strength
    )

    return await scan_divergences(request)


@divergence_router.get("/chart/{symbol}")
async def get_divergence_chart(
    symbol: str,
    timeframe: str = Query("1d"),
    period: str = Query("3mo"),
    min_strength: float = Query(60.0),
    indicators: Optional[str] = Query(None)
):
    """
    Get candlestick chart with divergence overlays

    Args:
        symbol: Stock symbol
        timeframe: 1m, 5m, 15m, 1h, 1d
        period: 1d, 5d, 1mo, 3mo, 6mo, 1y
        min_strength: Minimum divergence strength (0-100)
        indicators: Comma-separated list (e.g., "sma_20,ema_50")

    Returns:
        HTML with interactive chart showing divergences
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

        # Scan for divergences
        result = scan_for_divergences(df, min_strength=min_strength)

        # Parse indicators
        indicator_list = indicators.split(',') if indicators else ['sma_20', 'ema_50', 'vwap']

        # Create base chart
        fig = chart_gen.create_candlestick_chart(
            df=df,
            title=f"{symbol} - Divergence Analysis",
            indicators=indicator_list,
            show_volume=True,
            height=800
        )

        # Add divergence overlays
        if result['divergences']:
            fig = chart_gen.add_divergence_overlays(
                fig=fig,
                df=df,
                divergences=result['divergences']
            )

        # Add summary text
        summary_text = f"Found {result['total_divergences']} divergences | Signal: {result['signal']}"
        if result['strongest']:
            summary_text += f"<br>Strongest: {result['strongest']['indicator'].upper()} "
            summary_text += f"{result['strongest']['type'].replace('_', ' ').title()} "
            summary_text += f"(strength: {result['strongest']['strength']:.0f})"

        fig.add_annotation(
            text=summary_text,
            xref="paper", yref="paper",
            x=0.5, y=1.08,
            showarrow=False,
            font=dict(size=14, color='#26a69a'),
            bgcolor='rgba(0,0,0,0.5)',
            bordercolor='#26a69a',
            borderwidth=2
        )

        # Return as HTML
        html = fig.to_html(
            include_plotlyjs='cdn',
            config={'displayModeBar': True, 'responsive': True}
        )

        return HTMLResponse(content=html)

    except Exception as e:
        logger.error(f"Error generating divergence chart: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@divergence_router.get("/dashboard/{symbol}")
async def get_divergence_dashboard(
    symbol: str,
    timeframe: str = Query("1d"),
    period: str = Query("3mo"),
    min_strength: float = Query(60.0)
):
    """
    Get comprehensive divergence dashboard

    Combines:
    - Price chart with divergence overlays
    - Indicator panel (RSI, MACD, Stochastic)
    - Divergence summary and signals

    Returns HTML dashboard
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

        # Scan for divergences
        result = scan_for_divergences(df, min_strength=min_strength)

        # Create price chart with divergences
        price_chart = chart_gen.create_candlestick_chart(
            df=df,
            title=f"{symbol} Price Chart",
            indicators=['sma_20', 'ema_50', 'vwap'],
            show_volume=True,
            height=600
        )

        if result['divergences']:
            price_chart = chart_gen.add_divergence_overlays(
                fig=price_chart,
                df=df,
                divergences=result['divergences']
            )

        # Create indicator panel
        indicator_panel = chart_gen.create_indicator_panel(
            df=df,
            title=f"{symbol} Indicators"
        )

        # Build HTML dashboard
        html_template = f"""
<!DOCTYPE html>
<html>
<head>
    <title>{symbol} Divergence Dashboard</title>
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
        .signal-banner {{
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            text-align: center;
            font-size: 18px;
            font-weight: bold;
        }}
        .signal-STRONG_BULLISH {{ background-color: rgba(76, 175, 80, 0.3); color: #4CAF50; }}
        .signal-BULLISH {{ background-color: rgba(76, 175, 80, 0.2); color: #81C784; }}
        .signal-STRONG_BEARISH {{ background-color: rgba(244, 67, 54, 0.3); color: #F44336; }}
        .signal-BEARISH {{ background-color: rgba(244, 67, 54, 0.2); color: #E57373; }}
        .signal-NEUTRAL {{ background-color: rgba(120, 144, 156, 0.2); color: #78909C; }}
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
            color: #26a69a;
        }}
        .chart-container {{
            background-color: #2d2d2d;
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 20px;
        }}
        .divergence-list {{
            background-color: #2d2d2d;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
        }}
        .divergence-list h3 {{
            margin-top: 0;
            color: #26a69a;
        }}
        .divergence-item {{
            padding: 12px;
            margin: 8px 0;
            background-color: #1e1e1e;
            border-radius: 5px;
            border-left: 4px solid;
        }}
        .div-bullish {{ border-left-color: #4CAF50; }}
        .div-bearish {{ border-left-color: #F44336; }}
        .strength-bar {{
            height: 8px;
            background-color: #444;
            border-radius: 4px;
            margin-top: 8px;
            overflow: hidden;
        }}
        .strength-fill {{
            height: 100%;
            transition: width 0.3s;
        }}
    </style>
</head>
<body>
    <div class="dashboard">
        <div class="header">
            <h1>📊 {symbol} Divergence Dashboard</h1>
            <p>Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>

        <div class="signal-banner signal-{result['signal']}">
            Overall Signal: {result['signal'].replace('_', ' ')}
        </div>

        <div class="metrics">
            <div class="metric-card">
                <div class="metric-label">Total Divergences</div>
                <div class="metric-value">{result['total_divergences']}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Regular Bullish</div>
                <div class="metric-value" style="color: #4CAF50;">{result['by_type']['regular_bullish']}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Regular Bearish</div>
                <div class="metric-value" style="color: #F44336;">{result['by_type']['regular_bearish']}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Hidden Bullish</div>
                <div class="metric-value" style="color: #81C784;">{result['by_type']['hidden_bullish']}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Hidden Bearish</div>
                <div class="metric-value" style="color: #E57373;">{result['by_type']['hidden_bearish']}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Strongest Signal</div>
                <div class="metric-value" style="color: #FFD700;">{result['strongest']['strength']:.0f if result['strongest'] else 0}</div>
            </div>
        </div>

        <div class="chart-container">
            {price_chart.to_html(include_plotlyjs=False, div_id="price-chart")}
        </div>

        <div class="chart-container">
            {indicator_panel.to_html(include_plotlyjs=False, div_id="indicator-panel")}
        </div>

        <div class="divergence-list">
            <h3>🔍 Detected Divergences</h3>
            {'<p style="color: #888;">No divergences detected above minimum strength threshold.</p>' if not result['divergences'] else ''}
            {''.join([f'''
            <div class="divergence-item div-{'bullish' if 'bullish' in div['type'] else 'bearish'}">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <strong style="color: {'#4CAF50' if 'bullish' in div['type'] else '#F44336'};">
                            {div['indicator'].upper()} - {div['type'].replace('_', ' ').title()}
                        </strong>
                        <div style="font-size: 13px; color: #aaa; margin-top: 4px;">
                            {div['description']}
                        </div>
                        <div style="font-size: 12px; color: #888; margin-top: 4px;">
                            {div['start_time'][:10]} to {div['end_time'][:10]}
                        </div>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-size: 20px; font-weight: bold; color: {'#4CAF50' if 'bullish' in div['type'] else '#F44336'};">
                            {div['strength']:.0f}
                        </div>
                        <div style="font-size: 11px; color: #888;">Strength</div>
                    </div>
                </div>
                <div class="strength-bar">
                    <div class="strength-fill" style="width: {div['strength']}%; background-color: {'#4CAF50' if 'bullish' in div['type'] else '#F44336'};"></div>
                </div>
            </div>
            ''' for div in result['divergences']])}
        </div>

        <div style="background-color: #2d2d2d; padding: 20px; border-radius: 10px;">
            <h3 style="color: #26a69a; margin-top: 0;">📚 Understanding Divergences</h3>
            <ul style="line-height: 1.8;">
                <li><strong style="color: #4CAF50;">Regular Bullish:</strong> Price makes lower low, indicator makes higher low - potential reversal UP</li>
                <li><strong style="color: #F44336;">Regular Bearish:</strong> Price makes higher high, indicator makes lower high - potential reversal DOWN</li>
                <li><strong style="color: #81C784;">Hidden Bullish:</strong> Price makes higher low, indicator makes lower low - trend continuation UP</li>
                <li><strong style="color: #E57373;">Hidden Bearish:</strong> Price makes lower high, indicator makes higher high - trend continuation DOWN</li>
            </ul>
            <p style="color: #888; font-size: 13px; margin-top: 15px;">
                💡 Tip: Regular divergences signal potential trend reversals, while hidden divergences suggest trend continuation.
                Higher strength scores indicate more reliable signals. Volume divergences (OBV) are particularly powerful.
            </p>
        </div>
    </div>
</body>
</html>
        """

        return HTMLResponse(content=html_template)

    except Exception as e:
        logger.error(f"Error generating divergence dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@divergence_router.get("/")
async def divergence_home():
    """Divergence detection home page"""
    html = """
<!DOCTYPE html>
<html>
<head>
    <title>MarketPulse Divergence Detection</title>
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
        .description {
            text-align: center;
            color: #888;
            margin-bottom: 40px;
        }
        .endpoint-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 20px;
            margin-top: 30px;
        }
        .endpoint-card {
            background-color: #2d2d2d;
            padding: 25px;
            border-radius: 10px;
            transition: transform 0.2s;
            border-left: 4px solid #26a69a;
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
            padding: 12px;
            border-radius: 5px;
            margin-top: 12px;
            font-family: monospace;
            font-size: 13px;
        }
        .info-box {
            background-color: #2d2d2d;
            padding: 25px;
            border-radius: 10px;
            margin-top: 30px;
            border-left: 4px solid #FFD700;
        }
        .info-box h3 {
            color: #FFD700;
            margin-top: 0;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 Divergence Detection System</h1>
        <div class="description">
            <p>Detect bullish and bearish divergences across multiple indicators</p>
            <p>RSI • MACD • Stochastic • Volume (OBV) • Regular & Hidden Divergences</p>
        </div>

        <div class="endpoint-grid">
            <div class="endpoint-card">
                <h3>📊 Scan for Divergences</h3>
                <p>Get JSON data with all detected divergences</p>
                <div class="example">
                    <a href="/api/divergence/scan/AAPL?period=3mo&min_strength=60" target="_blank">
                        /api/divergence/scan/AAPL
                    </a>
                </div>
            </div>

            <div class="endpoint-card">
                <h3>📈 Divergence Chart</h3>
                <p>Interactive price chart with divergence overlays</p>
                <div class="example">
                    <a href="/api/divergence/chart/AAPL?period=3mo" target="_blank">
                        /api/divergence/chart/AAPL
                    </a>
                </div>
            </div>

            <div class="endpoint-card">
                <h3>🎛️ Full Dashboard</h3>
                <p>Comprehensive dashboard with all divergence analysis</p>
                <div class="example">
                    <a href="/api/divergence/dashboard/AAPL?period=3mo" target="_blank">
                        /api/divergence/dashboard/AAPL
                    </a>
                </div>
            </div>
        </div>

        <div class="info-box">
            <h3>📚 Divergence Types</h3>
            <ul>
                <li><strong>Regular Bullish:</strong> Price makes lower low, indicator makes higher low → Potential reversal UP</li>
                <li><strong>Regular Bearish:</strong> Price makes higher high, indicator makes lower high → Potential reversal DOWN</li>
                <li><strong>Hidden Bullish:</strong> Price makes higher low, indicator makes lower low → Trend continuation UP</li>
                <li><strong>Hidden Bearish:</strong> Price makes lower high, indicator makes higher high → Trend continuation DOWN</li>
            </ul>
        </div>

        <div class="info-box" style="border-left-color: #26a69a;">
            <h3>⚙️ Parameters</h3>
            <ul>
                <li><code>period</code>: 1d, 5d, 1mo, 3mo, 6mo, 1y (default: 3mo)</li>
                <li><code>timeframe</code>: 1m, 5m, 15m, 1h, 1d (default: 1d)</li>
                <li><code>min_strength</code>: 0-100 (default: 60)</li>
            </ul>
        </div>

        <div class="info-box" style="border-left-color: #64b5f6;">
            <h3>💡 Trading Tips</h3>
            <ul>
                <li>Volume divergences (OBV) are particularly powerful and receive bonus strength</li>
                <li>Regular divergences signal potential trend reversals</li>
                <li>Hidden divergences suggest trend continuation</li>
                <li>Higher strength scores (75+) indicate more reliable signals</li>
                <li>Combine with ICT concepts (FVG, Order Blocks) for best results</li>
            </ul>
        </div>
    </div>
</body>
</html>
    """
    return HTMLResponse(content=html)
