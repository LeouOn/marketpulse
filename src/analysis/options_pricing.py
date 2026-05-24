"""Black-Scholes Options Pricing and Greeks Calculator

This module provides accurate Black-Scholes pricing for European-style options
and calculates all the Greeks (Delta, Gamma, Theta, Vega, Rho).
"""

import numpy as np
from scipy.stats import norm
from dataclasses import dataclass
from typing import Literal
from datetime import datetime, date
from loguru import logger


@dataclass
class Greeks:
    """Container for options Greeks"""
    delta: float  # Rate of change of option price w.r.t. underlying price
    gamma: float  # Rate of change of delta w.r.t. underlying price
    theta: float  # Rate of change of option price w.r.t. time (per day)
    vega: float   # Rate of change of option price w.r.t. volatility (per 1% change)
    rho: float    # Rate of change of option price w.r.t. risk-free rate (per 1% change)


@dataclass
class OptionPrice:
    """Container for option price and Greeks"""
    price: float
    greeks: Greeks


class BlackScholesCalculator:
    """Black-Scholes calculator for European options pricing and Greeks"""

    @staticmethod
    def _calculate_d1_d2(
        S: float,
        K: float,
        T: float,
        r: float,
        sigma: float,
        q: float = 0.0
    ) -> tuple[float, float]:
        """Calculate d1 and d2 for Black-Scholes formula

        Args:
            S: Current stock price
            K: Strike price
            T: Time to expiration (years)
            r: Risk-free rate (annualized)
            sigma: Volatility (annualized)
            q: Dividend yield (annualized)

        Returns:
            Tuple of (d1, d2)
        """
        if T <= 0:
            # Option has expired
            return 0.0, 0.0

        d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)

        return d1, d2

    @staticmethod
    def calculate_call_price(
        S: float,
        K: float,
        T: float,
        r: float,
        sigma: float,
        q: float = 0.0
    ) -> float:
        """Calculate Black-Scholes call option price

        Args:
            S: Current stock price
            K: Strike price
            T: Time to expiration (years)
            r: Risk-free rate (annualized)
            sigma: Volatility (annualized)
            q: Dividend yield (annualized)

        Returns:
            Call option theoretical price
        """
        if T <= 0:
            # Option has expired - intrinsic value only
            return max(S - K, 0.0)

        d1, d2 = BlackScholesCalculator._calculate_d1_d2(S, K, T, r, sigma, q)

        call_price = (
            S * np.exp(-q * T) * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
        )

        return float(call_price)

    @staticmethod
    def calculate_put_price(
        S: float,
        K: float,
        T: float,
        r: float,
        sigma: float,
        q: float = 0.0
    ) -> float:
        """Calculate Black-Scholes put option price

        Args:
            S: Current stock price
            K: Strike price
            T: Time to expiration (years)
            r: Risk-free rate (annualized)
            sigma: Volatility (annualized)
            q: Dividend yield (annualized)

        Returns:
            Put option theoretical price
        """
        if T <= 0:
            # Option has expired - intrinsic value only
            return max(K - S, 0.0)

        d1, d2 = BlackScholesCalculator._calculate_d1_d2(S, K, T, r, sigma, q)

        put_price = (
            K * np.exp(-r * T) * norm.cdf(-d2) - S * np.exp(-q * T) * norm.cdf(-d1)
        )

        return float(put_price)

    @staticmethod
    def calculate_greeks(
        S: float,
        K: float,
        T: float,
        r: float,
        sigma: float,
        q: float = 0.0,
        option_type: Literal["call", "put"] = "call"
    ) -> Greeks:
        """Calculate all Greeks for an option

        Args:
            S: Current stock price
            K: Strike price
            T: Time to expiration (years)
            r: Risk-free rate (annualized)
            sigma: Volatility (annualized)
            q: Dividend yield (annualized)
            option_type: 'call' or 'put'

        Returns:
            Greeks dataclass with all Greek values
        """
        if T <= 0:
            # Option has expired - all Greeks are zero except delta
            if option_type == "call":
                delta = 1.0 if S > K else 0.0
            else:
                delta = -1.0 if S < K else 0.0

            return Greeks(delta=delta, gamma=0.0, theta=0.0, vega=0.0, rho=0.0)

        d1, d2 = BlackScholesCalculator._calculate_d1_d2(S, K, T, r, sigma, q)

        # Common terms
        sqrt_T = np.sqrt(T)
        exp_neg_qT = np.exp(-q * T)
        exp_neg_rT = np.exp(-r * T)
        pdf_d1 = norm.pdf(d1)

        # Calculate Greeks
        if option_type == "call":
            delta = exp_neg_qT * norm.cdf(d1)
            theta = (
                -(S * pdf_d1 * sigma * exp_neg_qT) / (2 * sqrt_T)
                - r * K * exp_neg_rT * norm.cdf(d2)
                + q * S * exp_neg_qT * norm.cdf(d1)
            ) / 365.0  # Convert to per-day
            rho = K * T * exp_neg_rT * norm.cdf(d2) / 100.0  # Per 1% change
        else:  # put
            delta = exp_neg_qT * (norm.cdf(d1) - 1)
            theta = (
                -(S * pdf_d1 * sigma * exp_neg_qT) / (2 * sqrt_T)
                + r * K * exp_neg_rT * norm.cdf(-d2)
                - q * S * exp_neg_qT * norm.cdf(-d1)
            ) / 365.0  # Convert to per-day
            rho = -K * T * exp_neg_rT * norm.cdf(-d2) / 100.0  # Per 1% change

        # Gamma and Vega are the same for calls and puts
        gamma = (pdf_d1 * exp_neg_qT) / (S * sigma * sqrt_T)
        vega = S * sqrt_T * pdf_d1 * exp_neg_qT / 100.0  # Per 1% change in IV

        return Greeks(
            delta=float(delta),
            gamma=float(gamma),
            theta=float(theta),
            vega=float(vega),
            rho=float(rho)
        )

    @staticmethod
    def calculate_option_with_greeks(
        S: float,
        K: float,
        T: float,
        r: float,
        sigma: float,
        q: float = 0.0,
        option_type: Literal["call", "put"] = "call"
    ) -> OptionPrice:
        """Calculate option price and all Greeks in one call

        Args:
            S: Current stock price
            K: Strike price
            T: Time to expiration (years)
            r: Risk-free rate (annualized)
            sigma: Volatility (annualized)
            q: Dividend yield (annualized)
            option_type: 'call' or 'put'

        Returns:
            OptionPrice with theoretical price and Greeks
        """
        if option_type == "call":
            price = BlackScholesCalculator.calculate_call_price(S, K, T, r, sigma, q)
        else:
            price = BlackScholesCalculator.calculate_put_price(S, K, T, r, sigma, q)

        greeks = BlackScholesCalculator.calculate_greeks(S, K, T, r, sigma, q, option_type)

        return OptionPrice(price=price, greeks=greeks)

    @staticmethod
    def calculate_implied_volatility(
        market_price: float,
        S: float,
        K: float,
        T: float,
        r: float,
        q: float = 0.0,
        option_type: Literal["call", "put"] = "call",
        max_iterations: int = 100,
        tolerance: float = 1e-5
    ) -> float:
        """Calculate implied volatility using Newton-Raphson method

        Args:
            market_price: Observed market price of option
            S: Current stock price
            K: Strike price
            T: Time to expiration (years)
            r: Risk-free rate (annualized)
            q: Dividend yield (annualized)
            option_type: 'call' or 'put'
            max_iterations: Maximum number of iterations
            tolerance: Convergence tolerance

        Returns:
            Implied volatility (annualized)
        """
        if T <= 0 or market_price <= 0:
            return 0.0

        # Initial guess using Brenner-Subrahmanyam approximation
        sigma = np.sqrt(2 * np.pi / T) * (market_price / S)

        for i in range(max_iterations):
            if option_type == "call":
                price = BlackScholesCalculator.calculate_call_price(S, K, T, r, sigma, q)
            else:
                price = BlackScholesCalculator.calculate_put_price(S, K, T, r, sigma, q)

            diff = price - market_price

            if abs(diff) < tolerance:
                return float(sigma)

            # Calculate vega for Newton-Raphson
            d1, _ = BlackScholesCalculator._calculate_d1_d2(S, K, T, r, sigma, q)
            vega = S * np.sqrt(T) * norm.pdf(d1) * np.exp(-q * T)

            if vega < 1e-10:
                break

            # Newton-Raphson update
            sigma = sigma - diff / (vega * 100.0)  # vega is per 1% change

            # Keep sigma in reasonable bounds
            sigma = max(0.001, min(sigma, 5.0))

        logger.warning(f"IV calculation did not converge after {max_iterations} iterations")
        return float(sigma)

    @staticmethod
    def days_to_expiration(expiration_date: str) -> float:
        """Calculate time to expiration in years

        Args:
            expiration_date: Expiration date as string 'YYYY-MM-DD'

        Returns:
            Time to expiration in years
        """
        try:
            if isinstance(expiration_date, str):
                exp_date = datetime.strptime(expiration_date, '%Y-%m-%d').date()
            else:
                exp_date = expiration_date

            today = date.today()
            days = (exp_date - today).days

            # Convert to years (using 365 days per year)
            return max(days / 365.0, 0.0)

        except Exception as e:
            logger.error(f"Error calculating days to expiration: {e}")
            return 0.0
