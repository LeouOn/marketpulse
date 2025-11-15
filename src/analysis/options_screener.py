"""Intelligent Options Screener with Macro Context

This module provides advanced options screening with macro context awareness,
filtering options opportunities based on market regime and volatility conditions.
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Literal
from datetime import datetime, date, timedelta
from loguru import logger

from .options_analyzer import OptionsAnalyzer, SingleLegAnalysis
from .macro_context import MacroRegime


@dataclass
class OptionOpportunity:
    """Represents a screened options opportunity"""
    symbol: str
    strike: float
    expiration: str
    option_type: Literal["call", "put"]
    underlying_price: float

    # Pricing
    market_price: float
    bid: float
    ask: float
    implied_volatility: float

    # Greeks
    delta: float
    gamma: float
    theta: float
    vega: float

    # Risk metrics
    breakeven: float
    probability_profit: float

    # Liquidity
    volume: int
    open_interest: int

    # Time
    days_to_expiration: int

    # Scoring
    score: float  # Overall opportunity score
    score_components: Dict[str, float]


class OptionsScreener:
    """Advanced options screener with macro awareness"""

    def __init__(self, yahoo_client):
        """Initialize screener

        Args:
            yahoo_client: Instance of YahooFinanceClient
        """
        self.yahoo_client = yahoo_client
        self.analyzer = OptionsAnalyzer(yahoo_client)
        self.macro_regime = MacroRegime(yahoo_client)

    def screen_otm_calls(
        self,
        symbols: List[str],
        min_delta: float = 0.20,
        max_delta: float = 0.45,
        min_days_to_expiry: int = 14,
        max_days_to_expiry: int = 60,
        min_volume: int = 100,
        min_open_interest: int = 100,
        use_macro_filter: bool = True
    ) -> List[OptionOpportunity]:
        """Screen for out-of-the-money call opportunities

        Args:
            symbols: List of symbols to screen
            min_delta: Minimum delta (e.g., 0.20 for ~20% OTM)
            max_delta: Maximum delta (e.g., 0.45 for slightly OTM)
            min_days_to_expiry: Minimum days to expiration
            max_days_to_expiry: Maximum days to expiration
            min_volume: Minimum volume filter
            min_open_interest: Minimum open interest filter
            use_macro_filter: Whether to apply macro regime filters

        Returns:
            List of OptionOpportunity objects, sorted by score
        """
        opportunities = []

        # Get macro context if using macro filter
        macro_context = None
        if use_macro_filter:
            macro_context = self.macro_regime.get_comprehensive_context()
            logger.info(f"Macro context: VIX {macro_context.get('vix', {}).get('current_level')}, "
                       f"Regime: {macro_context.get('volatility_regime', {}).get('regime')}")

        # Filter date range
        today = date.today()
        min_date = today + timedelta(days=min_days_to_expiry)
        max_date = today + timedelta(days=max_days_to_expiry)

        for symbol in symbols:
            try:
                # Get options expirations
                expirations = self.yahoo_client.get_options_expirations(symbol)

                # Filter by date range
                valid_expirations = [
                    exp for exp in expirations
                    if min_date <= datetime.strptime(exp, '%Y-%m-%d').date() <= max_date
                ]

                # Screen each expiration (limit to first 3 for performance)
                for expiration in valid_expirations[:3]:
                    chain_data = self.yahoo_client.get_options_chain(symbol, expiration)

                    if 'error' in chain_data or not chain_data['underlying_price']:
                        continue

                    # Analyze calls
                    for call in chain_data['calls']:
                        # Apply volume and OI filters
                        if call.get('volume', 0) < min_volume:
                            continue
                        if call.get('openInterest', 0) < min_open_interest:
                            continue

                        # Analyze this option
                        analysis = self.analyzer.analyze_single_leg(
                            symbol=symbol,
                            strike=call['strike'],
                            expiration=expiration,
                            option_type='call',
                            position_type='long',
                            contracts=1
                        )

                        if not analysis:
                            continue

                        # Apply delta filter
                        if not (min_delta <= abs(analysis.greeks.delta) <= max_delta):
                            continue

                        # Score the opportunity
                        score_components = self._score_opportunity(
                            analysis=analysis,
                            macro_context=macro_context,
                            strategy_type='long_call'
                        )

                        total_score = sum(score_components.values())

                        # Create opportunity
                        opp = OptionOpportunity(
                            symbol=symbol,
                            strike=analysis.strike,
                            expiration=expiration,
                            option_type='call',
                            underlying_price=analysis.underlying_price,
                            market_price=analysis.market_price,
                            bid=analysis.bid,
                            ask=analysis.ask,
                            implied_volatility=analysis.implied_volatility,
                            delta=analysis.greeks.delta,
                            gamma=analysis.greeks.gamma,
                            theta=analysis.greeks.theta,
                            vega=analysis.greeks.vega,
                            breakeven=analysis.breakeven,
                            probability_profit=analysis.probability_profit,
                            volume=call.get('volume', 0),
                            open_interest=call.get('openInterest', 0),
                            days_to_expiration=analysis.days_to_expiration,
                            score=total_score,
                            score_components=score_components
                        )

                        opportunities.append(opp)

            except Exception as e:
                logger.warning(f"Error screening {symbol}: {e}")
                continue

        # Sort by score
        opportunities.sort(key=lambda x: x.score, reverse=True)

        logger.info(f"Found {len(opportunities)} OTM call opportunities")
        return opportunities

    def screen_with_macro_filter(
        self,
        symbols: List[str],
        strategy_preference: Optional[Literal["directional", "premium_selling", "neutral"]] = None
    ) -> List[OptionOpportunity]:
        """Screen for opportunities with intelligent macro-based filtering

        Args:
            symbols: List of symbols to screen
            strategy_preference: Preferred strategy type (if None, auto-selects based on regime)

        Returns:
            List of opportunities tailored to current market regime
        """
        # Get macro context
        macro_context = self.macro_regime.get_comprehensive_context()
        regime = macro_context.get('volatility_regime', {}).get('regime', 'normal')
        vix_level = macro_context.get('vix', {}).get('current_level', 20)

        logger.info(f"Screening with macro filter - Regime: {regime}, VIX: {vix_level}")

        # Determine strategy based on regime if not specified
        if strategy_preference is None:
            if regime == 'low_volatility':
                strategy_preference = 'premium_selling'
            elif regime == 'high_volatility':
                strategy_preference = 'directional'
            else:
                strategy_preference = 'neutral'

        # Adjust screening parameters based on regime and strategy
        if strategy_preference == 'premium_selling':
            # Look for options with good premium to sell
            return self.screen_otm_calls(
                symbols=symbols,
                min_delta=0.25,
                max_delta=0.40,
                min_days_to_expiry=21,
                max_days_to_expiry=45,
                min_volume=200,
                min_open_interest=200,
                use_macro_filter=True
            )
        elif strategy_preference == 'directional':
            # Look for directional plays with better probability
            return self.screen_otm_calls(
                symbols=symbols,
                min_delta=0.35,
                max_delta=0.55,
                min_days_to_expiry=14,
                max_days_to_expiry=45,
                min_volume=100,
                min_open_interest=100,
                use_macro_filter=True
            )
        else:  # neutral
            return self.screen_otm_calls(
                symbols=symbols,
                min_delta=0.20,
                max_delta=0.45,
                min_days_to_expiry=21,
                max_days_to_expiry=60,
                min_volume=150,
                min_open_interest=150,
                use_macro_filter=True
            )

    def _score_opportunity(
        self,
        analysis: SingleLegAnalysis,
        macro_context: Optional[Dict[str, Any]],
        strategy_type: str
    ) -> Dict[str, float]:
        """Score an options opportunity based on multiple factors

        Args:
            analysis: SingleLegAnalysis result
            macro_context: Macro market context
            strategy_type: Type of strategy ('long_call', 'long_put', etc.)

        Returns:
            Dictionary with score components
        """
        scores = {}

        # 1. Liquidity score (0-20 points)
        # Good liquidity is critical for getting fills
        volume = analysis.bid * 100  # Approximate volume from bid
        open_interest_proxy = abs(analysis.greeks.delta) * 1000

        liquidity_score = 0
        if volume > 500:
            liquidity_score += 10
        elif volume > 200:
            liquidity_score += 7
        elif volume > 100:
            liquidity_score += 5

        if open_interest_proxy > 1000:
            liquidity_score += 10
        elif open_interest_proxy > 500:
            liquidity_score += 7
        elif open_interest_proxy > 100:
            liquidity_score += 5

        scores['liquidity'] = liquidity_score

        # 2. Probability score (0-25 points)
        # Higher probability of profit is better
        prob_profit = analysis.probability_profit
        if prob_profit > 60:
            scores['probability'] = 25
        elif prob_profit > 50:
            scores['probability'] = 20
        elif prob_profit > 40:
            scores['probability'] = 15
        elif prob_profit > 30:
            scores['probability'] = 10
        else:
            scores['probability'] = 5

        # 3. Risk/Reward score (0-20 points)
        if analysis.risk_reward_ratio:
            rr = analysis.risk_reward_ratio
            if rr > 3:
                scores['risk_reward'] = 20
            elif rr > 2:
                scores['risk_reward'] = 15
            elif rr > 1.5:
                scores['risk_reward'] = 10
            elif rr > 1:
                scores['risk_reward'] = 5
            else:
                scores['risk_reward'] = 2
        else:
            scores['risk_reward'] = 10  # Neutral for undefined R/R

        # 4. Time value score (0-15 points)
        # Favor options with more time but not too much
        days = analysis.days_to_expiration
        if 30 <= days <= 45:
            scores['time_value'] = 15
        elif 21 <= days <= 60:
            scores['time_value'] = 12
        elif 14 <= days <= 21:
            scores['time_value'] = 8
        else:
            scores['time_value'] = 5

        # 5. Macro context score (0-20 points)
        if macro_context:
            regime = macro_context.get('volatility_regime', {}).get('regime', 'normal')
            vix_percentile = macro_context.get('vix', {}).get('percentile', 50)

            macro_score = 0

            # Adjust based on regime and strategy
            if strategy_type == 'long_call':
                if regime == 'low_volatility':
                    macro_score = 8  # Okay but not ideal
                elif regime == 'normal':
                    macro_score = 15  # Good conditions
                elif regime == 'elevated':
                    macro_score = 18  # Good for directional if timed right
                else:  # high_volatility
                    macro_score = 12  # Risky but can work

                # Adjust for VIX percentile
                if vix_percentile < 30:
                    macro_score += 5  # Low VIX is good for buying calls
                elif vix_percentile > 70:
                    macro_score -= 3  # High VIX means expensive options

            scores['macro_context'] = max(0, min(macro_score, 20))
        else:
            scores['macro_context'] = 10  # Neutral

        return scores

    def generate_screening_report(
        self,
        opportunities: List[OptionOpportunity],
        top_n: int = 10
    ) -> Dict[str, Any]:
        """Generate a formatted screening report

        Args:
            opportunities: List of opportunities
            top_n: Number of top opportunities to include in report

        Returns:
            Dictionary with formatted report data
        """
        if not opportunities:
            return {
                'total_opportunities': 0,
                'top_picks': [],
                'summary': 'No opportunities found matching criteria'
            }

        # Get top N
        top_picks = opportunities[:top_n]

        # Calculate summary statistics
        avg_score = sum(opp.score for opp in opportunities) / len(opportunities)
        avg_prob = sum(opp.probability_profit for opp in opportunities) / len(opportunities)
        avg_delta = sum(opp.delta for opp in opportunities) / len(opportunities)

        # Format top picks
        formatted_picks = []
        for opp in top_picks:
            formatted_picks.append({
                'symbol': opp.symbol,
                'strike': round(opp.strike, 2),
                'expiration': opp.expiration,
                'days_to_exp': opp.days_to_expiration,
                'underlying_price': round(opp.underlying_price, 2),
                'market_price': round(opp.market_price, 2),
                'delta': round(opp.delta, 3),
                'implied_volatility': round(opp.implied_volatility, 3),
                'breakeven': round(opp.breakeven, 2),
                'probability_profit': round(opp.probability_profit, 1),
                'score': round(opp.score, 1),
                'score_breakdown': {k: round(v, 1) for k, v in opp.score_components.items()}
            })

        return {
            'total_opportunities': len(opportunities),
            'top_picks': formatted_picks,
            'summary_stats': {
                'average_score': round(avg_score, 1),
                'average_probability': round(avg_prob, 1),
                'average_delta': round(avg_delta, 3)
            },
            'timestamp': datetime.now().isoformat()
        }
