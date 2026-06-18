"""FRED API key helper. Fail-fast if not configured."""
import os


def get_fred_api_key() -> str:
    key = os.environ.get("FRED_API_KEY")
    if not key:
        raise RuntimeError(
            "FRED_API_KEY not set. Register free at "
            "https://fredaccount.stlouisfed.org/apikeys"
        )
    return key
