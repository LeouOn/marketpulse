"""Multi-Leg Options Strategy Analyzers

This module provides analysis for multi-leg options strategies including
covered calls, bull call spreads, bear put spreads, and other common strategies.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from datetime import datetime
from loguru import logger

from .options_analyzer import OptionsAnalyzer, SingleLegAnalysis


@dataclass
class CoveredCallAnalysis:
    """Analysis results for covered call strategy"""
    symbol: str
    shares_owned: int
    stock_price: float

    # Short call details
    strike: float
    expiration: str
    premium_received: float
    contracts: int

    # Strategy metrics
    total_premium: float  # Premium * 100 * contracts
    cost_basis_reduction: float  # Per share
    downside_protection: float  # Percentage
    upside_cap: float  # Stock price at which max profit occurs

    # Return calculations
    max_profit: float  # If stock at or above strike at expiration
    max_loss: float  # If stock goes to zero (covered, so loss on stock minus premium)
    breakeven: float  # Stock price breakeven
    return_if_called: float  # Percentage return if stock called away
    annualized_return: float  # Annualized percentage return

    # Greeks (for the short call)
    delta: float
    theta: float  # Daily theta - positive for covered call

    # Time metrics
    days_to_expiration: int

    # Risk assessment
    probability_max_profit: float  # Probability stock above strike


@dataclass
class SpreadAnalysis:
    """Analysis results for vertical spread strategies"""
    symbol: str
    spread_type: str  # 'bull_call', 'bear_put', 'bull_put', 'bear_call'

    # Leg details
    long_strike: float
    short_strike: float
    expiration: str
    contracts: int

    # Pricing
    long_premium: float
    short_premium: float
    net_debit: float  # Or credit if negative
    total_cost: float  # Net debit/credit * 100 * contracts

    # Risk metrics
    max_profit: float
    max_loss: float
    breakeven: float
    risk_reward_ratio: float

    # Return metrics
    max_return_pct: float  # Max profit as % of risk
    probability_profit: float

    # Greeks (net position)
    net_delta: float
    net_theta: float
    net_vega: float

    # Time metrics
    days_to_expiration: int

    # Width
    spread_width: float


class StrategyBuilder:
    """Builder for multi-leg options strategies"""

    def __init__(self, yahoo_client):
        """Initialize strategy builder

        Args:
            yahoo_client: Instance of YahooFinanceClient
        """
        self.yahoo_client = yahoo_client
        self.analyzer = OptionsAnalyzer(yahoo_client)

    def analyze_covered_call(
        self,
        symbol: str,
        shares_owned: int,
        strike: float,
        expiration: str,
        contracts: Optional[int] = None
    ) -> Optional[CoveredCallAnalysis]:
        """Analyze a covered call strategy

        Args:
            symbol: Stock symbol
            shares_owned: Number of shares owned
            strike: Strike price of call to sell
            expiration: Expiration date
            contracts: Number of contracts (if None, calculated from shares_owned)

        Returns:
            CoveredCallAnalysis or None if analysis fails
        """
        try:
            # Calculate contracts if not provided
            if contracts is None:
                contracts = shares_owned // 100

            if contracts == 0:
                logger.error("Need at least 100 shares to write covered call")
                return None

            # Analyze the short call
            call_analysis = self.analyzer.analyze_single_leg(
                symbol=symbol,
                strike=strike,
                expiration=expiration,
                option_type='call',
                position_type='short',  # We're selling the call
                contracts=contracts
            )

            if not call_analysis:
                return None

            stock_price = call_analysis.underlying_price

            # Calculate strategy metrics
            premium_per_share = call_analysis.market_price
            total_premium = call_analysis.cost_basis  # This is positive for short positions

            # Downside protection
            cost_basis_reduction = premium_per_share
            downside_protection_pct = (premium_per_share / stock_price) * 100

            # Upside cap
            upside_cap = strike

            # Max profit: premium + (strike - current price) if stock > strike
            # If stock called away, we get strike price + premium
            capital_gain = (strike - stock_price) * shares_owned if strike > stock_price else 0
            max_profit = total_premium + capital_gain

            # Max loss: if stock goes to zero, we lose stock value minus premium
            max_loss = (stock_price * shares_owned) - total_premium

            # Breakeven: current stock price - premium received
            breakeven = stock_price - premium_per_share

            # Return if called
            if stock_price > 0:
                return_if_called = ((strike - stock_price + premium_per_share) / stock_price) * 100
            else:
                return_if_called = 0

            # Annualized return
            days = call_analysis.days_to_expiration
            if days > 0:
                annualized_return = return_if_called * (365 / days)
            else:
                annualized_return = 0

            # Probability stock above strike (using delta as proxy)
            # For short call, delta is negative, but represents prob ITM
            probability_max_profit = abs(call_analysis.greeks.delta) * 100

            return CoveredCallAnalysis(
                symbol=symbol,
                shares_owned=shares_owned,
                stock_price=stock_price,
                strike=strike,
                expiration=expiration,
                premium_received=premium_per_share,
                contracts=contracts,
                total_premium=total_premium,
                cost_basis_reduction=round(cost_basis_reduction, 2),
                downside_protection=round(downside_protection_pct, 2),
                upside_cap=upside_cap,
                max_profit=round(max_profit, 2),
                max_loss=round(max_loss, 2),
                breakeven=round(breakeven, 2),
                return_if_called=round(return_if_called, 2),
                annualized_return=round(annualized_return, 2),
                delta=call_analysis.greeks.delta,
                theta=call_analysis.greeks.theta,
                days_to_expiration=call_analysis.days_to_expiration,
                probability_max_profit=round(probability_max_profit, 1)
            )

        except Exception as e:
            logger.error(f"Error analyzing covered call: {e}")
            return None

    def analyze_bull_call_spread(
        self,
        symbol: str,
        long_strike: float,
        short_strike: float,
        expiration: str,
        contracts: int = 1
    ) -> Optional[SpreadAnalysis]:
        """Analyze a bull call spread

        Args:
            symbol: Stock symbol
            long_strike: Strike of call to buy (lower strike)
            short_strike: Strike of call to sell (higher strike)
            expiration: Expiration date
            contracts: Number of contracts

        Returns:
            SpreadAnalysis or None if analysis fails
        """
        try:
            if long_strike >= short_strike:
                logger.error("For bull call spread, long strike must be < short strike")
                return None

            # Analyze long call
            long_call = self.analyzer.analyze_single_leg(
                symbol=symbol,
                strike=long_strike,
                expiration=expiration,
                option_type='call',
                position_type='long',
                contracts=contracts
            )

            # Analyze short call
            short_call = self.analyzer.analyze_single_leg(
                symbol=symbol,
                strike=short_strike,
                expiration=expiration,
                option_type='call',
                position_type='short',
                contracts=contracts
            )

            if not long_call or not short_call:
                return None

            # Calculate spread metrics
            spread_width = short_strike - long_strike
            net_debit = long_call.market_price - short_call.market_price
            total_cost = abs(long_call.cost_basis + short_call.cost_basis)

            # Max profit: spread width - net debit (per share)
            max_profit_per_share = spread_width - net_debit
            max_profit = max_profit_per_share * 100 * contracts

            # Max loss: net debit paid
            max_loss = total_cost

            # Breakeven: long strike + net debit
            breakeven = long_strike + net_debit

            # Risk/reward
            risk_reward_ratio = max_profit / max_loss if max_loss > 0 else 0

            # Return as percentage of risk
            max_return_pct = (max_profit / max_loss * 100) if max_loss > 0 else 0

            # Net Greeks
            net_delta = long_call.greeks.delta + short_call.greeks.delta
            net_theta = long_call.greeks.theta + short_call.greeks.theta
            net_vega = long_call.greeks.vega + short_call.greeks.vega

            # Probability of profit (approximate using net delta)
            # For bull call spread, we profit if stock > breakeven
            # Use long call delta as approximation
            probability_profit = abs(long_call.greeks.delta) * 100

            return SpreadAnalysis(
                symbol=symbol,
                spread_type='bull_call',
                long_strike=long_strike,
                short_strike=short_strike,
                expiration=expiration,
                contracts=contracts,
                long_premium=long_call.market_price,
                short_premium=short_call.market_price,
                net_debit=round(net_debit, 2),
                total_cost=round(total_cost, 2),
                max_profit=round(max_profit, 2),
                max_loss=round(max_loss, 2),
                breakeven=round(breakeven, 2),
                risk_reward_ratio=round(risk_reward_ratio, 2),
                max_return_pct=round(max_return_pct, 1),
                probability_profit=round(probability_profit, 1),
                net_delta=round(net_delta, 4),
                net_theta=round(net_theta, 4),
                net_vega=round(net_vega, 4),
                days_to_expiration=long_call.days_to_expiration,
                spread_width=spread_width
            )

        except Exception as e:
            logger.error(f"Error analyzing bull call spread: {e}")
            return None

    def analyze_bear_put_spread(
        self,
        symbol: str,
        long_strike: float,
        short_strike: float,
        expiration: str,
        contracts: int = 1
    ) -> Optional[SpreadAnalysis]:
        """Analyze a bear put spread

        Args:
            symbol: Stock symbol
            long_strike: Strike of put to buy (higher strike)
            short_strike: Strike of put to sell (lower strike)
            expiration: Expiration date
            contracts: Number of contracts

        Returns:
            SpreadAnalysis or None if analysis fails
        """
        try:
            if long_strike <= short_strike:
                logger.error("For bear put spread, long strike must be > short strike")
                return None

            # Analyze long put
            long_put = self.analyzer.analyze_single_leg(
                symbol=symbol,
                strike=long_strike,
                expiration=expiration,
                option_type='put',
                position_type='long',
                contracts=contracts
            )

            # Analyze short put
            short_put = self.analyzer.analyze_single_leg(
                symbol=symbol,
                strike=short_strike,
                expiration=expiration,
                option_type='put',
                position_type='short',
                contracts=contracts
            )

            if not long_put or not short_put:
                return None

            # Calculate spread metrics
            spread_width = long_strike - short_strike
            net_debit = long_put.market_price - short_put.market_price
            total_cost = abs(long_put.cost_basis + short_put.cost_basis)

            # Max profit: spread width - net debit
            max_profit_per_share = spread_width - net_debit
            max_profit = max_profit_per_share * 100 * contracts

            # Max loss: net debit paid
            max_loss = total_cost

            # Breakeven: long strike - net debit
            breakeven = long_strike - net_debit

            # Risk/reward
            risk_reward_ratio = max_profit / max_loss if max_loss > 0 else 0

            # Return as percentage of risk
            max_return_pct = (max_profit / max_loss * 100) if max_loss > 0 else 0

            # Net Greeks
            net_delta = long_put.greeks.delta + short_put.greeks.delta
            net_theta = long_put.greeks.theta + short_put.greeks.theta
            net_vega = long_put.greeks.vega + short_put.greeks.vega

            # Probability of profit (approximate using net delta)
            probability_profit = abs(long_put.greeks.delta) * 100

            return SpreadAnalysis(
                symbol=symbol,
                spread_type='bear_put',
                long_strike=long_strike,
                short_strike=short_strike,
                expiration=expiration,
                contracts=contracts,
                long_premium=long_put.market_price,
                short_premium=short_put.market_price,
                net_debit=round(net_debit, 2),
                total_cost=round(total_cost, 2),
                max_profit=round(max_profit, 2),
                max_loss=round(max_loss, 2),
                breakeven=round(breakeven, 2),
                risk_reward_ratio=round(risk_reward_ratio, 2),
                max_return_pct=round(max_return_pct, 1),
                probability_profit=round(probability_profit, 1),
                net_delta=round(net_delta, 4),
                net_theta=round(net_theta, 4),
                net_vega=round(net_vega, 4),
                days_to_expiration=long_put.days_to_expiration,
                spread_width=spread_width
            )

        except Exception as e:
            logger.error(f"Error analyzing bear put spread: {e}")
            return None

    def generate_strategy_comparison(
        self,
        symbol: str,
        expiration: str
    ) -> Dict[str, Any]:
        """Generate comparison of multiple strategies for a symbol

        Args:
            symbol: Stock symbol
            expiration: Expiration date to analyze

        Returns:
            Dictionary with strategy comparisons
        """
        try:
            # Get current stock price
            stock_data = self.yahoo_client.get_single_symbol_data(symbol)
            if not stock_data:
                return {'error': 'Could not fetch stock data'}

            stock_price = stock_data['price']

            # Get options chain
            chain = self.yahoo_client.get_options_chain(symbol, expiration)
            if 'error' in chain:
                return {'error': chain['error']}

            strategies = []

            # Example covered call (ATM)
            atm_strike_call = min(
                [c['strike'] for c in chain['calls']],
                key=lambda x: abs(x - stock_price)
            )

            # Example bull call spread (OTM)
            otm_calls = [c['strike'] for c in chain['calls'] if c['strike'] > stock_price]
            if len(otm_calls) >= 2:
                otm_calls.sort()
                bull_spread = {
                    'type': 'bull_call_spread',
                    'long_strike': otm_calls[0],
                    'short_strike': otm_calls[1]
                }
                strategies.append(bull_spread)

            return {
                'symbol': symbol,
                'stock_price': stock_price,
                'expiration': expiration,
                'strategies': strategies,
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error generating strategy comparison: {e}")
            return {'error': str(e)}
