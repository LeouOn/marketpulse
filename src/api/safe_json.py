"""Safe JSON response class + error-message hygiene for the API.

``SafeJSONResponse`` is drop-in compatible with Starlette's ``JSONResponse``
(byte-identical for every payload that serializes today) and never raises
for non-finite floats. **Reach caveat:** as ``default_response_class`` it only
sees what FastAPI's ``jsonable_encoder`` lets through — that pass converts
datetime/Decimal/set itself and passes plain floats (so NaN/inf in a plain-
dict return are nulled here), but it *raises* on numpy values before the
response class renders, so numpy in a plain dict still 500s. The numpy rescue
is the ``MarketResponse`` response-model validator (``to_builtin`` before
pydantic serializes) or returning an explicit ``SafeJSONResponse`` — whose
``render`` also handles datetime/date (isoformat), Decimal, set and pandas
Timestamp/NaT. It reuses :func:`src.api.json_utils.to_builtin` for the
numpy/non-finite pass rather than duplicating it. pandas ``Series``/
``DataFrame`` are NOT supported.

``public_error_message`` and ``new_error_id`` back the central error layer:
client-facing messages for expected (client-error) exceptions only, a fixed
generic text for everything else, and a short id to correlate the logged
traceback with the generic message the client saw.
"""

from __future__ import annotations

import json
import math
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pandas as pd
from fastapi import HTTPException
from loguru import logger
from starlette.responses import JSONResponse

from src.api.json_utils import to_builtin

_GENERIC_ERROR_TEXT = "Internal server error"


def _prepare(obj: Any) -> Any:
    """Convert the few remaining types ``json.dumps`` cannot carry.

    Applied AFTER ``to_builtin`` (which already handled numpy and non-finite
    floats), so anything that already serializes passes through untouched.
    """
    if isinstance(obj, dict):
        return {_prepare(k): _prepare(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):  # sets were already listified by to_builtin
        return [_prepare(v) for v in obj]
    if isinstance(obj, Decimal):
        number = float(obj)  # Decimal("NaN")/Infinity -> float non-finite -> null below
        return number if math.isfinite(number) else None
    if obj is pd.NaT:  # NaT subclasses datetime and would otherwise isoformat to "NaT"
        return None
    if isinstance(obj, datetime):  # also covers pandas.Timestamp
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None  # non-finite float dict keys land here too
    return obj


class SafeJSONResponse(JSONResponse):
    """``JSONResponse`` that cannot fail on non-finite floats.

    Ordinary payloads render byte-identically to Starlette's ``JSONResponse``
    (same ``json.dumps`` arguments). Content rejected by the ordinary encoder
    passes through ``to_builtin`` and ``_prepare`` so NaN/inf (any depth,
    incl. numpy) become ``null`` and datetime/Decimal/set/Timestamp values
    become serializable.
    """

    def render(self, content: Any) -> bytes:
        dumps_args = {
            "ensure_ascii": False,
            "allow_nan": False,
            "indent": None,
            "separators": (",", ":"),
        }
        try:
            # Fast path: identical to starlette's JSONResponse for everything
            # json can already carry. Avoid a Python tree walk on ordinary data.
            return json.dumps(content, **dumps_args).encode("utf-8")
        except (TypeError, ValueError):
            # datetime/date/Decimal/set/NaT/... are still in the content;
            # convert ONLY what json cannot carry and retry once.
            pass
        return json.dumps(_prepare(to_builtin(content)), **dumps_args).encode("utf-8")


def public_error_message(
    exc: BaseException,
    *,
    expected: tuple[type[BaseException], ...] = (ValueError,),
) -> str:
    """Client-facing message for an exception.

    For an instance of an *expected* (client-error) type, ``str(exc)`` trimmed
    to 300 characters. For anything else, the fixed generic text — never a
    traceback, file path, class path or a repr of unknown objects.
    """
    # Contract: ValueError text (<=300 chars) is exposed by design for callers
    # passing expected=(ValueError,); unexpected_error() passes expected=().
    if isinstance(exc, expected):
        return str(exc)[:300]
    return _GENERIC_ERROR_TEXT


def new_error_id() -> str:
    """Short correlation id linking a logged traceback to the generic client message."""
    return uuid.uuid4().hex[:12]


def unexpected_error(exc: BaseException) -> dict[str, str]:
    """Log an internal failure and expose only its generic message and id.

    Unlike deliberate validation paths, catch-all failures must never treat
    ValueError (or any other exception type) as permission to expose its text.
    """
    error_id = new_error_id()
    logger.opt(exception=(type(exc), exc, exc.__traceback__)).error("Internal error {}", error_id)
    return {"error": public_error_message(exc, expected=()), "error_id": error_id}


def internal_http_error(exc: BaseException) -> HTTPException:
    """Safe 500 for routers, including when mounted on a standalone test app."""
    error = unexpected_error(exc)
    return HTTPException(500, detail=error["error"], headers={"X-Error-ID": error["error_id"]})
