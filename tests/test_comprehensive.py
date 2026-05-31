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
import os
import uuid
from pathlib import Path
from datetime import datetime

import pytest
import numpy as np
import pandas as pd

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class TestImports:
    def test_all_modules_import(self):
        from src.analysis.technical_indicators import TechnicalIndicators
        from src.visualization.chart_generator import ChartGenerator
        from src.api.yahoo_client import YahooFinanceClient
        from src.analysis.risk_manager import RiskManager
        from src.state.position_manager import PositionManager
        from src.journal.trade_tracker import TradeJournal
        from src.alerts.alert_manager import AlertManager
        from src.analysis.ict_concepts import FairValueGapDetector
        assert all([TechnicalIndicators, ChartGenerator, YahooFinanceClient,
                     RiskManager, PositionManager, TradeJournal,
                     AlertManager, FairValueGapDetector])


class TestTechnicalIndicators:
    @pytest.fixture
    def sample_df(self):
        np.random.seed(42)
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
        return df

    def test_calculate_all_indicators(self, sample_df):
        from src.analysis.technical_indicators import TechnicalIndicators
        indicators = ['sma_20', 'ema_21', 'rsi', 'macd', 'bollinger', 'atr', 'vwap', 'supertrend']
        df_ind = TechnicalIndicators.calculate_all(sample_df, indicators)
        assert 'sma_20' in df_ind.columns
        assert 'rsi' in df_ind.columns
        assert 'macd' in df_ind.columns


class TestChartGeneration:
    @pytest.fixture
    def sample_df(self):
        np.random.seed(42)
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
        return df

    def test_candlestick_chart(self, sample_df):
        from src.visualization.chart_generator import ChartGenerator
        chart_gen = ChartGenerator(theme='dark')
        fig = chart_gen.create_candlestick_chart(sample_df, indicators=['sma_20', 'ema_21'])
        assert fig is not None

    def test_indicator_panel(self, sample_df):
        from src.visualization.chart_generator import ChartGenerator
        chart_gen = ChartGenerator(theme='dark')
        fig = chart_gen.create_indicator_panel(sample_df)
        assert fig is not None

    def test_market_heatmap(self):
        from src.visualization.chart_generator import ChartGenerator
        chart_gen = ChartGenerator(theme='dark')
        heatmap_data = {'Tech': 2.5, 'Finance': -1.2, 'Healthcare': 0.8, 'Energy': -0.5}
        fig = chart_gen.create_market_heatmap(heatmap_data)
        assert fig is not None


class TestRiskManagement:
    def test_good_trade_approved(self):
        from src.analysis.risk_manager import RiskManager
        risk_mgr = RiskManager(account_size=10000, max_daily_loss=500, max_position_risk=250)
        validation = risk_mgr.validate_trade(
            symbol='MNQ', entry_price=15850, stop_loss=15840,
            take_profit=15870, direction='long', contracts=2
        )
        assert validation.approved is True

    def test_excessive_risk_rejected(self):
        from src.analysis.risk_manager import RiskManager
        risk_mgr = RiskManager(account_size=10000, max_daily_loss=500, max_position_risk=250)
        validation = risk_mgr.validate_trade(
            symbol='MNQ', entry_price=15850, stop_loss=15800,
            take_profit=15900, direction='long', contracts=4
        )
        assert validation.approved is False

    def test_position_sizing(self):
        from src.analysis.risk_manager import RiskManager
        risk_mgr = RiskManager(account_size=10000, max_daily_loss=500, max_position_risk=250)
        contracts = risk_mgr.calculate_position_size(
            entry_price=15850, stop_loss=15840,
            direction='long', point_value=2.0
        )
        assert contracts > 0


class TestStateManagement:
    def test_position_lifecycle(self):
        from src.state.position_manager import PositionManager, Position, PositionSide, PositionStatus
        test_file = 'data/state/test_comprehensive_state.json'
        if os.path.exists(test_file):
            os.remove(test_file)

        pos_mgr = PositionManager(state_file=test_file)
        pos = Position(
            id=str(uuid.uuid4()), symbol='MNQ', side=PositionSide.LONG,
            entry_price=15850, stop_loss=15840, take_profit=15870,
            contracts=2, entry_timestamp=datetime.now(), status=PositionStatus.OPEN
        )
        pos_mgr.add_position(pos)
        closed = pos_mgr.close_position(pos.id, exit_price=15870)
        assert closed.realized_pnl == 80.0

        summary = pos_mgr.get_state_summary()
        assert summary['total_closed_trades'] == 1

        if os.path.exists(test_file):
            os.remove(test_file)


class TestTradeJournal:
    def test_journal_with_trades(self):
        from src.state.position_manager import PositionManager, Position, PositionSide, PositionStatus
        from src.journal.trade_tracker import TradeJournal

        test_file = 'data/state/test_journal_state.json'
        if os.path.exists(test_file):
            os.remove(test_file)

        pos_mgr = PositionManager(state_file=test_file)
        pos = Position(
            id=str(uuid.uuid4()), symbol='MNQ', side=PositionSide.LONG,
            entry_price=15850, stop_loss=15840, take_profit=15870,
            contracts=2, entry_timestamp=datetime.now(), status=PositionStatus.OPEN
        )
        pos_mgr.add_position(pos)
        pos_mgr.close_position(pos.id, exit_price=15870)

        journal = TradeJournal()
        journal.load_trades(pos_mgr.closed_positions)
        if journal.trades:
            stats = journal.analyze_performance()
            assert stats.total_trades >= 1

        if os.path.exists(test_file):
            os.remove(test_file)
