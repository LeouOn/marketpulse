"""MarketPulse Data Validation Module
Better validation using:
- Historical baseline (previous close comparison)
- Cross-symbol consistency
- Data freshness
- No hardcoded price ranges
"""

from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, timedelta
from loguru import logger
import numpy as np


# Thresholds (configurable)
FRESHNESS_THRESHOLD_SECONDS = 900  # 15 minutes - data older than this is stale
MAX_DAILY_CHANGE_PCT = 8.0  # Maximum allowed daily change (%)
MAX_CROSS_SYMBOL_DIVERGENCE_PCT = 10.0  # SPY/QQQ allowed to diverge before flag
MAX_FUTURES_SPOT_DIFF_PCT = 1.0  # Futures vs spot max divergence


class ValidationResult:
    """Result of a validation check"""

    def __init__(self, is_valid: bool, issues: List[str] = None, warnings: List[str] = None):
        self.is_valid = is_valid
        self.issues = issues or []
        self.warnings = warnings or []

    def __repr__(self):
        status = "VALID" if self.is_valid else "INVALID"
        return f"ValidationResult({status}, issues={self.issues}, warnings={self.warnings})"

    def merge(self, other: 'ValidationResult') -> 'ValidationResult':
        """Merge two validation results"""
        return ValidationResult(
            is_valid=self.is_valid and other.is_valid,
            issues=self.issues + other.issues,
            warnings=self.warnings + other.warnings
        )


def validate_freshness(data_age_seconds: Optional[float], max_age_seconds: int = FRESHNESS_THRESHOLD_SECONDS) -> ValidationResult:
    """
    Validate that data is fresh (not stale).
    Stale = older than max_age_seconds (default 15 minutes).
    Flagged as warning, not failure - system continues with stale data.

    Args:
        data_age_seconds: Age of data in seconds
        max_age_seconds: Maximum allowed age

    Returns:
        ValidationResult with warnings if stale (not issues - continues operation)
    """
    if data_age_seconds is None:
        return ValidationResult(True, warnings=["Data age unknown (timestamp missing)"])

    if data_age_seconds > max_age_seconds:
        return ValidationResult(True, warnings=[f"Data is stale: {data_age_seconds:.0f}s old (max: {max_age_seconds}s)"])

    return ValidationResult(True)


def validate_change_from_previous(price: float, prev_close: float, max_change_pct: float = MAX_DAILY_CHANGE_PCT) -> ValidationResult:
    """
    Validate price change against previous close (historical baseline).
    This adapts to any price level - no hardcoded ranges.

    Args:
        price: Current price
        prev_close: Previous close price
        max_change_pct: Maximum allowed change percentage

    Returns:
        ValidationResult with issues if change exceeds threshold
    """
    if price is None or prev_close is None:
        return ValidationResult(False, ["Price or previous close is None"])

    if prev_close <= 0:
        return ValidationResult(False, [f"Invalid previous close: {prev_close}"])

    change_pct = abs((price - prev_close) / prev_close) * 100

    if change_pct > max_change_pct:
        return ValidationResult(False, [f"Price change {change_pct:.2f}% exceeds max {max_change_pct}%"])

    return ValidationResult(True)


def validate_cross_symbol_consistency(internals: Dict[str, Any], max_divergence_pct: float = MAX_CROSS_SYMBOL_DIVERGENCE_PCT) -> ValidationResult:
    """
    Validate that related symbols are consistent with each other.
    SPY and QQQ should generally agree on direction.

    Args:
        internals: Market internals dict with symbol data
        max_divergence_pct: Maximum allowed divergence percentage

    Returns:
        ValidationResult with issues if inconsistency found
    """
    issues = []
    warnings = []

    spy_data = internals.get('spy')
    qqq_data = internals.get('qqq')

    if spy_data and qqq_data:
        spy_change = spy_data.get('change_pct', 0)
        qqq_change = qqq_data.get('change_pct', 0)

        if spy_change != 0 or qqq_change != 0:
            divergence = abs(spy_change - qqq_change)

            if divergence > max_divergence_pct:
                # Large divergence - this could be real market behavior, flag as warning
                warnings.append(f"SPY ({spy_change:+.2f}%) and QQQ ({qqq_change:+.2f}%) diverge by {divergence:.2f}%")

    return ValidationResult(True, issues, warnings)


def validate_futures_spot_consistency(internals: Dict[str, Any], max_diff_pct: float = MAX_FUTURES_SPOT_DIFF_PCT) -> ValidationResult:
    """
    Validate that futures prices are consistent with spot prices.
    ES=F should track SPY, NQ=F should track QQQ.

    Args:
        internals: Market internals dict
        max_diff_pct: Maximum allowed futures/spot difference percentage

    Returns:
        ValidationResult with issues if inconsistency found
    """
    issues = []
    warnings = []

    # ES=F (S&P futures) vs SPY
    if 'es=f' in internals and 'spy' in internals:
        es_price = internals['es=f'].get('price', 0)
        spy_price = internals['spy'].get('price', 0)

        if es_price > 0 and spy_price > 0:
            # S&P futures track SPY, multiply spot by ~1 for the futures price approximation
            # Actually ES=F is priced differently, we check % change instead
            es_change = internals['es=f'].get('change_pct', 0)
            spy_change = internals['spy'].get('change_pct', 0)

            diff = abs(es_change - spy_change)
            if diff > max_diff_pct * 3:  # Give more room for futures
                warnings.append(f"ES=F ({es_change:+.2f}%) vs SPY ({spy_change:+.2f}%) diff {diff:.2f}%")

    # NQ=F (Nasdaq futures) vs QQQ
    if 'nq=f' in internals and 'qqq' in internals:
        nq_price = internals['nq=f'].get('price', 0)
        qqq_price = internals['qqq'].get('price', 0)

        if nq_price > 0 and qqq_price > 0:
            nq_change = internals['nq=f'].get('change_pct', 0)
            qqq_change = internals['qqq'].get('change_pct', 0)

            diff = abs(nq_change - qqq_change)
            if diff > max_diff_pct * 5:  # Nasdaq is more volatile
                warnings.append(f"NQ=F ({nq_change:+.2f}%) vs QQQ ({qqq_change:+.2f}%) diff {diff:.2f}%")

    return ValidationResult(True, issues, warnings)


def validate_ohlc(open_price: float, high_price: float, low_price: float, close_price: float) -> ValidationResult:
    """
    Validate OHLC data consistency.
    Rules: High >= max(Open, Close), Low <= min(Open, Close), all > 0

    Args:
        open_price, high_price, low_price, close_price: OHLC values

    Returns:
        ValidationResult with issues if any
    """
    issues = []

    if any(p is None for p in [open_price, high_price, low_price, close_price]):
        return ValidationResult(False, ["One or more OHLC values are None"])

    if any(p <= 0 for p in [open_price, high_price, low_price, close_price]):
        issues.append(f"OHLC contains non-positive price: O={open_price}, H={high_price}, L={low_price}, C={close_price}")

    if high_price < max(open_price, close_price):
        issues.append(f"High ${high_price:.2f} < max(Open ${open_price:.2f}, Close ${close_price:.2f})")

    if low_price > min(open_price, close_price):
        issues.append(f"Low ${low_price:.2f} > min(Open ${open_price:.2f}, Close ${close_price:.2f})")

    return ValidationResult(len(issues) == 0, issues)


def validate_market_internals(internals: Dict[str, Any], strict: bool = True) -> ValidationResult:
    """
    Validate complete market internals data.

    Args:
        internals: Market internals dictionary
        strict: If True, issues become failures. If False, issues become warnings.

    Returns:
        ValidationResult with aggregated issues/warnings
    """
    result = ValidationResult(True)
    symbol_data_keys = ['price', 'change', 'change_pct', 'volume']

    for symbol, data in internals.items():
        # Skip metadata keys
        if symbol in ('data_source', 'timestamp', 'volume_flow', 'synthetic', 'data_quality', 'quality_issues'):
            continue

        if not isinstance(data, dict):
            result = result.merge(ValidationResult(False, [f"{symbol}: data is not a dict"]))
            continue

        # Freshness validation
        data_age = data.get('data_age_seconds')
        freshness_result = validate_freshness(data_age)
        if not freshness_result.is_valid:
            if strict:
                result = result.merge(freshness_result)
            else:
                result.warnings.append(f"{symbol}: {freshness_result.issues[0]}")

        # Volume validation (non-negative)
        volume = data.get('volume')
        if volume is not None and volume < 0:
            result = result.merge(ValidationResult(False, [f"{symbol}: negative volume"]))

        # OHLC validation (if present)
        has_ohlc = all(k in data for k in ['open', 'high', 'low', 'close'])
        if has_ohlc:
            ohlc_result = validate_ohlc(
                data['open'], data['high'], data['low'], data['close']
            )
            result = result.merge(ohlc_result)

    # Cross-symbol validation
    cross_result = validate_cross_symbol_consistency(internals)
    result = result.merge(cross_result)

    # Futures/spot validation
    futures_result = validate_futures_spot_consistency(internals)
    result = result.merge(futures_result)

    return result


def is_data_usable(internals: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Quick check if data is usable for trading decisions.
    Returns (is_usable, reason).

    Args:
        internals: Market internals dictionary

    Returns:
        Tuple of (bool, reason_string)
    """
# Check for synthetic/mock data - not usable for trading
    if internals.get('synthetic') or internals.get('data_source') == 'mock':
        return False, "Data is synthetic/mock - not suitable for trading decisions"

    # Check for missing core symbols
    for sym in ['spy', 'qqq']:
        if sym not in internals or not isinstance(internals.get(sym), dict):
            return False, f"Core symbol {sym.upper()} missing or invalid"

    # Validate price data
    for sym in ['spy', 'qqq']:
        data = internals.get(sym, {})
        if not isinstance(data, dict):
            return False, f"{sym.upper()} data is not a dict"

        price = data.get('price', 0)
        if price <= 0:
            return False, f"{sym.upper()} price is {price} - invalid"

    return True, "Data passes basic usability checks"


def flag_data_quality(internals: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze internals and add data quality flags.
    Always returns data with quality metadata - never rejects.

    Args:
        internals: Market internals dictionary

    Returns:
        Dictionary with quality metadata added:
        - data_quality: 'good', 'partial', 'poor', 'unknown'
        - issues: List of validation issues
        - warnings: List of validation warnings
        - missing_symbols: List of expected but missing symbols
        - synthetic: True if data is from mock
        - freshness_status: 'fresh' or 'stale'
    """
    quality_flags = {
        'data_quality': 'unknown',
        'issues': [],
        'warnings': [],
        'missing_symbols': [],
        'synthetic': internals.get('synthetic', False),
        'freshness_status': 'unknown',
        'validation_passed': True
    }

    # Check for synthetic/mock data
    if internals.get('data_source') == 'mock' or internals.get('synthetic'):
        quality_flags['synthetic'] = True
        quality_flags['warnings'].append(f"Data is synthetic (source: {internals.get('data_source', 'unknown')})")

    # Check freshness
    data_age = internals.get('spy', {}).get('data_age_seconds') if 'spy' in internals else None
    if data_age is not None:
        if data_age <= FRESHNESS_THRESHOLD_SECONDS:
            quality_flags['freshness_status'] = 'fresh'
        else:
            quality_flags['freshness_status'] = 'stale'
            quality_flags['warnings'].append(f"Data is stale: {data_age:.0f}s old")

    # Validate what we have
    validation = validate_market_internals(internals, strict=False)
    quality_flags['issues'].extend(validation.issues)
    quality_flags['warnings'].extend(validation.warnings)

    if not validation.is_valid:
        quality_flags['validation_passed'] = False

    # Check for missing core symbols
    required = ['spy', 'qqq', 'vix']
    for sym in required:
        if sym not in internals:
            quality_flags['missing_symbols'].append(sym)
            quality_flags['warnings'].append(f"Missing required symbol: {sym}")

    # Determine overall quality
    if quality_flags['synthetic']:
        quality_flags['data_quality'] = 'poor'
    elif not validation.is_valid:
        quality_flags['data_quality'] = 'poor'
    elif len(quality_flags['warnings']) > 0:
        quality_flags['data_quality'] = 'partial'
    elif len(quality_flags['issues']) == 0:
        quality_flags['data_quality'] = 'good'
    else:
        quality_flags['data_quality'] = 'unknown'

    return quality_flags