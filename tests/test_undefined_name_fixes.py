"""T1: behavior tests for the code behind the F821 undefined-name fixes.

- ``ImbalanceDetector.detect_imbalances``: characterization tests. The
  method itself is intact; orphaned duplicate loop bodies (cherry-pick
  leftovers de-headed by a ruff F811 pass) sit after it in the file and
  are removed by T1 -- these tests pin the live behavior through that
  deletion.
- ``MiniMaxClient.validate_data``: the market-internals prompt referenced
  an undefined ``internals_data`` (NameError at runtime) instead of the
  ``data`` parameter.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.analysis.order_flow import Imbalance, ImbalanceDetector, VolumeBar


def _bar(ts: datetime, buy: float, sell: float) -> VolumeBar:
    total = buy + sell
    return VolumeBar(
        timestamp=ts,
        buy_volume=buy,
        sell_volume=sell,
        total_volume=total,
        delta=buy - sell,
        delta_percent=(buy - sell) / total * 100 if total else 0.0,
    )


class TestDetectImbalances:
    def test_buy_imbalance_detected_at_ratio(self):
        det = ImbalanceDetector(imbalance_ratio=3.0)
        t0 = datetime(2026, 9, 28, 9, 30)
        bars = [_bar(t0 + timedelta(minutes=5 * i), buy=300.0, sell=100.0) for i in range(6)]
        out = det.detect_imbalances(bars, lookback=5)
        assert out and all(imb.type == "buy" for imb in out)
        assert all(imb.ratio == pytest.approx(3.0) for imb in out)
        assert all(imb.strength == pytest.approx(50.0) for imb in out)

    def test_sell_imbalance_detected(self):
        det = ImbalanceDetector(imbalance_ratio=3.0)
        t0 = datetime(2026, 9, 28, 9, 30)
        bars = [_bar(t0 + timedelta(minutes=5 * i), buy=50.0, sell=400.0) for i in range(6)]
        out = det.detect_imbalances(bars, lookback=5)
        assert out and all(imb.type == "sell" for imb in out)
        assert all(imb.ratio == pytest.approx(8.0) for imb in out)

    def test_balanced_volume_yields_nothing(self):
        det = ImbalanceDetector(imbalance_ratio=3.0)
        t0 = datetime(2026, 9, 28, 9, 30)
        bars = [_bar(t0 + timedelta(minutes=5 * i), buy=100.0, sell=110.0) for i in range(6)]
        assert det.detect_imbalances(bars, lookback=5) == []

    def test_short_input_returns_empty(self):
        det = ImbalanceDetector()
        assert det.detect_imbalances([_bar(datetime(2026, 1, 1), 10, 1)], lookback=5) == []

    def test_candle_price_resolution(self):
        import pandas as pd

        det = ImbalanceDetector(imbalance_ratio=3.0)
        t0 = datetime(2026, 9, 28, 9, 30)
        bars = [_bar(t0 + timedelta(minutes=5 * i), buy=300.0, sell=100.0) for i in range(6)]
        idx = pd.DatetimeIndex([b.timestamp for b in bars])
        candles = pd.DataFrame({"close": [100.0 + i for i in range(len(bars))]}, index=idx)
        out = det.detect_imbalances(bars, candles=candles, lookback=5)
        assert out
        assert all(isinstance(imb, Imbalance) for imb in out)
        # Last window's timestamp resolves to its own candle close.
        assert out[-1].price == pytest.approx(105.0)


class TestMiniMaxValidateData:
    def _client(self):
        from src.llm.minimax_client import MiniMaxClient

        return MiniMaxClient()

    @pytest.mark.asyncio
    async def test_prompt_contains_data_and_parses_json(self, monkeypatch):
        client = self._client()
        captured: dict = {}

        async def _fake_completion(messages, **kw):
            captured["messages"] = messages
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"is_valid": false, "issues": ["vix=0"], '
                            '"confidence": 95, "recommendations": [], '
                            '"summary": "bad vix"}'
                        }
                    }
                ]
            }

        monkeypatch.setattr(client, "generate_completion", _fake_completion)

        payload = {"VIX": 0.0, "TICK": 123}
        result = await client.validate_data(payload, data_type="market_internals")

        user_prompt = captured["messages"][1]["content"]
        assert "VIX" in user_prompt and "0.0" in user_prompt, "prompt must contain the actual data payload"
        assert result == {
            "is_valid": False,
            "issues": ["vix=0"],
            "confidence": 95,
            "recommendations": [],
            "summary": "bad vix",
        }

    @pytest.mark.asyncio
    async def test_invalid_json_falls_back_to_default(self, monkeypatch):
        client = self._client()

        async def _fake_completion(messages, **kw):
            return {"choices": [{"message": {"content": "not json at all"}}]}

        monkeypatch.setattr(client, "generate_completion", _fake_completion)
        result = await client.validate_data({"SPY": 500.0}, data_type="market_internals")
        assert result["is_valid"] is True
        assert result["confidence"] == 80
