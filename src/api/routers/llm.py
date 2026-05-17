"""LLM chat and analysis endpoints"""

import json
import asyncio
from datetime import datetime
from loguru import logger
from fastapi import APIRouter
from typing import Dict, Any

from .deps import (
    settings, LMStudioClient, LLMManager, db_manager, model_cache,
    MarketResponse, ChatRequest, ModelSelectionRequest,
    UserComment, RefinedAnalysisRequest, ChartAnalysisRequest,
)

router = APIRouter(prefix="/api/llm", tags=["llm"])

# Shared LLM client so we reuse the aiohttp session across requests
_shared_client: LMStudioClient | None = None
_client_lock = asyncio.Lock()


async def _get_llm_client() -> LMStudioClient:
    """Get or create a shared LMStudioClient (reuses session)."""
    global _shared_client
    if _shared_client is not None and _shared_client.session is not None and not _shared_client.session.closed:
        return _shared_client
    async with _client_lock:
        # Double-check after acquiring lock
        if _shared_client is not None and _shared_client.session is not None and not _shared_client.session.closed:
            return _shared_client
        client = LMStudioClient()
        await client.__aenter__()
        _shared_client = client
        logger.info(f"Created shared LLM client, model={client.get_active_model()}")
    return _shared_client


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

            if 'detected_symbols' in context_data and context_data['detected_symbols']:
                detected_syms = context_data['detected_symbols']
                context_info += f"Symbols Mentioned: {', '.join(detected_syms)}\n"

            if 'query_type' in context_data:
                query_type = context_data['query_type']
                context_info += f"Query Type: {query_type}\n"

                if query_type == 'trend_analysis':
                    context_info += "Focus on trend direction, momentum, and price patterns.\n"
                elif query_type == 'technical_levels':
                    context_info += "Focus on support/resistance levels and price targets.\n"
                elif query_type == 'volatility_analysis':
                    context_info += "Focus on volatility patterns, risk assessment, and timing.\n"
                elif query_type == 'trading_strategy':
                    context_info += "Focus on actionable strategies, entries, exits, and risk management.\n"
                elif query_type == 'symbol_specific':
                    context_info += "Focus analysis on the detected symbols mentioned.\n"

        if request.symbol:
            context_info += f"Primary Symbol: {request.symbol}\n"

        messages = []
        messages.append({'role': 'system', 'content': system_prompt})

        if request.conversation_history:
            for msg in request.conversation_history[-6:]:
                messages.append({'role': msg['role'], 'content': msg['content']})

        if context_info:
            messages.append({'role': 'system', 'content': context_info})

        messages.append({'role': 'user', 'content': request.message})

        response_text = None

        try:
            client = await _get_llm_client()
            selected_model = client.get_active_model()
            logger.info(f"LLM chat: model={selected_model}, msg_count={len(messages)}")

            response = await asyncio.wait_for(
                client.generate_completion(
                    model=selected_model,
                    messages=messages,
                    max_tokens=600,
                    temperature=0.7
                ),
                timeout=180.0
            )

            if response and 'choices' in response and len(response['choices']) > 0:
                response_text = response['choices'][0]['message']['content']
                logger.info(f"LLM chat success: {len(response_text)} chars")

        except asyncio.TimeoutError:
            logger.error("LM Studio request timed out after 3 minutes")
            return MarketResponse(
                success=False,
                error="The AI request timed out after 3 minutes. The query might be too complex or the AI service is overloaded. Please try again with a simpler question.",
                timestamp=datetime.now().isoformat()
            )
        except Exception as e:
            logger.error(f"LM Studio error: {type(e).__name__}: {e}")
            # Reset shared client on error so next request creates a fresh one
            global _shared_client
            if _shared_client:
                try:
                    await _shared_client.__aexit__(None, None, None)
                except Exception:
                    pass
                _shared_client = None

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

        return MarketResponse(
            success=True,
            data={'response': response_text},
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error in LLM chat: {type(e).__name__}: {e}")
        # Always return a proper response, never let FastAPI generate a 500
        return MarketResponse(
            success=False,
            error=f"An error occurred while processing your request: {str(e)}",
            timestamp=datetime.now().isoformat()
        )


@router.get("/models", response_model=MarketResponse)
async def get_available_models():
    """Get available models from LM Studio and cache them"""
    try:
        import aiohttp
        current_time = datetime.now().timestamp()

        if (model_cache["models"] and
            model_cache["timestamp"] and
            current_time - model_cache["timestamp"] < model_cache["cache_duration"]):

            return MarketResponse(
                success=True,
                data={
                    "models": model_cache["models"],
                    "cached": True,
                    "cache_age": int(current_time - model_cache["timestamp"]),
                    "provider": "lm_studio"
                },
                timestamp=datetime.now().isoformat()
            )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("http://localhost:1234/v1/models", timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        models_data = await response.json()

                        models = []
                        loaded_ids = [m.get("id") for m in models_data.get("data", [])]
                        config_model = getattr(settings.llm.primary, 'model', '')
                        recommended_id = config_model if config_model in loaded_ids else (loaded_ids[0] if loaded_ids else None)

                        for model in models_data.get("data", []):
                            model_id = model.get("id")
                            model_info = {
                                "id": model_id,
                                "object": model.get("object"),
                                "owned_by": model.get("owned_by"),
                                "size": _estimate_model_size(model_id or ""),
                                "recommended": model_id == recommended_id
                            }
                            models.append(model_info)

                        model_cache["models"] = models
                        model_cache["timestamp"] = current_time

                        return MarketResponse(
                            success=True,
                            data={
                                "models": models,
                                "cached": False,
                                "cache_age": 0,
                                "provider": "lm_studio",
                                "total_count": len(models)
                            },
                            timestamp=datetime.now().isoformat()
                        )
                    else:
                        raise Exception(f"LM Studio API returned status {response.status}")

        except Exception as lm_error:
            logger.warning(f"Could not fetch models from LM Studio: {lm_error}")

            if model_cache["models"]:
                return MarketResponse(
                    success=True,
                    data={
                        "models": model_cache["models"],
                        "cached": True,
                        "cache_age": int(current_time - model_cache["timestamp"]) if model_cache["timestamp"] else 999999,
                        "provider": "lm_studio",
                        "warning": "Using stale cache - LM Studio unavailable"
                    },
                    timestamp=datetime.now().isoformat()
                )

            default_model = getattr(settings.llm.primary, 'model', '')
            fallback_models = [
                {
                    "id": default_model or "no-model-loaded",
                    "object": "model",
                    "owned_by": "organization_owner",
                    "size": "Unknown",
                    "recommended": True
                }
            ]

            return MarketResponse(
                success=True,
                data={
                    "models": fallback_models,
                    "cached": False,
                    "cache_age": 0,
                    "provider": "fallback",
                    "warning": "LM Studio unavailable - using fallback models"
                },
                timestamp=datetime.now().isoformat()
            )

    except Exception as e:
        logger.error(f"Error fetching models: {e}")
        return MarketResponse(
            success=False,
            error=str(e),
            timestamp=datetime.now().isoformat()
        )


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
                    timestamp=datetime.now().isoformat()
                )

        if hasattr(LMStudioClient, 'default_model'):
            LMStudioClient.default_model = request.model_id

        return MarketResponse(
            success=True,
            data={
                "selected_model": request.model_id,
                "provider": request.provider,
                "message": f"Model '{request.model_id}' selected successfully"
            },
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error selecting model: {e}")
        return MarketResponse(
            success=False,
            error=str(e),
            timestamp=datetime.now().isoformat()
        )


@router.get("/model-status", response_model=MarketResponse)
async def get_model_status():
    """Get current model status and LM Studio connection"""
    try:
        import aiohttp

        config_model = getattr(settings.llm.primary, 'model', '') or 'not configured'

        status_info = {
            "lm_studio_connected": False,
            "config_model": config_model,
            "active_model": config_model,
            "auto_detected": False,
            "loaded_models": [],
            "last_check": datetime.now().isoformat(),
            "response_time_ms": None
        }

        try:
            start_time = datetime.now().timestamp()
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{settings.llm.primary.base_url}/models",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status == 200:
                        status_info["lm_studio_connected"] = True
                        status_info["response_time_ms"] = int((datetime.now().timestamp() - start_time) * 1000)
                        md = await response.json()
                        loaded = [m['id'] for m in md.get('data', [])]
                        status_info["loaded_models"] = loaded
                        if loaded:
                            active = config_model if config_model in loaded else loaded[0]
                            status_info["active_model"] = active
                            status_info["auto_detected"] = active != config_model
        except Exception as connection_error:
            logger.warning(f"LM Studio connection test failed: {connection_error}")
            status_info["connection_error"] = str(connection_error)

        return MarketResponse(
            success=True,
            data=status_info,
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error getting model status: {e}")
        return MarketResponse(
            success=False,
            error=str(e),
            timestamp=datetime.now().isoformat()
        )


@router.post("/comment", response_model=MarketResponse)
async def add_user_comment(comment: UserComment):
    """Add user comment to LLM analysis"""
    try:
        comment_data = {
            'analysis_id': comment.analysis_id,
            'user_id': comment.user_id,
            'comment': comment.comment,
            'timestamp': comment.timestamp or datetime.now().isoformat()
        }

        if db_manager:
            db_manager.save_user_comment(comment_data)

        return MarketResponse(
            success=True,
            data={"message": "Comment added successfully", "comment_id": comment.analysis_id},
            timestamp=datetime.now().isoformat()
        )
    except Exception as e:
        logger.error(f"Error adding comment: {e}")
        return MarketResponse(
            success=False,
            error=str(e),
            timestamp=datetime.now().isoformat()
        )


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
        {json.dumps(request.additional_context, indent=2) if request.additional_context else 'None'}

        Provide a refined, more accurate analysis.
        """

        messages = [{'role': 'user', 'content': refinement_prompt}]

        async with LMStudioClient() as client:
            response = await client.generate_completion(
                model='deep_analysis',
                messages=messages,
                max_tokens=400,
                temperature=0.4
            )

            if response and 'choices' in response:
                refined_analysis = response['choices'][0]['message']['content']

                return MarketResponse(
                    success=True,
                    data={
                        "refined_analysis": refined_analysis,
                        "original_analysis": request.original_analysis,
                        "user_comments_count": len(request.user_comments)
                    },
                    timestamp=datetime.now().isoformat()
                )

        return MarketResponse(
            success=False,
            error="Failed to generate refined analysis",
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error refining analysis: {e}")
        return MarketResponse(
            success=False,
            error=str(e),
            timestamp=datetime.now().isoformat()
        )


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
                        "symbol": request.chart_data.get('symbol'),
                        "timeframe": request.chart_data.get('timeframe')
                    },
                    timestamp=datetime.now().isoformat()
                )
            else:
                return MarketResponse(
                    success=False,
                    error="Failed to analyze chart data",
                    timestamp=datetime.now().isoformat()
                )

    except Exception as e:
        logger.error(f"Error analyzing chart: {e}")
        return MarketResponse(
            success=False,
            error=str(e),
            timestamp=datetime.now().isoformat()
        )


@router.get("/validation/sanity-check", response_model=MarketResponse)
async def run_sanity_check():
    """Run sanity check on current market data"""
    try:
        from .deps import collector

        if not collector:
            return MarketResponse(
                success=False,
                error="Collector not initialized",
                timestamp=datetime.now().isoformat()
            )

        internals = await collector.collect_market_internals()

        if not internals:
            return MarketResponse(
                success=False,
                error="No market data available for validation",
                timestamp=datetime.now().isoformat()
            )

        async with LMStudioClient() as client:
            validation_result = await client.validate_data_interpretation(internals, "market_internals")

            return MarketResponse(
                success=True,
                data={
                    "validation_result": validation_result,
                    "market_data": internals
                },
                timestamp=datetime.now().isoformat()
            )

    except Exception as e:
        logger.error(f"Error running sanity check: {e}")
        return MarketResponse(
            success=False,
            error=str(e),
            timestamp=datetime.now().isoformat()
        )


@router.get("/conversation-history/{analysis_id}", response_model=MarketResponse)
async def get_conversation_history(analysis_id: str):
    """Get conversation history for an analysis"""
    try:
        if db_manager:
            history = db_manager.get_analysis_conversation(analysis_id)
        else:
            history = []

        return MarketResponse(
            success=True,
            data={
                "analysis_id": analysis_id,
                "conversation_history": history,
                "turns_count": len(history) if history else 0
            },
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error retrieving conversation history: {e}")
        return MarketResponse(
            success=False,
            error=str(e),
            timestamp=datetime.now().isoformat()
        )
