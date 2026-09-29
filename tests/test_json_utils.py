"""to_builtin: analysis payloads with numpy values must be JSON-safe (regression: /api/options/macro-context 500)."""

import json

import numpy as np
from fastapi.testclient import TestClient

from src.api.json_utils import to_builtin


def test_numpy_scalars_and_arrays_become_builtins():
    payload = {
        "outperforming": np.bool_(True),
        "count": np.int64(3),
        "ratio": np.float64(0.5),
        "series": np.array([1.0, 2.0]),
        "nested": [{"flag": np.bool_(False)}, (np.int32(1),)],
        np.int64(7): "numpy key",
    }
    out = to_builtin(payload)
    assert out["outperforming"] is True and out["nested"][0]["flag"] is False
    assert type(out["count"]) is int and type(out["ratio"]) is float
    assert out["series"] == [1.0, 2.0] and out["nested"][1] == [1]
    assert out[7] == "numpy key"
    json.dumps(out, allow_nan=False)  # must not raise


def test_non_finite_floats_become_none():
    assert to_builtin({"a": float("nan"), "b": np.float64("inf"), "c": 1.5}) == {"a": None, "b": None, "c": 1.5}


def test_macro_context_route_survives_numpy_values(monkeypatch):
    """The route used to return HTTP 500 'Unable to serialize unknown type: numpy.bool'."""
    from src.analysis.macro_context import MacroRegime
    from src.api.main import app

    context = {
        "vix": {"current_level": np.float64(16.2), "percentile": np.float64(27.3)},
        "sector_performance": {
            "sectors": {"XLK": {"outperforming": np.bool_(True), "relative_strength": np.float64(4.49)}}
        },
    }
    monkeypatch.setattr(MacroRegime, "get_comprehensive_context", lambda self: context)

    response = TestClient(app).get("/api/options/macro-context")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["sector_performance"]["sectors"]["XLK"]["outperforming"] is True
