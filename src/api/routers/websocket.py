"""WebSocket endpoints"""

import asyncio
import contextlib
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from . import deps

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/market")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time market data"""
    await websocket.accept()
    logger.info("WebSocket connection established")

    try:
        await websocket.send_json(
            {
                "type": "connection_established",
                "message": "Connected to MarketPulse WebSocket",
                "timestamp": datetime.now().isoformat(),
            }
        )

        message_count = 0
        while True:
            try:
                collector = deps.collector

                if collector:
                    internals = await collector.collect_market_internals()
                    await websocket.send_json(
                        {
                            "type": "market_update",
                            "data": internals,
                            "timestamp": datetime.now().isoformat(),
                            "message_id": message_count,
                        }
                    )
                    message_count += 1
                else:
                    await websocket.send_json(
                        {
                            "type": "status",
                            "message": "Collector not initialized",
                            "timestamp": datetime.now().isoformat(),
                        }
                    )

                await asyncio.sleep(30)
            except Exception as loop_error:
                logger.error(f"Error in WebSocket loop: {loop_error}")
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": f"Error fetching data: {str(loop_error)}",
                        "timestamp": datetime.now().isoformat(),
                    }
                )
                await asyncio.sleep(5)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        with contextlib.suppress(Exception):
            await websocket.send_json(
                {"type": "error", "message": f"WebSocket error: {str(e)}", "timestamp": datetime.now().isoformat()}
            )
    finally:
        logger.info("WebSocket connection closed")


@router.websocket("/ws/test")
async def websocket_test_endpoint(websocket: WebSocket):
    """Simple WebSocket test endpoint"""
    await websocket.accept()
    logger.info("Test WebSocket connection established")

    try:
        await websocket.send_json(
            {
                "type": "test_connection",
                "message": "Test WebSocket is working!",
                "timestamp": datetime.now().isoformat(),
            }
        )

        while True:
            try:
                data = await websocket.receive_json()
                await websocket.send_json({"type": "echo", "received": data, "timestamp": datetime.now().isoformat()})
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"Error in test WebSocket: {e}")
                break

    except WebSocketDisconnect:
        logger.info("Test WebSocket disconnected")
    except Exception as e:
        logger.error(f"Test WebSocket error: {e}")
    finally:
        logger.info("Test WebSocket connection closed")


@router.websocket("/ws/stream-analysis")
async def stream_analysis_endpoint(websocket: WebSocket):
    """WebSocket endpoint for streaming agentic market analysis.

    Client sends::

        {"query": "Is SPY healthy?", "symbols": ["SPY"], "include_breadth": true}

    Server streams phase events::

        {"phase": "plan", "data": {...}}
        {"phase": "data_fetching", "agent_name": "data_agent"}
        {"phase": "data_complete", "content": "...", "tools_used": [...]}
        {"phase": "agents_running", "data": {"agents": [...]}}
        {"phase": "agent_done", "agent_name": "Macro", "content": "...", "tools_used": [...]}
        ... (one per agent)
        {"phase": "draft_ready", "content": "..."}
        {"phase": "critiquing", "agent_name": "critique_agent"}
        {"phase": "final_ready", "content": "...", "data": {...}}
    """
    await websocket.accept()
    logger.info("Stream-analysis WebSocket connected")

    try:
        # Wait for the analysis request
        data = await websocket.receive_json()
        query = data.get("query", "")
        symbols = data.get("symbols", ["SPY"])
        include_breadth = data.get("include_breadth", True)

        if not query:
            await websocket.send_json(
                {
                    "phase": "error",
                    "content": "Missing 'query' field in request.",
                }
            )
            return

        logger.info(f"Stream-analysis: query='{query[:60]}...' symbols={symbols}")

        # Send acknowledgement
        await websocket.send_json(
            {
                "phase": "accepted",
                "data": {"query": query, "symbols": symbols},
            }
        )

        # Run the streaming pipeline
        from src.llm.agents.orchestrator import MarketAnalysisOrchestrator

        orchestrator = MarketAnalysisOrchestrator()
        async with orchestrator:
            async for event in orchestrator.analyze_streaming(
                query=query,
                symbols=symbols,
                include_breadth=include_breadth,
            ):
                # Send event as JSON to the WebSocket client
                await websocket.send_json(
                    {
                        "phase": event.phase,
                        "agent_name": event.agent_name,
                        "content": event.content,
                        "tools_used": event.tools_used,
                        "data": event.data,
                    }
                )

        # Send completion signal
        await websocket.send_json(
            {
                "phase": "complete",
                "content": "Analysis pipeline finished.",
            }
        )

    except WebSocketDisconnect:
        logger.info("Stream-analysis WebSocket disconnected")
    except Exception as e:
        logger.error(f"Stream-analysis WebSocket error: {e}")
        with contextlib.suppress(Exception):
            await websocket.send_json(
                {
                    "phase": "error",
                    "content": f"Pipeline error: {str(e)}",
                }
            )
    finally:
        logger.info("Stream-analysis WebSocket closed")
