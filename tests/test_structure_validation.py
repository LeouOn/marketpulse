#!/usr/bin/env python3
"""
Structural validation tests - verify code structure without dependencies
These tests check imports, syntax, and code structure
"""

import sys
import ast
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def validate_file_syntax(file_path):
    """Validate Python file syntax"""
    try:
        with open(file_path, 'r') as f:
            code = f.read()
        ast.parse(code)
        return True, None
    except SyntaxError as e:
        return False, str(e)


def test_file_structure():
    """Test that all required files exist"""
    print("\n📁 File Structure Validation")
    print("="*70)

    required_files = [
        # Options pricing modules
        'src/analysis/options_pricing.py',
        'src/analysis/options_analyzer.py',
        'src/analysis/strategy_builder.py',
        'src/analysis/macro_context.py',
        'src/analysis/options_screener.py',

        # Database
        'database/02-options-tables.sql',

        # Tests
        'tests/test_options_pricing.py',
        'tests/test_options_api.py',

        # Documentation
        'OPTIONS_IMPLEMENTATION.md',
    ]

    all_exist = True
    for file_path in required_files:
        full_path = project_root / file_path
        if full_path.exists():
            print(f"  ✅ {file_path}")
        else:
            print(f"  ❌ {file_path} - MISSING")
            all_exist = False

    return all_exist


def test_python_syntax():
    """Test that all Python files have valid syntax"""
    print("\n🔍 Python Syntax Validation")
    print("="*70)

    python_files = [
        'src/analysis/options_pricing.py',
        'src/analysis/options_analyzer.py',
        'src/analysis/strategy_builder.py',
        'src/analysis/macro_context.py',
        'src/analysis/options_screener.py',
        'tests/test_options_pricing.py',
        'tests/test_options_api.py',
    ]

    all_valid = True
    for file_path in python_files:
        full_path = project_root / file_path
        if full_path.exists():
            valid, error = validate_file_syntax(full_path)
            if valid:
                print(f"  ✅ {file_path}")
            else:
                print(f"  ❌ {file_path} - SYNTAX ERROR: {error}")
                all_valid = False

    return all_valid


def test_class_definitions():
    """Test that key classes are defined"""
    print("\n🏗️  Class Definition Validation")
    print("="*70)

    # Read and parse each file
    files_and_classes = {
        'src/analysis/options_pricing.py': ['BlackScholesCalculator', 'Greeks', 'OptionPrice'],
        'src/analysis/options_analyzer.py': ['OptionsAnalyzer', 'SingleLegAnalysis'],
        'src/analysis/strategy_builder.py': ['StrategyBuilder', 'CoveredCallAnalysis', 'SpreadAnalysis'],
        'src/analysis/macro_context.py': ['MacroRegime'],
        'src/analysis/options_screener.py': ['OptionsScreener', 'OptionOpportunity'],
    }

    all_defined = True
    for file_path, expected_classes in files_and_classes.items():
        full_path = project_root / file_path
        if not full_path.exists():
            print(f"  ❌ {file_path} - FILE MISSING")
            all_defined = False
            continue

        try:
            with open(full_path, 'r') as f:
                code = f.read()
            tree = ast.parse(code)

            # Extract class names
            class_names = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]

            # Check each expected class
            for class_name in expected_classes:
                if class_name in class_names:
                    print(f"  ✅ {file_path}: {class_name}")
                else:
                    print(f"  ❌ {file_path}: {class_name} - NOT FOUND")
                    all_defined = False

        except Exception as e:
            print(f"  ❌ {file_path} - ERROR: {e}")
            all_defined = False

    return all_defined


def test_api_endpoints():
    """Test that API endpoints are defined in main.py"""
    print("\n🌐 API Endpoint Validation")
    print("="*70)

    main_py = project_root / 'src/api/main.py'

    if not main_py.exists():
        print("  ❌ src/api/main.py not found")
        return False

    with open(main_py, 'r') as f:
        content = f.read()

    expected_endpoints = [
        '/api/options/expirations/',
        '/api/options/chain/',
        '/api/options/analyze/single-leg',
        '/api/options/screen',
        '/api/options/strategy/covered-call',
        '/api/options/strategy/bull-call-spread',
        '/api/options/strategy/bear-put-spread',
        '/api/options/macro-context',
    ]

    all_defined = True
    for endpoint in expected_endpoints:
        if endpoint in content:
            print(f"  ✅ {endpoint}")
        else:
            print(f"  ❌ {endpoint} - NOT FOUND")
            all_defined = False

    return all_defined


def test_database_schema():
    """Test that database schema files are valid SQL"""
    print("\n🗄️  Database Schema Validation")
    print("="*70)

    schema_file = project_root / 'database/02-options-tables.sql'

    if not schema_file.exists():
        print("  ❌ database/02-options-tables.sql not found")
        return False

    with open(schema_file, 'r') as f:
        content = f.read()

    # Check for key tables
    expected_tables = [
        'options_chains',
        'options_analysis',
        'options_screening',
        'macro_context',
        'options_watchlist',
    ]

    all_defined = True
    for table in expected_tables:
        if table in content:
            print(f"  ✅ Table: {table}")
        else:
            print(f"  ❌ Table: {table} - NOT FOUND")
            all_defined = False

    return all_defined


def test_yahoo_client_methods():
    """Test that Yahoo client has options methods"""
    print("\n📡 Yahoo Client Methods Validation")
    print("="*70)

    yahoo_client = project_root / 'src/api/yahoo_client.py'

    if not yahoo_client.exists():
        print("  ❌ src/api/yahoo_client.py not found")
        return False

    with open(yahoo_client, 'r') as f:
        content = f.read()

    expected_methods = [
        'get_options_expirations',
        'get_options_chain',
        'get_risk_free_rate',
        'get_dividend_yield',
    ]

    all_defined = True
    for method in expected_methods:
        if f'def {method}' in content:
            print(f"  ✅ Method: {method}")
        else:
            print(f"  ❌ Method: {method} - NOT FOUND")
            all_defined = False

    return all_defined


def run_structural_validation():
    """Run all structural validation tests"""
    print("\n" + "="*70)
    print("STRUCTURAL VALIDATION (No Dependencies Required)")
    print("="*70)

    results = []

    results.append(("File Structure", test_file_structure()))
    results.append(("Python Syntax", test_python_syntax()))
    results.append(("Class Definitions", test_class_definitions()))
    results.append(("API Endpoints", test_api_endpoints()))
    results.append(("Database Schema", test_database_schema()))
    results.append(("Yahoo Client Methods", test_yahoo_client_methods()))

    # Summary
    print("\n" + "="*70)
    print("STRUCTURAL VALIDATION SUMMARY")
    print("="*70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{name}: {status}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All structural validation tests passed!")
        print("   Code structure is correct and ready for runtime testing.")
        return True
    else:
        print("\n❌ Some structural validation tests failed")
        print("   Please fix the issues before running unit tests.")
        return False


if __name__ == "__main__":
    success = run_structural_validation()
    sys.exit(0 if success else 1)
