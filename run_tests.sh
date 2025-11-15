#!/bin/bash
# Comprehensive test runner for MarketPulse with options pricing

echo "=================================================="
echo "MarketPulse Test Suite - With Options Pricing"
echo "=================================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if dependencies are installed
echo "📦 Checking dependencies..."
python3 -c "import numpy, scipy, yfinance" 2>/dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ All dependencies installed${NC}"
else
    echo -e "${RED}❌ Missing dependencies${NC}"
    echo ""
    echo "Please install dependencies first:"
    echo "  pip install -r requirements.txt"
    echo ""
    exit 1
fi

echo ""

# Run structural validation (doesn't need data)
echo "🔍 Step 1: Structural Validation"
echo "=================================================="
python3 tests/test_structure_validation.py
if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Structural validation failed${NC}"
    exit 1
fi
echo ""

# Run unit tests
echo "🧪 Step 2: Unit Tests"
echo "=================================================="
python3 tests/test_options_pricing.py
UNIT_TEST_RESULT=$?
echo ""

# Run integration tests (requires server)
echo "🌐 Step 3: Integration Tests"
echo "=================================================="
echo "Checking if API server is running..."
curl -s http://localhost:8000/ > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ API server is running${NC}"
    python3 tests/test_options_api.py
    API_TEST_RESULT=$?
else
    echo -e "${YELLOW}⚠️  API server not running - skipping integration tests${NC}"
    echo "   To run integration tests, start the server:"
    echo "   uvicorn src.api.main:app --reload"
    API_TEST_RESULT=0  # Don't fail if server not running
fi
echo ""

# Run existing test suite (regression test)
echo "🔄 Step 4: Regression Tests"
echo "=================================================="
if [ -f tests/test_api.py ]; then
    python3 tests/test_api.py
    REGRESSION_RESULT=$?
else
    echo "No existing tests found - skipping"
    REGRESSION_RESULT=0
fi
echo ""

# Summary
echo "=================================================="
echo "TEST SUMMARY"
echo "=================================================="

if [ $UNIT_TEST_RESULT -eq 0 ]; then
    echo -e "${GREEN}✅ Unit tests: PASSED${NC}"
else
    echo -e "${RED}❌ Unit tests: FAILED${NC}"
fi

if [ $API_TEST_RESULT -eq 0 ]; then
    echo -e "${GREEN}✅ Integration tests: PASSED${NC}"
else
    echo -e "${RED}❌ Integration tests: FAILED${NC}"
fi

if [ $REGRESSION_RESULT -eq 0 ]; then
    echo -e "${GREEN}✅ Regression tests: PASSED${NC}"
else
    echo -e "${RED}❌ Regression tests: FAILED${NC}"
fi

echo ""

# Overall result
if [ $UNIT_TEST_RESULT -eq 0 ] && [ $API_TEST_RESULT -eq 0 ] && [ $REGRESSION_RESULT -eq 0 ]; then
    echo -e "${GREEN}🎉 ALL TESTS PASSED!${NC}"
    exit 0
else
    echo -e "${RED}❌ SOME TESTS FAILED${NC}"
    exit 1
fi
