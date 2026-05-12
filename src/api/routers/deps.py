"""Shared dependencies for API routers"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger
from datetime import datetime
from typing import Dict, Any, Optional, List
from pydantic import BaseModel
from fastapi import WebSocket

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
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: str


class UserComment(BaseModel):
    analysis_id: str
    comment: str
    user_id: Optional[str] = "anonymous"
    timestamp: Optional[str] = None


class RefinedAnalysisRequest(BaseModel):
    original_analysis: str
    user_comments: List[str]
    additional_context: Optional[Dict[str, Any]] = None
    focus_areas: Optional[List[str]] = None


class ChartAnalysisRequest(BaseModel):
    chart_data: Dict[str, Any]
    analysis_type: str = "technical"
    specific_questions: Optional[List[str]] = None


class ChatRequest(BaseModel):
    message: str
    context: Optional[Dict[str, Any]] = None
    symbol: Optional[str] = None
    conversation_history: Optional[List[Dict[str, str]]] = None


class ModelSelectionRequest(BaseModel):
    model_id: str
    provider: str = "lm_studio"


def get_current_timestamp() -> str:
    return datetime.now().isoformat()


def success_response(data: Any) -> MarketResponse:
    return MarketResponse(success=True, data=data, timestamp=get_current_timestamp())


def error_response(error: str) -> MarketResponse:
    return MarketResponse(success=False, error=error, timestamp=get_current_timestamp())
