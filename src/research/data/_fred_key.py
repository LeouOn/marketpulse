"""FRED API key helper. Fail-fast if not configured.

Lookup order (env -> .env -> config/credentials.yaml) lives in ``src.core.keys``.
"""

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src.core.keys import require_macro_key  # noqa: E402


def get_fred_api_key() -> str:
    return require_macro_key("FRED_API_KEY")
