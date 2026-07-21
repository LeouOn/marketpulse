"""LLM chat and analysis endpoints"""

import asyncio
import contextlib
import json
from datetime import datetime

from fastapi import APIRouter
from loguru import logger

from src.llm.enhanced_llm_client import EnhancedLLMClient
from src.llm.trading_knowledge_rag import get_trading_rag

from . import deps as _deps
from .deps import (
    ChartAnalysisRequest,
    ChatRequest,
    EnhancedAnalysisRequest,
    LMStudioClient,
    MarketResponse,
    ModelSelectionRequest,
    RefinedAnalysisRequest,
    RetrieveContextRequest,
    TestHypothesisRequest,
    UserComment,
    model_cache,
    settings,
)

router = APIRouter(prefix="/api/llm", tags=["llm"])

# ---------------------------------------------------------------------------
# Shared router-backed client -- reuses sessions across requests
# ---------------------------------------------------------------------------

_shared_router = None
_shared_router_lock = asyncio.Lock()
_selected_model: str | None = None  # User-overridden model preference


async def _get_router():
    """Get or create a shared ModelRouter (reuses provider sessions)."""
    global _shared_router

    if _shared_router is not None and _shared_router._entered:
        return _shared_router

    async with _shared_router_lock:
        if _shared_router is not None and _shared_router._entered:
            return _shared_router

        from src.llm.model_router import ModelRouter

        _shared_router = ModelRouter(settings)
        await _shared_router.__aenter__()
        logger.info("Created shared ModelRouter")

    return _shared_router


async def _get_llm_client() -> LMStudioClient:
    """Legacy helper -- returns LMStudioClient for backward compat.

    New code should use ``_get_router()`` instead.
    """
    client = LMStudioClient()
    await client.__aenter__()
    return client


async def _get_cached_market_context() -> str:
    """Fetch cached market internals and format as LLM context string."""
    collector = _deps.collector
    if not collector:
        return ""

    try:
        internals = await asyncio.wait_for(
            collector.collect_market_internals(),
            timeout=10.0,
        )

        if not internals:
            return ""

        lines = ["[LIVE MARKET DATA from cache]"]

        symbol_labels = {
            "spy": "SPY (S&P 500)",
            "qqq": "QQQ (Nasdaq 100)",
            "iwm": "IWM (Russell 2000)",
            "vix": "VIX (Volatility)",
            "nq=f": "NQ Futures",
            "btc-usd": "BTC/USD",
            "eth-usd": "ETH/USD",
        }

        for key in ["spy", "qqq", "iwm", "vix", "nq=f", "btc-usd", "eth-usd"]:
            data = internals.get(key)
            if not data or not isinstance(data, dict):
                continue
            label = symbol_labels.get(key, key.upper())
            price = data.get("price", "N/A")
            change = data.get("change", "N/A")
            change_pct = data.get("change_pct", "N/A")
            volume = data.get("volume", "N/A")
            sign = "+" if isinstance(change, (int, float)) and change >= 0 else ""
            lines.append(f"  {label}: ${price} | {sign}{change} ({sign}{change_pct}%) | Vol: {volume}")

        if "data_source" in internals:
            lines.append(f"  Data Source: {internals['data_source']}")
        if "data_quality" in internals:
            lines.append(f"  Data Quality: {internals['data_quality']}")

        return "\n".join(lines) + "\n"

    except TimeoutError:
        logger.warning("Timed out fetching cached market data for chat context")
        return ""

    except Exception as e:
        logger.warning(f"Could not fetch cached market data for chat context: {e}")
        return ""


@router.post("/chat", response_model=MarketResponse)
async def chat_with_llm(request: ChatRequest):
    """Chat with the LLM trading assistant"""
    try:
        system_prompt = """You are a professional AI trading assistant. You help users analyze market conditions,
        understand trading strategies, and provide insights about financial markets. Always be helpful,
        educational, and responsible with your advice. Never provide guaranteed financial advice.

        When users ask about market data, reference the provided context. When you don't have specific data,
        acknowledge the limitations and provide general guidance."""

        context_info = ""

        if request.context:
            context_data = request.context
            context_info = f"Current Market Context:\n{json.dumps(context_data, indent=2)}\n\n"

            if "detected_symbols" in context_data and context_data["detected_symbols"]:
                detected_syms = context_data["detected_symbols"]
                context_info += f"Symbols Mentioned: {', '.join(detected_syms)}\n"

            if "query_type" in context_data:
                query_type = context_data["query_type"]
                context_info += f"Query Type: {query_type}\n"

                if query_type == "trend_analysis":
                    context_info += "Focus on trend direction, momentum, and price patterns.\n"
                elif query_type == "technical_levels":
                    context_info += "Focus on support/resistance levels and price targets.\n"
                elif query_type == "volatility_analysis":
                    context_info += "Focus on volatility patterns, risk assessment, and timing.\n"
                elif query_type == "trading_strategy":
                    context_info += "Focus on actionable strategies, entries, exits, and risk management.\n"
                elif query_type == "symbol_specific":
                    context_info += "Focus analysis on the detected symbols mentioned.\n"

        if request.symbol:
            context_info += f"Primary Symbol: {request.symbol}\n"

        cached_market = await _get_cached_market_context()
        if cached_market:
            context_info += f"\n{cached_market}\n"

        messages = []
        messages.append({"role": "system", "content": system_prompt})

        if request.conversation_history:
            for msg in request.conversation_history[-6:]:
                messages.append({"role": msg["role"], "content": msg["content"]})

        if context_info:
            messages.append({"role": "system", "content": context_info})

        messages.append({"role": "user", "content": request.message})

        response_text = None

        try:
            router = await _get_router()

            # Use user-selected model if set, otherwise route by capability
            if _selected_model:
                # Route to the provider that owns this model
                client, model_id = await router.route("standard")

                # Override model if the selected one is on a known provider
                if "deepseek" in (_selected_model or "").lower():
                    client, model_id = await router.route("standard")
                    model_id = _selected_model

                logger.info(f"LLM chat: model={model_id} (user-selected), msgs={len(messages)}")
            else:
                client, model_id = await router.route("standard")
                logger.info(f"LLM chat: model={model_id} (auto-routed), msgs={len(messages)}")

            response = await asyncio.wait_for(
                client.generate_completion(
                    messages=messages,
                    model=model_id or None,
                    max_tokens=600,
                    temperature=0.7,
                ),
                timeout=180.0,
            )

            if response and "choices" in response and len(response["choices"]) > 0:
                response_text = response["choices"][0]["message"]["content"]
                logger.info(f"LLM chat success: {len(response_text)} chars")

        except TimeoutError:
            logger.error("LLM request timed out after 3 minutes")
            return MarketResponse(
                success=False,
                error="The AI request timed out after 3 minutes. The query might be too complex or the AI service is overloaded. Please try again with a simpler question.",
                timestamp=datetime.now().isoformat(),
            )

        except Exception as e:
            logger.error(f"LLM error: {type(e).__name__}: {e}")

            # Reset shared router on error so next request creates a fresh one
            global _shared_router

            if _shared_router:
                with contextlib.suppress(Exception):
                    await _shared_router.__aexit__(None, None, None)
                _shared_router = None

        if not response_text:
            logger.warning("LM Studio failed, providing fallback response")
            message_lower = request.message.lower()

            if "trend" in message_lower and request.symbol:
                response_text = f"I apologize, but I'm having trouble connecting to my AI analysis service right now. However, I can tell you that for {request.symbol}, you should look at multiple timeframes to determine the current trend. Check for higher highs and higher lows for an uptrend, or lower highs and lower lows for a downtrend."

            elif "market" in message_lower:
                response_text = "I apologize, but I'm having trouble connecting to my AI analysis service right now. For general market analysis, I recommend looking at the major indices (SPY, QQQ), volatility (VIX), and market breadth indicators to get a complete picture of market conditions."

            elif "buy" in message_lower or "sell" in message_lower:
                response_text = "I apologize, but I'm having trouble connecting to my AI analysis service right now. Remember that trading decisions should be based on your own analysis, risk tolerance, and strategy. Always use proper risk management and never risk more than you're willing to lose."

            else:
                response_text = "I apologize, but I'm having trouble connecting to my AI analysis service right now. This could be due to technical difficulties with the LM Studio service. Please check if LM Studio is running and try again in a moment."

        return MarketResponse(success=True, data={"response": response_text}, timestamp=datetime.now().isoformat())

    except Exception as e:
        logger.error(f"Error in LLM chat: {type(e).__name__}: {e}")

        # Always return a proper response, never let FastAPI generate a 500
        return MarketResponse(
            success=False,
            error=f"An error occurred while processing your request: {str(e)}",
            timestamp=datetime.now().isoformat(),
        )


@router.get("/models", response_model=MarketResponse)
async def get_available_models():
    """Get available models from all providers (DeepSeek + LM Studio)."""
    try:
        import aiohttp

        current_time = datetime.now().timestamp()

        # Return cached result if fresh
        if (
            model_cache["models"]
            and model_cache["timestamp"]
            and current_time - model_cache["timestamp"] < model_cache["cache_duration"]
        ):
            return MarketResponse(
                success=True,
                data={
                    "models": model_cache["models"],
                    "cached": True,
                    "cache_age": int(current_time - model_cache["timestamp"]),
                    "provider": "multi",
                },
                timestamp=datetime.now().isoformat(),
            )

        models: list[dict] = []

        # --- DeepSeek models (from config) ---
        ds = settings.llm.deepseek
        ds_configured = bool(ds.api_key and ds.api_key not in ("your_deepseek_api_key", ""))

        models.append(
            {
                "id": ds.model_pro,
                "provider": "deepseek",
                "capability": "reasoning",
                "description": "DeepSeek V4 Pro -- full reasoning, function calling, 128K context",
                "recommended": True,
                "configured": ds_configured,
            }
        )

        models.append(
            {
                "id": ds.model_flash,
                "provider": "deepseek",
                "capability": "fast",
                "description": "DeepSeek V4 Flash -- fast, cost-effective, 128K context",
                "recommended": False,
                "configured": ds_configured,
            }
        )

        # --- LM Studio models (live probe, non-blocking) ---
        try:
            async with (
                aiohttp.ClientSession() as session,
                session.get(
                    f"{settings.llm.primary.base_url}/models",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as response,
            ):
                if response.status == 200:
                    lm_data = await response.json()
                    loaded_ids = [m.get("id") for m in lm_data.get("data", [])]
                    for model_id in loaded_ids:
                        models.append(
                            {
                                "id": model_id,
                                "provider": "lm_studio",
                                "capability": "fallback",
                                "description": f"Local model: {model_id}",
                                "recommended": False,
                                "configured": True,
                            }
                        )

        except Exception as lm_error:
            logger.debug(f"LM Studio model probe skipped: {lm_error}")

            # Add a placeholder for the local provider
            models.append(
                {
                    "id": "lm-studio-local",
                    "provider": "lm_studio",
                    "capability": "fallback",
                    "description": "Local model via LM Studio (auto-detected when running)",
                    "recommended": False,
                    "configured": False,
                }
            )

        # Cache and return
        model_cache["models"] = models
        model_cache["timestamp"] = current_time

        return MarketResponse(
            success=True,
            data={
                "models": models,
                "cached": False,
                "cache_age": 0,
                "provider": "multi",
                "total_count": len(models),
                "primary_provider": settings.llm.model_routing.primary_provider,
            },
            timestamp=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"Error fetching models: {e}")
        return MarketResponse(success=False, error=str(e), timestamp=datetime.now().isoformat())


def _infer_provider(model_id: str) -> str:
    """Infer which provider owns a model ID."""
    if not model_id:
        return "unknown"
    mid = model_id.lower()
    if "deepseek" in mid:
        return "deepseek"
    if "gpt" in mid or "openai" in mid:
        return "openrouter"
    return "lm_studio"


def _estimate_model_size(model_id: str) -> str:
    model_id_lower = model_id.lower()

    if "42b" in model_id_lower or "70b" in model_id_lower:
        return "42B-70B"

    elif "32b" in model_id_lower or "36b" in model_id_lower:
        return "32B-36B"

    elif "24b" in model_id_lower or "27b" in model_id_lower:
        return "24B-27B"

    elif "18b" in model_id_lower:
        return "18B"

    elif "14b" in model_id_lower or "12b" in model_id_lower:
        return "12B-14B"

    elif "8b" in model_id_lower:
        return "8B"

    else:
        return "Unknown"


@router.post("/select-model", response_model=MarketResponse)
async def select_model(request: ModelSelectionRequest):
    """Select a specific model for LLM chat"""
    try:
        models_response = await get_available_models()

        if models_response.success and models_response.data:
            available_models = models_response.data.get("models", [])
            model_ids = [model["id"] for model in available_models]

            if request.model_id not in model_ids:
                return MarketResponse(
                    success=False,
                    error=f"Model '{request.model_id}' not available. Available models: {', '.join(model_ids[:5])}...",
                    timestamp=datetime.now().isoformat(),
                )

        # Store user preference for subsequent chat requests
        global _selected_model

        _selected_model = request.model_id
        logger.info(f"User selected model: {request.model_id}")

        return MarketResponse(
            success=True,
            data={
                "selected_model": request.model_id,
                "provider": request.provider or _infer_provider(request.model_id),
                "message": f"Model '{request.model_id}' selected successfully",
            },
            timestamp=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"Error selecting model: {e}")
        return MarketResponse(success=False, error=str(e), timestamp=datetime.now().isoformat())


@router.get("/model-status", response_model=MarketResponse)
async def get_model_status():
    """Get multi-provider model status (DeepSeek + LM Studio + OpenRouter)."""
    try:
        import aiohttp

        ds = settings.llm.deepseek
        ds_configured = bool(ds.api_key and ds.api_key not in ("your_deepseek_api_key", ""))

        status_info = {
            "providers": {
                "deepseek": {
                    "configured": ds_configured,
                    "endpoint": ds.base_url,
                    "model_pro": ds.model_pro,
                    "model_flash": ds.model_flash,
                },
                "lm_studio": {
                    "connected": False,
                    "endpoint": settings.llm.primary.base_url,
                    "loaded_models": [],
                },
            },
            "routing": {
                "primary_provider": settings.llm.model_routing.primary_provider,
                "fallback_providers": settings.llm.model_routing.fallback_providers,
                "selected_model": _selected_model,
            },
            "last_check": datetime.now().isoformat(),
        }

        # Probe LM Studio (non-blocking)
        try:
            start_time = datetime.now().timestamp()
            async with (
                aiohttp.ClientSession() as session,
                session.get(
                    f"{settings.llm.primary.base_url}/models",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as response,
            ):
                if response.status == 200:
                    status_info["providers"]["lm_studio"]["connected"] = True
                    status_info["providers"]["lm_studio"]["response_time_ms"] = int(
                        (datetime.now().timestamp() - start_time) * 1000
                    )
                    md = await response.json()
                    status_info["providers"]["lm_studio"]["loaded_models"] = [m["id"] for m in md.get("data", [])]
        except Exception as e:
            logger.debug(f"LM Studio status probe: {e}")

        return MarketResponse(success=True, data=status_info, timestamp=datetime.now().isoformat())

    except Exception as e:
        logger.error(f"Error getting model status: {e}")
        return MarketResponse(success=False, error=str(e), timestamp=datetime.now().isoformat())


@router.post("/comment", response_model=MarketResponse)
async def add_user_comment(comment: UserComment):
    """Add user comment to LLM analysis"""
    try:
        comment_data = {
            "analysis_id": comment.analysis_id,
            "user_id": comment.user_id,
            "comment": comment.comment,
            "timestamp": comment.timestamp or datetime.now().isoformat(),
        }

        db_manager = _deps.db_manager
        if db_manager:
            db_manager.save_user_comment(comment_data)

        return MarketResponse(
            success=True,
            data={"message": "Comment added successfully", "comment_id": comment.analysis_id},
            timestamp=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"Error adding comment: {e}")
        return MarketResponse(success=False, error=str(e), timestamp=datetime.now().isoformat())


@router.post("/refine", response_model=MarketResponse)
async def refine_analysis(request: RefinedAnalysisRequest):
    """Refine LLM analysis based on user comments"""
    try:
        comments_text = "\n".join([f"- {comment}" for comment in request.user_comments])
        focus_text = f"Focus on: {', '.join(request.focus_areas)}" if request.focus_areas else ""

        refinement_prompt = f"""
        Original Analysis:

        {request.original_analysis}

        User Comments/Feedback:

        {comments_text}

        {focus_text}

        Please refine the analysis addressing the user feedback.
        Provide an improved analysis that incorporates their perspectives
        and focuses on the areas they mentioned.

        Additional Context:

        {json.dumps(request.additional_context, indent=2) if request.additional_context else "None"}

        Provide a refined, more accurate analysis.

        """

        messages = [{"role": "user", "content": refinement_prompt}]

        async with LMStudioClient() as client:
            response = await client.generate_completion(
                model="deep_analysis", messages=messages, max_tokens=400, temperature=0.4
            )

            if response and "choices" in response:
                refined_analysis = response["choices"][0]["message"]["content"]

                return MarketResponse(
                    success=True,
                    data={
                        "refined_analysis": refined_analysis,
                        "original_analysis": request.original_analysis,
                        "user_comments_count": len(request.user_comments),
                    },
                    timestamp=datetime.now().isoformat(),
                )

        return MarketResponse(
            success=False, error="Failed to generate refined analysis", timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error refining analysis: {e}")
        return MarketResponse(success=False, error=str(e), timestamp=datetime.now().isoformat())


@router.post("/analyze-chart", response_model=MarketResponse)
async def analyze_chart(request: ChartAnalysisRequest):
    """Analyze text-encoded chart data"""
    try:
        async with LMStudioClient() as client:
            analysis = await client.interpret_text_chart_data(request.chart_data)

            if analysis:
                return MarketResponse(
                    success=True,
                    data={
                        "chart_analysis": analysis,
                        "symbol": request.chart_data.get("symbol"),
                        "timeframe": request.chart_data.get("timeframe"),
                    },
                    timestamp=datetime.now().isoformat(),
                )

            else:
                return MarketResponse(
                    success=False, error="Failed to analyze chart data", timestamp=datetime.now().isoformat()
                )

    except Exception as e:
        logger.error(f"Error analyzing chart: {e}")
        return MarketResponse(success=False, error=str(e), timestamp=datetime.now().isoformat())


@router.get("/validation/sanity-check", response_model=MarketResponse)
async def run_sanity_check():
    """Run sanity check on current market data"""
    try:
        collector = _deps.collector

        if not collector:
            return MarketResponse(
                success=False, error="Collector not initialized", timestamp=datetime.now().isoformat()
            )

        internals = await collector.collect_market_internals()

        if not internals:
            return MarketResponse(
                success=False, error="No market data available for validation", timestamp=datetime.now().isoformat()
            )

        async with LMStudioClient() as client:
            validation_result = await client.validate_data_interpretation(internals, "market_internals")

            return MarketResponse(
                success=True,
                data={"validation_result": validation_result, "market_data": internals},
                timestamp=datetime.now().isoformat(),
            )

    except Exception as e:
        logger.error(f"Error running sanity check: {e}")
        return MarketResponse(success=False, error=str(e), timestamp=datetime.now().isoformat())


@router.get("/conversation-history/{analysis_id}", response_model=MarketResponse)
async def get_conversation_history(analysis_id: str):
    """Get conversation history for an analysis"""
    try:
        db_manager = _deps.db_manager
        history = db_manager.get_analysis_conversation(analysis_id) if db_manager else []

        return MarketResponse(
            success=True,
            data={
                "analysis_id": analysis_id,
                "conversation_history": history,
                "turns_count": len(history) if history else 0,
            },
            timestamp=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"Error retrieving conversation history: {e}")
        return MarketResponse(success=False, error=str(e), timestamp=datetime.now().isoformat())


# ---------------------------------------------------------------------------
# Feedback endpoints
# ---------------------------------------------------------------------------

import hashlib
import pathlib
import uuid as _uuid

_feedback_dir = pathlib.Path("trading_knowledge/feedback")
_feedback_dir.mkdir(parents=True, exist_ok=True)


@router.post("/feedback", response_model=MarketResponse)
async def submit_feedback(request: dict):
    try:
        analysis_id = request.get("analysis_id", str(_uuid.uuid4()))
        rating = int(request.get("rating", 0))
        outcome = request.get("outcome", "unknown")
        notes = request.get("notes", "")
        if rating < 1 or rating > 5:
            return MarketResponse(success=False, error="Rating must be 1-5", timestamp=datetime.now().isoformat())
        feedback = {
            "analysis_id": analysis_id,
            "rating": rating,
            "outcome": outcome,
            "notes": notes,
            "timestamp": datetime.now().isoformat(),
        }
        safe_id = hashlib.md5(analysis_id.encode()).hexdigest()[:12]
        fpath = _feedback_dir / f"{safe_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        fpath.write_text(json.dumps(feedback, indent=2), encoding="utf-8")
        logger.info(f"Feedback stored: {fpath.name} rating={rating}")
        return MarketResponse(
            success=True, data={"feedback_id": fpath.stem, "stored": True}, timestamp=datetime.now().isoformat()
        )
    except Exception as e:
        logger.error(f"Feedback error: {e}")
        return MarketResponse(success=False, error=str(e), timestamp=datetime.now().isoformat())


@router.get("/feedback/stats", response_model=MarketResponse)
async def get_feedback_stats():
    try:
        feedbacks = []
        for fpath in _feedback_dir.glob("*.json"):
            try:
                feedbacks.append(json.loads(fpath.read_text(encoding="utf-8")))
            except Exception:
                pass
        if not feedbacks:
            return MarketResponse(
                success=True, data={"total": 0, "message": "No feedback yet"}, timestamp=datetime.now().isoformat()
            )
        ratings = [f["rating"] for f in feedbacks if "rating" in f]
        outcomes = {}
        for f in feedbacks:
            o = f.get("outcome", "unknown")
            outcomes[o] = outcomes.get(o, 0) + 1
        return MarketResponse(
            success=True,
            data={
                "total": len(feedbacks),
                "average_rating": round(sum(ratings) / len(ratings), 2) if ratings else 0,
                "rating_distribution": {str(r): ratings.count(r) for r in range(1, 6)},
                "outcomes": outcomes,
                "recent": sorted(feedbacks, key=lambda x: x.get("timestamp", ""), reverse=True)[:5],
            },
            timestamp=datetime.now().isoformat(),
        )
    except Exception as e:
        logger.error(f"Feedback stats error: {e}")
        return MarketResponse(success=False, error=str(e), timestamp=datetime.now().isoformat())


# ---------------------------------------------------------------------------
# RAG endpoints -- EnhancedLLMClient + TradingKnowledgeRAG
# ---------------------------------------------------------------------------


async def _get_enhanced_client() -> EnhancedLLMClient:
    """Enhanced (RAG-backed) client on the shared ModelRouter."""
    router = await _get_router()
    return EnhancedLLMClient(settings=settings, router=router)


@router.post("/enhanced-analysis", response_model=MarketResponse)
async def enhanced_analysis(request: EnhancedAnalysisRequest):
    """Knowledge-enhanced analysis via RAG + routed LLM."""
    try:
        client = await _get_enhanced_client()
        analysis = await client.analyze_with_knowledge(
            query=request.query,
            market_data=request.market_data,
            prompt_type=request.prompt_type,
            max_tokens=request.max_tokens,
        )
        if analysis is None:
            return MarketResponse(success=False, error="LLM unavailable", timestamp=datetime.now().isoformat())
        chunks = client.get_related_knowledge(request.query, max_results=3)
        return MarketResponse(
            success=True,
            data={"analysis": analysis, "knowledge_used": [c.get("title") or c.get("term") for c in chunks]},
            timestamp=datetime.now().isoformat(),
        )
    except Exception as e:
        logger.error(f"enhanced-analysis error: {e}")
        return MarketResponse(success=False, error=str(e), timestamp=datetime.now().isoformat())


@router.post("/test-hypothesis", response_model=MarketResponse)
async def test_hypothesis_endpoint(request: TestHypothesisRequest):
    """Test a trading hypothesis from trading_knowledge/hypotheses/."""
    try:
        client = await _get_enhanced_client()
        result = await client.test_hypothesis(request.hypothesis_name, request.market_data)
        if result is None:
            return MarketResponse(
                success=False,
                error="Hypothesis not found or LLM unavailable",
                timestamp=datetime.now().isoformat(),
            )
        return MarketResponse(success=True, data=result, timestamp=datetime.now().isoformat())
    except Exception as e:
        logger.error(f"test-hypothesis error: {e}")
        return MarketResponse(success=False, error=str(e), timestamp=datetime.now().isoformat())


@router.get("/knowledge/{term}", response_model=MarketResponse)
async def knowledge_term(term: str):
    """Glossary definition + related terms."""
    rag = get_trading_rag()
    definition = rag.get_glossary_term(term)
    if definition is None:
        return MarketResponse(success=False, error=f"Unknown term: {term}", timestamp=datetime.now().isoformat())
    return MarketResponse(
        success=True,
        data={"term": term, "definition": definition, "related": rag.get_related_terms(term)},
        timestamp=datetime.now().isoformat(),
    )


@router.post("/retrieve-context", response_model=MarketResponse)
async def retrieve_context_endpoint(request: RetrieveContextRequest):
    """Raw RAG retrieval (debug/UX: shows what context the LLM would see)."""
    rag = get_trading_rag()
    chunks = rag.retrieve_context(request.query, request.max_results)
    mode = chunks[0].get("retrieval", "keyword") if chunks else "none"
    return MarketResponse(
        success=True,
        data={"query": request.query, "chunks": chunks, "retrieval_mode": mode},
        timestamp=datetime.now().isoformat(),
    )
