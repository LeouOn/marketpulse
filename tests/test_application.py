#!/usr/bin/env python3
"""
MarketPulse Test Suite
Tests all major functionality of the application
"""

import requests
import json
import time
from typing import Dict, List, Any
import sys

class MarketPulseTester:
    def __init__(self):
        self.api_base = "http://localhost:8000"
        self.client_base = "http://localhost:3000"
        self.results = []
        self.passed = 0
        self.failed = 0

    def log_test(self, test_name: str, passed: bool, details: str = ""):
        """Log test result"""
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} {test_name}")
        if details:
            print(f"     {details}")

        self.results.append({
            "test": test_name,
            "passed": passed,
            "details": details
        })

        if passed:
            self.passed += 1
        else:
            self.failed += 1

    def test_api_health(self):
        """Test API health endpoint"""
        try:
            response = requests.get(f"{self.api_base}/", timeout=5)
            passed = response.status_code == 200
            details = f"Status: {response.status_code}" if not passed else "API is running"
            self.log_test("API Health Check", passed, details)
        except Exception as e:
            self.log_test("API Health Check", False, f"Connection error: {str(e)}")

    def test_client_health(self):
        """Test client health"""
        try:
            response = requests.get(self.client_base, timeout=5)
            passed = response.status_code == 200
            details = f"Status: {response.status_code}" if not passed else "Client is running"
            self.log_test("Client Health Check", passed, details)
        except Exception as e:
            self.log_test("Client Health Check", False, f"Connection error: {str(e)}")

    def test_models_endpoint(self):
        """Test models API endpoint"""
        try:
            response = requests.get(f"{self.api_base}/api/llm/models", timeout=10)
            passed = response.status_code == 200
            if passed:
                data = response.json()
                models_count = len(data.get("data", {}).get("models", []))
                details = f"Found {models_count} models"
            else:
                details = f"Status: {response.status_code}"
            self.log_test("Models API Endpoint", passed, details)
        except Exception as e:
            self.log_test("Models API Endpoint", False, f"Error: {str(e)}")

    def test_model_status_endpoint(self):
        """Test model status endpoint"""
        try:
            response = requests.get(f"{self.api_base}/api/llm/model-status", timeout=10)
            passed = response.status_code == 200
            if passed:
                data = response.json()
                lm_studio_connected = data.get("data", {}).get("lm_studio_connected", False)
                current_model = data.get("data", {}).get("current_model", "Unknown")
                details = f"LM Studio: {'Connected' if lm_studio_connected else 'Disconnected'}, Model: {current_model}"
            else:
                details = f"Status: {response.status_code}"
            self.log_test("Model Status Endpoint", passed, details)
        except Exception as e:
            self.log_test("Model Status Endpoint", False, f"Error: {str(e)}")

    def test_chat_endpoint(self):
        """Test chat endpoint with symbol recognition"""
        test_queries = [
            {"message": "What's the trend for bitcoin?", "expected_symbols": ["BTC-USD"]},
            {"message": "Tell me about Apple stock", "expected_symbols": ["AAPL"]},
            {"message": "How are NQ futures doing?", "expected_symbols": ["NQ=F"]},
            {"message": "ETH vs BTC analysis", "expected_symbols": ["ETH-USD", "BTC-USD"]},
            {"message": "General market analysis", "expected_symbols": []}
        ]

        for i, query_test in enumerate(test_queries):
            try:
                # Simulate client symbol detection
                detected_symbols = self._detect_symbols(query_test["message"])

                payload = {
                    "message": query_test["message"],
                    "context": {
                        "detected_symbols": detected_symbols,
                        "query_type": "trend_analysis"
                    },
                    "symbol": "SPY",
                    "conversation_history": []
                }

                response = requests.post(
                    f"{self.api_base}/api/llm/chat",
                    json=payload,
                    timeout=30
                )

                passed = response.status_code == 200
                if passed:
                    data = response.json()
                    # Test the response parsing fix - check for data.data.response structure
                    has_nested_response = data.get("data", {}).get("response") is not None
                    response_content = data.get("data", {}).get("response", "")
                    has_content = len(response_content) > 0
                    passed = passed and has_nested_response and has_content
                    details = f"Symbols detected: {detected_symbols}, Response length: {len(response_content)}"
                else:
                    details = f"Status: {response.status_code}"

                self.log_test(f"Chat Query {i+1}: {query_test['message']}", passed, details)

            except Exception as e:
                self.log_test(f"Chat Query {i+1}: {query_test['message']}", False, f"Error: {str(e)}")

    def _detect_symbols(self, text: str) -> List[str]:
        """Simple symbol detection for testing"""
        symbol_map = {
            "bitcoin": "BTC-USD",
            "btc": "BTC-USD",
            "ethereum": "ETH-USD",
            "eth": "ETH-USD",
            "apple": "AAPL",
            "aapl": "AAPL",
            "nq": "NQ=F",
            "nasdaq futures": "NQ=F",
            "spy": "SPY",
            "qqq": "QQQ"
        }

        detected = []
        text_lower = text.lower()

        for term, symbol in symbol_map.items():
            if term in text_lower:
                detected.append(symbol)

        return list(set(detected))

    def test_market_data_endpoint(self):
        """Test market data endpoint"""
        try:
            response = requests.get(f"{self.api_base}/api/market/internals", timeout=15)
            passed = response.status_code == 200
            if passed:
                data = response.json()
                has_data = data.get("data") is not None
                passed = passed and has_data
                details = "Market data available" if has_data else "No market data"
            else:
                details = f"Status: {response.status_code}"
            self.log_test("Market Data Endpoint", passed, details)
        except Exception as e:
            self.log_test("Market Data Endpoint", False, f"Error: {str(e)}")

    def test_symbol_patterns(self):
        """Test symbol pattern recognition"""
        test_cases = [
            {"input": "bitcoin price", "expected": ["BTC-USD"]},
            {"input": "ETH analysis", "expected": ["ETH-USD"]},
            {"input": "Apple vs Tesla", "expected": ["AAPL", "TSLA"]},
            {"input": "NQ futures trend", "expected": ["NQ=F"]},
            {"input": "Gold and oil", "expected": ["GC=F", "CL=F"]},
            {"input": "market analysis", "expected": []}
        ]

        for case in test_cases:
            detected = self._detect_symbols(case["input"])
            passed = set(detected) == set(case["expected"])
            details = f"Input: '{case['input']}', Expected: {case['expected']}, Got: {detected}"
            self.log_test(f"Symbol Pattern: {case['input']}", passed, details)

    def test_client_pages(self):
        """Test that main client pages load"""
        pages = [
            {"path": "/", "name": "Main Dashboard"},
        ]

        for page in pages:
            try:
                response = requests.get(f"{self.client_base}{page['path']}", timeout=10)
                passed = response.status_code == 200
                if passed:
                    content = response.text
                    has_title = "MarketPulse" in content
                    passed = passed and has_title
                    details = "Page loads with title" if has_title else "Page loads but missing title"
                else:
                    details = f"Status: {response.status_code}"

                self.log_test(f"Client Page: {page['name']}", passed, details)
            except Exception as e:
                self.log_test(f"Client Page: {page['name']}", False, f"Error: {str(e)}")

    def run_all_tests(self):
        """Run all tests"""
        print("Starting MarketPulse Test Suite")
        print("=" * 50)

        print("\nTesting API Endpoints...")
        self.test_api_health()
        self.test_models_endpoint()
        self.test_model_status_endpoint()
        self.test_chat_endpoint()
        self.test_market_data_endpoint()

        print("\nTesting Symbol Recognition...")
        self.test_symbol_patterns()

        print("\nTesting Client...")
        self.test_client_health()
        self.test_client_pages()

        print("\n" + "=" * 50)
        print(f"Test Results: {self.passed} passed, {self.failed} failed")

        if self.failed == 0:
            print("All tests passed! The application is working correctly.")
        else:
            print(f"{self.failed} test(s) failed. Please check the details above.")

        print("\nDetailed Results:")
        for result in self.results:
            status = "PASS" if result["passed"] else "FAIL"
            print(f"{status}: {result['test']}")
            if result["details"]:
                print(f"    {result['details']}")

        return self.failed == 0

if __name__ == "__main__":
    tester = MarketPulseTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)