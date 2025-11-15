"""Options Analyzer for Single and Multi-Leg Strategies

This module provides analysis capabilities for options strategies including
breakeven calculations, profit/loss scenarios, and probability analysis.
"""

from dataclasses import dataclass
from typing import Literal, Optional, Dict, Any
from datetime import datetime
from loguru import logger

from .options_pricing import BlackScholesCalculator, Greeks


@dataclass
class SingleLegAnalysis:
    """Analysis results for a single options leg"""
    symbol: str
    option_type: Literal["call", "put"]
    strike: float
    expiration: str
    underlying_price: float

    # Pricing
    theoretical_price: float
    market_price: float
    bid: float
    ask: float
    mid_price: float

    # Greeks
    greeks: Greeks

    # Implied Volatility
    implied_volatility: float

    # Position Analysis
    position_type: Literal["long", "short"]
    contracts: int
    cost_basis: float  # Total cost/credit for position

    # Risk Metrics
    breakeven: float
    max_profit: Optional[float]  # None if unlimited
    max_loss: Optional[float]    # None if unlimited
    risk_reward_ratio: Optional[float]

    # Probabilities (using delta as proxy)
    probability_profit: float  # Approximate using delta

    # Time metrics
    days_to_expiration: int
    theta_decay_per_day: float


class OptionsAnalyzer:
    """Analyzer for options strategies"""

    def __init__(self, yahoo_client):
        """Initialize with Yahoo Finance client

        Args:
            yahoo_client: Instance of YahooFinanceClient
        """
        self.yahoo_client = yahoo_client

    def analyze_single_leg(
        self,
        symbol: str,
        strike: float,
        expiration: str,
        option_type: Literal["call", "put"],
        position_type: Literal["long", "short"] = "long",
        contracts: int = 1,
        market_price: Optional[float] = None
    ) -> Optional[SingleLegAnalysis]:
        """Analyze a single options leg

        Args:
            symbol: Stock symbol (e.g., 'AAPL', 'SPY')
            strike: Strike price
            expiration: Expiration date 'YYYY-MM-DD'
            option_type: 'call' or 'put'
            position_type: 'long' or 'short'
            contracts: Number of contracts
            market_price: Market price (if None, will fetch from chain)

        Returns:
            SingleLegAnalysis or None if analysis fails
        """
        try:
            # Get options chain
            chain_data = self.yahoo_client.get_options_chain(symbol, expiration)

            if 'error' in chain_data or not chain_data['underlying_price']:
                logger.error(f"Failed to fetch options chain for {symbol}")
                return None

            underlying_price = chain_data['underlying_price']

            # Find the specific option in the chain
            options_list = chain_data['calls'] if option_type == 'call' else chain_data['puts']

            option_data = None
            for opt in options_list:
                if abs(opt['strike'] - strike) < 0.01:  # Match strike with small tolerance
                    option_data = opt
                    break

            if not option_data:
                logger.error(f"Option with strike {strike} not found in chain")
                return None

            # Extract market data
            bid = float(option_data.get('bid', 0))
            ask = float(option_data.get('ask', 0))
            last_price = float(option_data.get('lastPrice', 0))
            volume = int(option_data.get('volume', 0))
            open_interest = int(option_data.get('openInterest', 0))
            implied_vol = float(option_data.get('impliedVolatility', 0))

            # Calculate mid price
            mid_price = (bid + ask) / 2.0 if bid > 0 and ask > 0 else last_price

            # Use provided market price or mid price
            if market_price is None:
                market_price = mid_price

            # Get risk-free rate and dividend yield
            risk_free_rate = self.yahoo_client.get_risk_free_rate()
            dividend_yield = self.yahoo_client.get_dividend_yield(symbol)

            # Calculate time to expiration
            T = BlackScholesCalculator.days_to_expiration(expiration)
            days_to_exp = int(T * 365)

            # Calculate theoretical price and Greeks
            result = BlackScholesCalculator.calculate_option_with_greeks(
                S=underlying_price,
                K=strike,
                T=T,
                r=risk_free_rate,
                sigma=implied_vol,
                q=dividend_yield,
                option_type=option_type
            )

            theoretical_price = result.price
            greeks = result.greeks

            # Calculate position metrics
            # For long positions: pay premium (negative cash flow)
            # For short positions: receive premium (positive cash flow)
            multiplier = 100  # Options contracts are for 100 shares

            if position_type == "long":
                cost_basis = -market_price * contracts * multiplier
                theta_decay = greeks.theta * contracts * multiplier
            else:  # short
                cost_basis = market_price * contracts * multiplier
                theta_decay = -greeks.theta * contracts * multiplier  # Theta benefits short sellers

            # Calculate breakeven, max profit, max loss
            breakeven, max_profit, max_loss, risk_reward = self._calculate_risk_metrics(
                option_type=option_type,
                position_type=position_type,
                strike=strike,
                premium=market_price,
                contracts=contracts
            )

            # Calculate probability of profit (using delta as approximation)
            probability_profit = self._estimate_probability_profit(
                option_type=option_type,
                position_type=position_type,
                delta=greeks.delta
            )

            return SingleLegAnalysis(
                symbol=symbol,
                option_type=option_type,
                strike=strike,
                expiration=expiration,
                underlying_price=underlying_price,
                theoretical_price=theoretical_price,
                market_price=market_price,
                bid=bid,
                ask=ask,
                mid_price=mid_price,
                greeks=greeks,
                implied_volatility=implied_vol,
                position_type=position_type,
                contracts=contracts,
                cost_basis=cost_basis,
                breakeven=breakeven,
                max_profit=max_profit,
                max_loss=max_loss,
                risk_reward_ratio=risk_reward,
                probability_profit=probability_profit,
                days_to_expiration=days_to_exp,
                theta_decay_per_day=theta_decay
            )

        except Exception as e:
            logger.error(f"Error analyzing single leg: {e}")
            return None

    def _calculate_risk_metrics(
        self,
        option_type: Literal["call", "put"],
        position_type: Literal["long", "short"],
        strike: float,
        premium: float,
        contracts: int
    ) -> tuple[float, Optional[float], Optional[float], Optional[float]]:
        """Calculate breakeven, max profit, max loss, and risk/reward ratio

        Returns:
            Tuple of (breakeven, max_profit, max_loss, risk_reward_ratio)
        """
        multiplier = 100

        if option_type == "call":
            if position_type == "long":
                # Long Call
                breakeven = strike + premium
                max_profit = None  # Unlimited
                max_loss = premium * contracts * multiplier
                risk_reward = None  # Undefined (unlimited upside)
            else:
                # Short Call
                breakeven = strike + premium
                max_profit = premium * contracts * multiplier
                max_loss = None  # Unlimited
                risk_reward = None  # Undefined (unlimited downside)
        else:  # put
            if position_type == "long":
                # Long Put
                breakeven = strike - premium
                max_profit = (strike - premium) * contracts * multiplier  # If stock goes to 0
                max_loss = premium * contracts * multiplier
                risk_reward = max_profit / max_loss if max_loss > 0 else None
            else:
                # Short Put
                breakeven = strike - premium
                max_profit = premium * contracts * multiplier
                max_loss = (strike - premium) * contracts * multiplier  # If stock goes to 0
                risk_reward = max_profit / max_loss if max_loss > 0 else None

        return breakeven, max_profit, max_loss, risk_reward

    def _estimate_probability_profit(
        self,
        option_type: Literal["call", "put"],
        position_type: Literal["long", "short"],
        delta: float
    ) -> float:
        """Estimate probability of profit using delta as proxy

        Delta approximates the probability that option expires ITM.
        For long options, we need price to move beyond breakeven.
        """
        # Delta is approximate probability of expiring ITM
        # For simplicity, we use delta as rough estimate

        if option_type == "call":
            if position_type == "long":
                # Long call profits if price > breakeven
                # Delta gives prob of being ITM, which is close to our needs
                prob = abs(delta) * 100
            else:
                # Short call profits if price < breakeven
                prob = (1 - abs(delta)) * 100
        else:  # put
            if position_type == "long":
                # Long put profits if price < breakeven
                prob = abs(delta) * 100
            else:
                # Short put profits if price > breakeven
                prob = (1 - abs(delta)) * 100

        return min(max(prob, 0.0), 100.0)

    def calculate_pnl_at_price(
        self,
        analysis: SingleLegAnalysis,
        stock_price: float
    ) -> float:
        """Calculate P&L at a specific stock price at expiration

        Args:
            analysis: SingleLegAnalysis from analyze_single_leg
            stock_price: Stock price to evaluate

        Returns:
            P&L in dollars
        """
        multiplier = 100
        strike = analysis.strike
        premium = analysis.market_price
        contracts = analysis.contracts

        if analysis.option_type == "call":
            intrinsic_value = max(stock_price - strike, 0)
        else:  # put
            intrinsic_value = max(strike - stock_price, 0)

        if analysis.position_type == "long":
            # Long: pay premium, receive intrinsic value
            pnl = (intrinsic_value - premium) * contracts * multiplier
        else:
            # Short: receive premium, pay intrinsic value
            pnl = (premium - intrinsic_value) * contracts * multiplier

        return pnl

    def generate_pnl_chart_data(
        self,
        analysis: SingleLegAnalysis,
        price_range_pct: float = 0.3
    ) -> Dict[str, Any]:
        """Generate P&L data points for charting

        Args:
            analysis: SingleLegAnalysis from analyze_single_leg
            price_range_pct: Percentage range around current price (e.g., 0.3 for ±30%)

        Returns:
            Dictionary with price points and corresponding P&L values
        """
        underlying = analysis.underlying_price
        min_price = underlying * (1 - price_range_pct)
        max_price = underlying * (1 + price_range_pct)

        # Generate 50 price points
        price_points = []
        pnl_points = []

        for i in range(51):
            price = min_price + (max_price - min_price) * i / 50
            pnl = self.calculate_pnl_at_price(analysis, price)

            price_points.append(round(price, 2))
            pnl_points.append(round(pnl, 2))

        return {
            'price_points': price_points,
            'pnl_points': pnl_points,
            'current_price': underlying,
            'breakeven': analysis.breakeven,
            'strike': analysis.strike
        }
