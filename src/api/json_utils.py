"""Make analysis results safe to return from a JSON endpoint."""

import math
from typing import Any

import numpy as np


def to_builtin(obj: Any) -> Any:
    """Recursively convert numpy scalars/arrays to plain Python values.

    ``numpy.bool_`` (and ``numpy.int64`` in some paths) cannot be serialized by FastAPI/pydantic, and
    non-finite floats make ``JSONResponse`` raise, so NaN/inf become ``None``.
    """
    if isinstance(obj, dict):
        return {to_builtin(k): to_builtin(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_builtin(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return to_builtin(obj.tolist())
    if isinstance(obj, np.generic):
        return to_builtin(obj.item())
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    return obj
