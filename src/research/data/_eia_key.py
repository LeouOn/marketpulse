"""EIA API key helper. Fail-fast if not configured.

Lookup order (env -> .env -> config/credentials.yaml) lives in ``src.core.keys``.
"""
from src.core.keys import require_macro_key


def get_eia_api_key() -> str:
    return require_macro_key("EIA_API_KEY")
