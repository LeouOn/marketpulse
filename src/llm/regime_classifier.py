"""
Market Regime Classifier

Use LLM to classify current market conditions and provide
adaptive trading recommendations.

Regimes:
- TRENDING_BULLISH: Strong uptrend, favor longs
- TRENDING_BEARISH: Strong downtrend, favor shorts
- RANGE_BOUND: Choppy, trade both directions
- CHOPPY_AVOID: High volatility, low follow-through
- BREAKOUT_PENDING: Coiling, wait for direction
"""

import asyncio
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
from loguru import logger

try:
    from src.llm.llm_client import LMStudioClient
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False
    logger.warning("LLM client not available - regime classification disabled")


@dataclass
class MarketData:
    """Current market data for regime classification"""
    # Price action
    symbol: str
    current_price: float
    range_points: float
    volume: int
    avg_volume: int

    # Volatility
    vix: float
    vix_percentile: float
    atr: float

    # Correlations
    nq_spy_corr: float
    nq_btc_corr: Optional[float] = None

    # Session
    session: str = "US Regular"  # London, NY Open, NY Close, After Hours

    # Trend
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    ema_21: Optional[float] = None

    # Additional context
    recent_high: Optional[float] = None
    recent_low: Optional[float] = None
    timestamp: datetime = None


@dataclass
class RegimeAnalysis:
    """Market regime classification result"""
    # Classification
    regime: str  # TRENDING_BULLISH, TRENDING_BEARISH, etc.
    confidence: float  # 0-100%

    # Trading recommendations
    recommended_bias: str  # long, short, neutral, avoid
    optimal_strategy: str  # Description of best approach

    # Key levels
    key_support: Optional[float] = None
    key_resistance: Optional[float] = None

    # Reasoning
    reasoning: str = ""
    risk_factors: list = None
    opportunities: list = None

    # Timestamp
    timestamp: datetime = None

    def __post_init__(self):
        if self.risk_factors is None:
            self.risk_factors = []
        if self.opportunities is None:
            self.opportunities = []
        if self.timestamp is None:
            self.timestamp = datetime.now()


class MarketRegimeClassifier:
    """
    Classify market regime using LLM analysis

    Uses AI to analyze:
    - Price action and trends
    - Volatility levels
    - Volume characteristics
    - Correlations
    - Session timing
    - News sentiment (future)
    """

    def __init__(self, use_anthropic: bool = False):
        """
        Initialize regime classifier

        Args:
            use_anthropic: Use Anthropic Claude instead of local LLM
        """
        self.use_anthropic = use_anthropic

        if not LLM_AVAILABLE and not use_anthropic:
            logger.warning("LLM not available - using rule-based classification")

    async def classify_regime(self, market_data: MarketData) -> RegimeAnalysis:
        """
        Classify current market regime

        Args:
            market_data: Current market data

        Returns:
            Regime analysis with recommendations
        """
        logger.info(f"Classifying market regime for {market_data.symbol}")

        # Try LLM classification first
        if LLM_AVAILABLE or self.use_anthropic:
            try:
                return await self._classify_with_llm(market_data)
            except Exception as e:
                logger.error(f"LLM classification failed: {e}")
                logger.info("Falling back to rule-based classification")

        # Fallback to rule-based
        return self._classify_with_rules(market_data)

    async def _classify_with_llm(self, market_data: MarketData) -> RegimeAnalysis:
        """Classify using LLM (Claude or local)"""

        # Build comprehensive prompt
        prompt = self._build_classification_prompt(market_data)

        if self.use_anthropic:
            # Use Anthropic Claude (via AI analyst if available)
            try:
                from src.ai.massive_analyst import MassiveAIAnalyst
                analyst = MassiveAIAnalyst()
                await analyst.create_agent()

                response = await analyst.query(prompt, include_technical_analysis=False)

                return self._parse_llm_response(response, market_data)

            except Exception as e:
                logger.error(f"Anthropic classification error: {e}")
                raise

        else:
            # Use local LM Studio
            if not LLM_AVAILABLE:
                raise RuntimeError("LLM client not available")

            async with LMStudioClient() as client:
                response = await client.generate_completion(
                    model='quick_analysis',
                    messages=[{'role': 'user', 'content': prompt}],
                    max_tokens=400,
                    temperature=0.3  # Lower temperature for classification
                )

                if response and 'choices' in response:
                    response_text = response['choices'][0]['message']['content']
                    return self._parse_llm_response(response_text, market_data)

            raise RuntimeError("LLM response empty")

    def _build_classification_prompt(self, market_data: MarketData) -> str:
        """Build prompt for LLM classification"""

        prompt = f"""Analyze the current {market_data.symbol} market regime and provide classification.

**Current Market Data:**

Price Action (Last 4 hours):
- Current Price: ${market_data.current_price:.2f}
- Range: {market_data.range_points:.1f} points
- Volume: {market_data.volume:,} vs Average: {market_data.avg_volume:,}
- Volume Ratio: {market_data.volume / market_data.avg_volume:.2f}x

Volatility Metrics:
- VIX: {market_data.vix:.2f} ({market_data.vix_percentile:.0f}th percentile)
- ATR(14): {market_data.atr:.2f}

Trend Indicators:
- SMA(20): ${market_data.sma_20:.2f if market_data.sma_20 else 'N/A'}
- SMA(50): ${market_data.sma_50:.2f if market_data.sma_50 else 'N/A'}
- EMA(21): ${market_data.ema_21:.2f if market_data.ema_21 else 'N/A'}
- Price vs SMA(20): {'Above' if market_data.sma_20 and market_data.current_price > market_data.sma_20 else 'Below'}

Correlations:
- {market_data.symbol} vs SPY: {market_data.nq_spy_corr:.2f}
- {market_data.symbol} vs BTC: {market_data.nq_btc_corr:.2f if market_data.nq_btc_corr else 'N/A'}

Session: {market_data.session}

**Your Task:**
Classify the market regime as ONE of the following:

1. **TRENDING_BULLISH** - Strong uptrend, high follow-through
   - Favor FVG longs, avoid shorts
   - Ride the trend, wide stops

2. **TRENDING_BEARISH** - Strong downtrend, consistent selling
   - Favor FVG shorts, avoid longs
   - Ride the trend down, wide stops

3. **RANGE_BOUND** - Consolidating, mean-reverting
   - Trade both directions
   - Fade extremes, tight stops
   - Look for range breaks

4. **CHOPPY_AVOID** - High volatility, low follow-through
   - Many false breakouts
   - Whipsaws common
   - Avoid trading or reduce size

5. **BREAKOUT_PENDING** - Coiling/compressing
   - Low volatility
   - Awaiting catalyst
   - Wait for direction, then trade breakout

**Provide:**
1. Regime classification (choose ONE from above)
2. Confidence level (0-100%)
3. Recommended bias: long, short, neutral, or avoid
4. Optimal strategy for this regime
5. Key support/resistance levels
6. Main risks
7. Main opportunities

Be concise but specific. Focus on actionable insights."""

        return prompt

    def _parse_llm_response(self, response: str, market_data: MarketData) -> RegimeAnalysis:
        """Parse LLM response into RegimeAnalysis"""

        response_lower = response.lower()

        # Extract regime
        regime = "RANGE_BOUND"  # Default
        if "trending_bullish" in response_lower or "trending bullish" in response_lower:
            regime = "TRENDING_BULLISH"
        elif "trending_bearish" in response_lower or "trending bearish" in response_lower:
            regime = "TRENDING_BEARISH"
        elif "choppy_avoid" in response_lower or "choppy avoid" in response_lower:
            regime = "CHOPPY_AVOID"
        elif "breakout_pending" in response_lower or "breakout pending" in response_lower:
            regime = "BREAKOUT_PENDING"

        # Extract confidence
        confidence = 75.0  # Default
        import re
        conf_match = re.search(r'confidence[:\s]+(\d+)%?', response_lower)
        if conf_match:
            confidence = float(conf_match.group(1))

        # Extract bias
        bias = "neutral"
        if "bias: long" in response_lower or "favor long" in response_lower:
            bias = "long"
        elif "bias: short" in response_lower or "favor short" in response_lower:
            bias = "short"
        elif "avoid" in response_lower:
            bias = "avoid"

        # Extract strategy (first sentence after "strategy" or "optimal")
        strategy = "Trade according to regime"
        strategy_match = re.search(r'(?:optimal strategy|strategy)[:\s]+([^.]+)', response_lower)
        if strategy_match:
            strategy = strategy_match.group(1).strip()

        return RegimeAnalysis(
            regime=regime,
            confidence=confidence,
            recommended_bias=bias,
            optimal_strategy=strategy,
            key_support=market_data.recent_low,
            key_resistance=market_data.recent_high,
            reasoning=response,
            timestamp=datetime.now()
        )

    def _classify_with_rules(self, market_data: MarketData) -> RegimeAnalysis:
        """
        Rule-based classification (fallback)

        Uses technical indicators and volatility to classify regime
        """
        logger.info("Using rule-based regime classification")

        # Check trend
        if market_data.sma_20 and market_data.sma_50:
            # Strong uptrend
            if (market_data.current_price > market_data.sma_20 > market_data.sma_50 and
                market_data.vix < 20):
                return RegimeAnalysis(
                    regime="TRENDING_BULLISH",
                    confidence=80.0,
                    recommended_bias="long",
                    optimal_strategy="Favor FVG longs, avoid shorts. Use wider stops.",
                    key_support=market_data.sma_20,
                    key_resistance=market_data.recent_high,
                    reasoning="Price > SMA20 > SMA50, low VIX, clear uptrend"
                )

            # Strong downtrend
            elif (market_data.current_price < market_data.sma_20 < market_data.sma_50 and
                  market_data.vix < 25):
                return RegimeAnalysis(
                    regime="TRENDING_BEARISH",
                    confidence=80.0,
                    recommended_bias="short",
                    optimal_strategy="Favor FVG shorts, avoid longs. Use wider stops.",
                    key_support=market_data.recent_low,
                    key_resistance=market_data.sma_20,
                    reasoning="Price < SMA20 < SMA50, clear downtrend"
                )

        # Check volatility
        if market_data.vix > 30 or market_data.atr > market_data.current_price * 0.03:
            return RegimeAnalysis(
                regime="CHOPPY_AVOID",
                confidence=75.0,
                recommended_bias="avoid",
                optimal_strategy="Reduce size or avoid trading. High volatility, likely whipsaws.",
                reasoning="VIX > 30 or ATR > 3%, high volatility environment"
            )

        # Check for coiling (low volatility)
        if market_data.vix < 15 and market_data.atr < market_data.current_price * 0.015:
            return RegimeAnalysis(
                regime="BREAKOUT_PENDING",
                confidence=70.0,
                recommended_bias="neutral",
                optimal_strategy="Wait for direction, then trade breakout. Coiling pattern.",
                reasoning="Low VIX and ATR, market compressing"
            )

        # Default to range-bound
        return RegimeAnalysis(
            regime="RANGE_BOUND",
            confidence=65.0,
            recommended_bias="neutral",
            optimal_strategy="Trade both directions, fade extremes. Use tight stops.",
            key_support=market_data.recent_low,
            key_resistance=market_data.recent_high,
            reasoning="Mixed signals, range-bound market"
        )


async def classify_current_regime(symbol: str = "NQ") -> RegimeAnalysis:
    """
    Classify current market regime (convenience function)

    Args:
        symbol: Symbol to analyze

    Returns:
        Regime analysis
    """
    # Get current market data
    from src.api.yahoo_client import YahooFinanceClient
    client = YahooFinanceClient()

    df = client.get_historical_data(symbol, period='1d', interval='5m')

    if df.empty:
        raise ValueError(f"No data available for {symbol}")

    # Calculate metrics
    current_price = float(df['close'].iloc[-1])
    recent_high = float(df['high'].iloc[-50:].max())
    recent_low = float(df['low'].iloc[-50:].min())
    range_points = recent_high - recent_low

    # Volume
    volume = int(df['volume'].iloc[-1])
    avg_volume = int(df['volume'].mean())

    # Get VIX
    vix_df = client.get_historical_data('^VIX', period='1d', interval='1d')
    vix = float(vix_df['close'].iloc[-1]) if not vix_df.empty else 20.0

    # Calculate indicators
    from src.analysis.technical_indicators import TechnicalIndicators
    df_with_ind = TechnicalIndicators.calculate_all(df, ['sma_20', 'sma_50', 'ema_21', 'atr'])

    sma_20 = float(df_with_ind['sma_20'].iloc[-1])
    sma_50 = float(df_with_ind['sma_50'].iloc[-1])
    ema_21 = float(df_with_ind['ema_21'].iloc[-1])
    atr = float(df_with_ind['atr'].iloc[-1])

    # Correlation with SPY
    spy_df = client.get_historical_data('SPY', period='1d', interval='5m')
    if not spy_df.empty:
        nq_returns = df['close'].pct_change().dropna()
        spy_returns = spy_df['close'].pct_change().dropna()
        # Align indices
        common_index = nq_returns.index.intersection(spy_returns.index)
        if len(common_index) > 10:
            correlation = nq_returns.loc[common_index].corr(spy_returns.loc[common_index])
        else:
            correlation = 0.8  # Default
    else:
        correlation = 0.8

    # Build market data
    market_data = MarketData(
        symbol=symbol,
        current_price=current_price,
        range_points=range_points,
        volume=volume,
        avg_volume=avg_volume,
        vix=vix,
        vix_percentile=50.0,  # Simplified
        atr=atr,
        nq_spy_corr=correlation,
        session="US Regular",
        sma_20=sma_20,
        sma_50=sma_50,
        ema_21=ema_21,
        recent_high=recent_high,
        recent_low=recent_low,
        timestamp=datetime.now()
    )

    # Classify
    classifier = MarketRegimeClassifier()
    return await classifier.classify_regime(market_data)
