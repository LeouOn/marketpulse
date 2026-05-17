"""API Key Authentication Middleware
Provides simple API key validation for protected endpoints
"""

from typing import Optional
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader
from loguru import logger

from ..core.config import get_settings


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def validate_api_key(api_key: Optional[str] = Security(api_key_header)) -> str:
    """
    Validate API key from header.

    Args:
        api_key: API key from X-API-Key header

    Returns:
        Valid API key

    Raises:
        HTTPException: If API key is invalid or missing
    """
    settings = get_settings()

    if not api_key:
        if not settings.api_keys_list:
            return "no-auth-required"
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Provide X-API-Key header."
        )

    if settings.validate_api_key(api_key):
        logger.debug(f"API key validated for request")
        return api_key

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid API key."
    )


async def optional_api_key(api_key: Optional[str] = Security(api_key_header)) -> Optional[str]:
    """
    Optional API key validation - doesn't fail if missing.

    Args:
        api_key: API key from X-API-Key header

    Returns:
        API key if valid, None otherwise
    """
    if not api_key:
        return None

    settings = get_settings()
    if settings.validate_api_key(api_key):
        return api_key
    return None