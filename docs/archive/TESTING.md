# MarketPulse Testing Guide

## Overview

This document describes the comprehensive testing strategy for MarketPulse with options pricing features. The test suite ensures both existing functionality (regression) and new options features work correctly.

## Test Structure

### 1. Structural Validation (`tests/test_structure_validation.py`)
**No dependencies required** - Validates code structure without runtime execution

**What it tests:**
- ✅ All required files exist
- ✅ Python syntax is valid
- ✅ Classes are defined correctly
- ✅ API endpoints are present in main.py
- ✅ Database schema is complete
- ✅ Yahoo client has options methods

**Run with:**
```bash
python3 tests/test_structure_validation.py
```

**Expected output:**
```
🎉 All structural validation tests passed!
   Code structure is correct and ready for runtime testing.
```

---

### 2. Unit Tests (`tests/test_options_pricing.py`)
**Requires: numpy, scipy, yfinance**

**What it tests:**

#### Black-Scholes Pricing
- Call and put option pricing
- Put-call parity relationship
- Greeks calculations (Delta, Gamma, Theta, Vega, Rho)
- ATM, ITM, and OTM options
- Expired options (intrinsic value)
- Time to expiration calculations

#### Options Analyzer
- Risk metrics (breakeven, max profit/loss)
- Probability of profit estimations
- Long/short positions for calls/puts

#### Strategy Builder
- Module imports and structure

#### Macro Context
- VIX regime classification
- Volatility level mappings

#### Options Screener
- Module imports and structure

**Run with:**
```bash
python3 tests/test_options_pricing.py
```

**Expected output:**
```
🎉 All tests passed!
Total tests: 16+
Passed: 16+ ✅
Failed: 0 ❌
```

---

### 3. Integration Tests (`tests/test_options_api.py`)
**Requires: API server running + dependencies**

**What it tests:**

#### Regression Tests (Existing Endpoints)
- Root endpoint (/)
- Market internals (/api/market/internals)
- Market dashboard (/api/market/dashboard)

#### New Options Endpoints
- GET /api/options/expirations/{symbol}
- GET /api/options/chain/{symbol}/{expiration}
- POST /api/options/analyze/single-leg
- POST /api/options/screen
- POST /api/options/strategy/covered-call
- POST /api/options/strategy/bull-call-spread
- GET /api/options/macro-context

**Run with:**
```bash
# Start API server first
uvicorn src.api.main:app --reload

# In another terminal
python3 tests/test_options_api.py
```

**Expected output:**
```
🎉 All integration tests passed!

✅ No regressions detected
✅ All new options endpoints working
```

---

### 4. Comprehensive Test Runner (`run_tests.sh`)
**Automated test suite that runs all tests in order**

**Run with:**
```bash
./run_tests.sh
```

**What it does:**
1. ✅ Checks dependencies are installed
2. ✅ Runs structural validation
3. ✅ Runs unit tests
4. ✅ Runs integration tests (if server running)
5. ✅ Runs regression tests
6. ✅ Provides comprehensive summary

**Expected output:**
```
🎉 ALL TESTS PASSED!

✅ Unit tests: PASSED
✅ Integration tests: PASSED
✅ Regression tests: PASSED
```

---

## Quick Start

### First Time Setup

1. **Install dependencies:**
```bash
pip install -r requirements.txt
```

2. **Verify installation:**
```bash
python3 -c "import numpy, scipy, yfinance; print('✅ Dependencies OK')"
```

3. **Run structural validation:**
```bash
python3 tests/test_structure_validation.py
```

### Regular Development Workflow

**Before committing:**
```bash
# Run quick validation
python3 tests/test_structure_validation.py

# Run unit tests
python3 tests/test_options_pricing.py
```

**Before deploying:**
```bash
# Run full test suite
./run_tests.sh
```

---

## Test Coverage

### Options Pricing Module

| Feature | Test Coverage |
|---------|--------------|
| Black-Scholes pricing | ✅ Full |
| Greeks calculations | ✅ Full |
| Put-call parity | ✅ Verified |
| Implied volatility | ✅ Structure |
| Time calculations | ✅ Full |

### Options Analyzer

| Feature | Test Coverage |
|---------|--------------|
| Single leg analysis | ✅ Risk metrics |
| P&L calculations | ✅ Structure |
| Probability estimates | ✅ Full |
| Long/short positions | ✅ Full |

### Strategy Builder

| Feature | Test Coverage |
|---------|--------------|
| Covered calls | ✅ Integration |
| Bull call spreads | ✅ Integration |
| Bear put spreads | ✅ Integration |
| Net Greeks | ✅ Integration |

### Macro Context

| Feature | Test Coverage |
|---------|--------------|
| VIX regime classification | ✅ Full |
| Sector performance | ✅ Structure |
| Market breadth | ✅ Structure |

### API Endpoints

| Endpoint | Test Coverage |
|----------|--------------|
| Options expirations | ✅ Integration |
| Options chain | ✅ Integration |
| Single leg analysis | ✅ Integration |
| Options screening | ✅ Integration |
| Covered call | ✅ Integration |
| Bull/bear spreads | ✅ Integration |
| Macro context | ✅ Integration |

---

## Testing Best Practices

### 1. Test Pyramid

```
           /\
          /  \     ← Few integration tests (slow, broad)
         /    \
        /------\   ← More unit tests (fast, focused)
       /        \
      /----------\ ← Many structural tests (instant, wide)
```

### 2. Test-Driven Development

1. **Red**: Write failing test
2. **Green**: Make it pass
3. **Refactor**: Improve code
4. **Repeat**

### 3. Before Committing

✅ Run structural validation
✅ Run unit tests
✅ Fix any failures
✅ Commit with confidence

### 4. Before Deploying

✅ Run full test suite (`./run_tests.sh`)
✅ Verify no regressions
✅ Check all new features work
✅ Deploy

---

## Continuous Integration (Future)

### GitHub Actions Workflow

```yaml
name: Test Suite
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Structural validation
        run: python3 tests/test_structure_validation.py
      - name: Unit tests
        run: python3 tests/test_options_pricing.py
      - name: Start API server
        run: uvicorn src.api.main:app &
      - name: Integration tests
        run: python3 tests/test_options_api.py
```

---

## Debugging Failed Tests

### Structural Validation Failures

**Symptom:** File not found or syntax error

**Fix:**
1. Check file exists in correct location
2. Run `python3 -m py_compile <file>` to find syntax errors
3. Fix syntax and re-run

### Unit Test Failures

**Symptom:** Assertion error or calculation mismatch

**Fix:**
1. Read the assertion message carefully
2. Add print statements to see intermediate values
3. Verify mathematical formulas
4. Check edge cases

### Integration Test Failures

**Symptom:** API returns error or unexpected data

**Fix:**
1. Check API server logs
2. Test endpoint manually with curl:
   ```bash
   curl http://localhost:8000/api/options/expirations/AAPL
   ```
3. Verify Yahoo Finance data is available
4. Check network connectivity

### Common Issues

| Issue | Solution |
|-------|----------|
| ModuleNotFoundError | Run `pip install -r requirements.txt` |
| API server not running | Start with `uvicorn src.api.main:app --reload` |
| Yahoo Finance timeout | Check internet connection, retry |
| Delta/Greeks mismatch | Verify Black-Scholes implementation |
| Database error | Run migrations, check connection |

---

## Test Data

### Mock vs Real Data

**Structural tests:** No data needed ✅

**Unit tests:** Use fixed test data (S=100, K=100, etc.) ✅

**Integration tests:** Use real market data from Yahoo Finance ⚠️
- AAPL (high liquidity, stable)
- SPY (ETF, always has options)
- Avoid: penny stocks, illiquid options

### Test Symbols

Recommended for testing:
- ✅ AAPL - High liquidity, predictable
- ✅ SPY - ETF, always tradable
- ✅ QQQ - Tech ETF, high volume
- ❌ Avoid: Low volume stocks
- ❌ Avoid: Stocks without options

---

## Performance Benchmarks

### Unit Tests
- **Target:** < 5 seconds
- **Actual:** ~2-3 seconds
- **Optimization:** Pure Python calculations, no I/O

### Integration Tests
- **Target:** < 60 seconds
- **Actual:** ~30-45 seconds (depends on Yahoo Finance)
- **Optimization:** Parallel requests, caching

### Full Test Suite
- **Target:** < 90 seconds
- **Actual:** ~60-75 seconds
- **Optimization:** Skip integration if server not running

---

## Future Enhancements

### Week 2
- [ ] Performance tests (load testing)
- [ ] Error injection tests (chaos engineering)
- [ ] Mock Yahoo Finance for faster tests
- [ ] Test coverage reporting (pytest-cov)

### Week 3
- [ ] Property-based testing (hypothesis)
- [ ] Mutation testing
- [ ] Visual regression testing (frontend)
- [ ] Security testing (SQL injection, XSS)

### Week 4
- [ ] End-to-end UI tests (Playwright/Selenium)
- [ ] Database migration tests
- [ ] Backward compatibility tests
- [ ] Benchmark regression tests

---

## Contributing

### Adding New Tests

1. **Structural tests:** Add to `test_structure_validation.py`
2. **Unit tests:** Add to `test_options_pricing.py`
3. **Integration tests:** Add to `test_options_api.py`
4. **Update this document**

### Test Naming Convention

```python
def test_<module>_<feature>_<scenario>():
    """Test that <feature> <expected_behavior> when <scenario>"""
    # Arrange
    ...
    # Act
    ...
    # Assert
    ...
```

### Example

```python
def test_black_scholes_call_pricing_atm_option():
    """Test that Black-Scholes calculates correct price for ATM call"""
    # Arrange
    S, K = 100, 100  # ATM

    # Act
    price = BlackScholesCalculator.calculate_call_price(...)

    # Assert
    assert 2 < price < 5, "ATM call should be 2-5% of stock price"
```

---

## Support

For testing issues:
1. Check this document first
2. Run `./run_tests.sh` to identify which test fails
3. Read error messages carefully
4. Check GitHub issues
5. Create new issue with:
   - Test output
   - Expected vs actual behavior
   - Environment details

---

**Last Updated:** November 15, 2025
**Test Suite Version:** 1.0.0
**Options Implementation Version:** 1.0.0
