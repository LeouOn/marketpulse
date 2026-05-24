"""Shared dependencies for API routers"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from datetime import datetime
from typing import Any

from loguru import logger
from pydantic import BaseModel

from src.core.config import get_settings

settings = get_settings()

try:
    from src.data.market_collector import MarketPulseCollector
except Exception as e:
    logger.warning(f"Could not import MarketPulseCollector: {e}")
    MarketPulseCollector = None

try:
    from src.core.database import DatabaseManager
except Exception as e:
    logger.warning(f"Could not import DatabaseManager: {e}")
    DatabaseManager = None

try:
    from src.llm.llm_client import LLMManager, LMStudioClient
except Exception as e:
    logger.warning(f"Could not import LLM modules: {e}")
    LLMManager = None
    LMStudioClient = None

try:
    from src.analysis.ohlc_analyzer import OHLCAnalyzer
except Exception as e:
    logger.warning(f"Could not import OHLCAnalyzer: {e}")
    OHLCAnalyzer = None

collector = None
ohlc_analyzer = None
model_cache = {"models": None, "timestamp": None, "cache_duration": 300}
db_manager = DatabaseManager(settings.database_url) if DatabaseManager else None


class MarketResponse(BaseModel):
    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    timestamp: str


class UserComment(BaseModel):
    analysis_id: str
    comment: str
    user_id: str | None = "anonymous"
    timestamp: str | None = None


class RefinedAnalysisRequest(BaseModel):
    original_analysis: str
    user_comments: list[str]
    additional_context: dict[str, Any] | None = None
    focus_areas: list[str] | None = None


class ChartAnalysisRequest(BaseModel):
    chart_data: dict[str, Any]
    analysis_type: str = "technical"
    specific_questions: list[str] | None = None


class ChatRequest(BaseModel):
    message: str
    context: dict[str, Any] | None = None
    symbol: str | None = None
    conversation_history: list[dict[str, str]] | None = None


class ModelSelectionRequest(BaseModel):
    model_id: str
    provider: str = "lm_studio"


def get_current_timestamp() -> str:
    return datetime.now().isoformat()


def success_response(data: Any) -> MarketResponse:
    return MarketResponse(success=True, data=data, timestamp=get_current_timestamp())


def error_response(error: str) -> MarketResponse:
    return MarketResponse(success=False, error=error, timestamp=get_current_timestamp())
