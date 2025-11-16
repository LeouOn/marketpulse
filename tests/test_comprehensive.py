#!/usr/bin/env python3
"""
Comprehensive MarketPulse Test Suite

Tests all major systems:
- Imports
- Technical Indicators
- Chart Generation
- Risk Management
- State Management
- Trade Journal
"""

import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

print('='*70)
print('MARKETPULSE COMPREHENSIVE TEST SUITE')
print('='*70)

# Test 1: Import all modules
print('\n📦 Testing imports...')
try:
    from src.analysis.technical_indicators import TechnicalIndicators
    print('✅ Technical Indicators imported')

    from src.visualization.chart_generator import ChartGenerator
    print('✅ Chart Generator imported')

    from src.api.yahoo_client import YahooFinanceClient
    print('✅ Yahoo Client imported')

    from src.analysis.risk_manager import RiskManager
    print('✅ Risk Manager imported')

    from src.state.position_manager import PositionManager
    print('✅ Position Manager imported')

    from src.journal.trade_tracker import TradeJournal
    print('✅ Trade Journal imported')

    from src.alerts.alert_manager import AlertManager
    print('✅ Alert Manager imported')

    from src.analysis.ict_concepts import FairValueGapDetector
    print('✅ ICT Concepts imported')

    print('✅ All modules imported successfully')
except Exception as e:
    print(f'❌ Import error: {e}')
    sys.exit(1)

# Test 2: Technical Indicators
print('\n📊 Testing Technical Indicators...')
try:
    import pandas as pd
    import numpy as np
    from datetime import datetime, timedelta

    dates = pd.date_range(end=datetime.now(), periods=200, freq='1h')
    data = {
        'open': np.random.randn(200).cumsum() + 15850,
        'high': np.random.randn(200).cumsum() + 15852,
        'low': np.random.randn(200).cumsum() + 15848,
        'close': np.random.randn(200).cumsum() + 15850,
        'volume': np.random.randint(1000, 10000, 200)
    }
    df = pd.DataFrame(data, index=dates)
    df['high'] = df[['open', 'high', 'close']].max(axis=1) + 1
    df['low'] = df[['open', 'low', 'close']].min(axis=1) - 1

    # Test all indicators
    indicators = ['sma_20', 'ema_21', 'rsi', 'macd', 'bollinger', 'atr', 'vwap', 'supertrend']
    df_ind = TechnicalIndicators.calculate_all(df, indicators)

    print(f'✅ Calculated {len(indicators)} indicators')
    print(f'✅ DataFrame has {len(df_ind.columns)} total columns')

    # Check values
    assert 'sma_20' in df_ind.columns
    assert 'rsi' in df_ind.columns
    assert 'macd' in df_ind.columns
    print('✅ All indicator columns present')

except Exception as e:
    print(f'❌ Technical Indicators error: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 3: Chart Generation
print('\n📈 Testing Chart Generation...')
try:
    chart_gen = ChartGenerator(theme='dark')

    # Candlestick chart
    fig1 = chart_gen.create_candlestick_chart(df, indicators=['sma_20', 'ema_21'])
    print('✅ Candlestick chart created')

    # Indicator panel
    fig2 = chart_gen.create_indicator_panel(df)
    print('✅ Indicator panel created')

    # Volume profile
    fig3 = chart_gen.create_volume_profile(df)
    print('✅ Volume profile created')

    # Heatmap
    heatmap_data = {'Tech': 2.5, 'Finance': -1.2, 'Healthcare': 0.8, 'Energy': -0.5}
    fig4 = chart_gen.create_market_heatmap(heatmap_data)
    print('✅ Market heatmap created')

    print('✅ All chart types generated successfully')

except Exception as e:
    print(f'❌ Chart Generation error: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 4: Risk Management
print('\n🛡️  Testing Risk Management...')
try:
    risk_mgr = RiskManager(account_size=10000, max_daily_loss=500, max_position_risk=250)

    # Validate good trade
    validation = risk_mgr.validate_trade(
        symbol='MNQ',
        entry_price=15850,
        stop_loss=15840,
        take_profit=15870,
        direction='long',
        contracts=2
    )

    assert validation.approved == True
    print('✅ Good trade approved')

    # Validate bad trade (excessive risk)
    validation2 = risk_mgr.validate_trade(
        symbol='MNQ',
        entry_price=15850,
        stop_loss=15800,  # 50 points
        take_profit=15900,
        direction='long',
        contracts=4
    )

    assert validation2.approved == False
    print('✅ Excessive risk trade rejected')

    # Test position sizing
    contracts = risk_mgr.calculate_position_size(
        entry_price=15850,
        stop_loss=15840,
        direction='long',
        point_value=2.0
    )

    assert contracts > 0
    print(f'✅ Position sizing calculated: {contracts} contracts')

    print('✅ Risk management working correctly')

except Exception as e:
    print(f'❌ Risk Management error: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 5: State Management
print('\n💾 Testing State Management...')
try:
    import os
    test_file = 'data/state/test_state.json'
    if os.path.exists(test_file):
        os.remove(test_file)

    pos_mgr = PositionManager(state_file=test_file)

    from src.state.position_manager import Position, PositionSide, PositionStatus
    import uuid

    # Add position
    pos = Position(
        id=str(uuid.uuid4()),
        symbol='MNQ',
        side=PositionSide.LONG,
        entry_price=15850,
        stop_loss=15840,
        take_profit=15870,
        contracts=2,
        entry_timestamp=datetime.now(),
        status=PositionStatus.OPEN
    )

    pos_mgr.add_position(pos)
    print('✅ Position added')

    # Close position
    closed = pos_mgr.close_position(pos.id, exit_price=15870)
    assert closed.realized_pnl == 80.0  # 20 points * $2 * 2 contracts
    print(f'✅ Position closed with P&L: ${closed.realized_pnl}')

    # Check state
    summary = pos_mgr.get_state_summary()
    assert summary['total_closed_trades'] == 1
    print('✅ State management working correctly')

    # Cleanup
    if os.path.exists(test_file):
        os.remove(test_file)

except Exception as e:
    print(f'❌ State Management error: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 6: Trade Journal
print('\n📔 Testing Trade Journal...')
try:
    journal = TradeJournal()
    journal.load_trades(pos_mgr.closed_positions)

    if journal.trades:
        stats = journal.analyze_performance()
        print(f'✅ Performance stats calculated: {stats.total_trades} trades')
        print(f'✅ Win rate: {stats.win_rate:.1f}%')
    else:
        print('✅ Journal initialized (no trades yet)')

except Exception as e:
    print(f'❌ Trade Journal error: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)

print('\n' + '='*70)
print('🎉 ALL TESTS PASSED!')
print('='*70)
print('✅ Imports: OK')
print('✅ Technical Indicators: OK')
print('✅ Chart Generation: OK')
print('✅ Risk Management: OK')
print('✅ State Management: OK')
print('✅ Trade Journal: OK')
print('='*70)
print('System Status: PRODUCTION READY ✅')
print('='*70)
