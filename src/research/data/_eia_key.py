"""EIA API key helper. Fail-fast if not configured."""
import os


def get_eia_api_key() -> str:
    key = os.environ.get("EIA_API_KEY")
    if not key:
        raise RuntimeError(
            "EIA_API_KEY not set. Register free at "
            "https://www.eia.gov/opendata/register"
        )
    return key
