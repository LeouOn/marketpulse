"""Follow-up completions (2026-09-29 owner decisions):

- TradeJournal.get_insights now includes ``session_rankings`` mirroring
  ``setup_rankings`` -- the ``analyze_by_session`` result was computed and
  discarded (plus a wasted pass over the trades).
- StrategyBuilder.generate_strategy_comparison now also returns a
  covered-call entry at the ATM strike -- the strike was computed and the
  strategy never built.
"""

from __future__ import annotations

from datetime import datetime

from src.analysis.strategy_builder import StrategyBuilder
from src.journal.trade_tracker import TradeJournal
from src.state.position_manager import Position, PositionSide, PositionStatus


def _trade(session: str, pnl: float, setup: str = "FVG_FILL") -> Position:
    return Position(
        id=f"t-{session}-{pnl}",
        symbol="NQ=F",
        side=PositionSide.LONG,
        entry_price=100.0,
        stop_loss=99.0,
        take_profit=102.0,
        contracts=1,
        entry_timestamp=datetime.now(),
        exit_timestamp=datetime.now(),
        status=PositionStatus.CLOSED,
        realized_pnl=pnl,
        setup_type=setup,
        session=session,
    )


class TestSessionRankings:
    def test_get_insights_includes_session_rankings(self):
        journal = TradeJournal()
        journal.add_trade(_trade("London", 100.0))
        journal.add_trade(_trade("London", 50.0))
        journal.add_trade(_trade("NY_Open", -40.0))

        insights = journal.get_insights(days=30)

        assert "session_rankings" in insights
        by_session = {r["session"]: r for r in insights["session_rankings"]}
        assert set(by_session) == {"London", "NY_Open"}
        assert by_session["London"]["trades"] == 2
        assert by_session["London"]["win_rate"] == "100.0%"
        assert by_session["London"]["pnl"] == "$+150.00"
        assert by_session["NY_Open"]["trades"] == 1
        assert by_session["NY_Open"]["win_rate"] == "0.0%"

    def test_setup_rankings_still_present(self):
        journal = TradeJournal()
        journal.add_trade(_trade("London", 100.0, setup="FVG_FILL"))
        journal.add_trade(_trade("London", -20.0, setup="ORDER_BLOCK"))

        insights = journal.get_insights(days=30)

        assert "setup_rankings" in insights
        assert len(insights["setup_rankings"]) == 2


class _FakeYahoo:
    """Only the two methods generate_strategy_comparison uses."""

    def get_single_symbol_data(self, symbol):
        return {"price": 100.0}

    def get_options_chain(self, symbol, expiration):
        strikes = [90.0, 95.0, 99.0, 100.0, 101.0, 105.0, 110.0]
        calls = [{"strike": s, "bid": 0.5, "ask": 0.6, "lastPrice": 0.55} for s in strikes]
        return {
            "symbol": symbol,
            "expiration": expiration,
            "underlying_price": 100.0,
            "calls": calls,
            "puts": [],
        }


class TestCoveredCall:
    def test_comparison_includes_atm_covered_call(self):
        builder = StrategyBuilder(_FakeYahoo())

        out = builder.generate_strategy_comparison("SPY", "2026-12-18")

        strategies = {s["type"]: s for s in out["strategies"]}
        assert "covered_call" in strategies
        cc = strategies["covered_call"]
        assert cc["strike"] == 100.0, "ATM strike must be closest to the stock price"
        assert cc["premium_bid"] == 0.5
        assert cc["premium_ask"] == 0.6

    def test_otm_bull_spread_still_generated(self):
        builder = StrategyBuilder(_FakeYahoo())

        out = builder.generate_strategy_comparison("SPY", "2026-12-18")

        strategies = {s["type"]: s for s in out["strategies"]}
        assert "bull_call_spread" in strategies
        assert strategies["bull_call_spread"]["long_strike"] == 101.0
        assert strategies["bull_call_spread"]["short_strike"] == 105.0
