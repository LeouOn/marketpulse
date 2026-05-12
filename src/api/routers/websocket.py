"""WebSocket endpoints"""

import asyncio
from datetime import datetime
from loguru import logger
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/market")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time market data"""
    await websocket.accept()
    logger.info("WebSocket connection established")

    try:
        await websocket.send_json({
            "type": "connection_established",
            "message": "Connected to MarketPulse WebSocket",
            "timestamp": datetime.now().isoformat()
        })

        message_count = 0
        while True:
            try:
                from src.api.routers.deps import collector

                if collector:
                    internals = await collector.collect_market_internals()
                    await websocket.send_json({
                        "type": "market_update",
                        "data": internals,
                        "timestamp": datetime.now().isoformat(),
                        "message_id": message_count
                    })
                    message_count += 1
                else:
                    await websocket.send_json({
                        "type": "status",
                        "message": "Collector not initialized",
                        "timestamp": datetime.now().isoformat()
                    })

                await asyncio.sleep(30)
            except Exception as loop_error:
                logger.error(f"Error in WebSocket loop: {loop_error}")
                await websocket.send_json({
                    "type": "error",
                    "message": f"Error fetching data: {str(loop_error)}",
                    "timestamp": datetime.now().isoformat()
                })
                await asyncio.sleep(5)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": f"WebSocket error: {str(e)}",
                "timestamp": datetime.now().isoformat()
            })
        except Exception:
            pass
    finally:
        logger.info("WebSocket connection closed")


@router.websocket("/ws/test")
async def websocket_test_endpoint(websocket: WebSocket):
    """Simple WebSocket test endpoint"""
    await websocket.accept()
    logger.info("Test WebSocket connection established")

    try:
        await websocket.send_json({
            "type": "test_connection",
            "message": "Test WebSocket is working!",
            "timestamp": datetime.now().isoformat()
        })

        while True:
            try:
                data = await websocket.receive_json()
                await websocket.send_json({
                    "type": "echo",
                    "received": data,
                    "timestamp": datetime.now().isoformat()
                })
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
