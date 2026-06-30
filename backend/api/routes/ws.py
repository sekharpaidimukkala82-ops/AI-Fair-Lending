"""
WebSocket route for real-time task progress updates.

Clients connect to /ws/{file_id} and receive JSON events:
  {"event": "processing.progress", "file_id": "...", "progress": 45, "step": "Embedding"}
  {"event": "processing.completed", "file_id": "...", "progress": 100}
  {"event": "ml.training.started", ...}
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Dict, List, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger("fair_lending.ws")
router = APIRouter(prefix="/ws", tags=["WebSocket"])


class ConnectionManager:
    """Manages WebSocket connections grouped by resource_id (file_id, task_id, etc.)."""

    def __init__(self):
        self._connections: Dict[str, Set[WebSocket]] = defaultdict(set)

    async def connect(self, resource_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections[resource_id].add(ws)
        logger.debug(f"WS connected: resource={resource_id}, total={len(self._connections[resource_id])}")

    def disconnect(self, resource_id: str, ws: WebSocket) -> None:
        self._connections[resource_id].discard(ws)
        if not self._connections[resource_id]:
            del self._connections[resource_id]

    async def broadcast(self, resource_id: str, data: dict) -> None:
        """Send data to all connected clients for a resource_id."""
        dead: List[WebSocket] = []
        for ws in list(self._connections.get(resource_id, set())):
            try:
                await ws.send_text(json.dumps(data))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(resource_id, ws)

    async def send_to(self, ws: WebSocket, data: dict) -> None:
        try:
            await ws.send_text(json.dumps(data))
        except Exception:
            pass

    @property
    def active_count(self) -> int:
        return sum(len(v) for v in self._connections.values())


# Singleton used by Celery tasks and routes
manager = ConnectionManager()


@router.websocket("/{resource_id}")
async def websocket_endpoint(ws: WebSocket, resource_id: str):
    """
    Subscribe to real-time events for a resource (file_id, task_id, etc.).
    Ping/pong keepalive is handled automatically by the browser.
    """
    await manager.connect(resource_id, ws)
    try:
        # Send welcome
        await manager.send_to(ws, {
            "event": "connected",
            "resource_id": resource_id,
            "message": "Subscribed to progress updates",
        })

        # Keep connection alive; client can also send messages (e.g. ping)
        while True:
            try:
                msg = await asyncio.wait_for(ws.receive_text(), timeout=30)
                if msg == "ping":
                    await manager.send_to(ws, {"event": "pong"})
            except asyncio.TimeoutError:
                # Send heartbeat
                await manager.send_to(ws, {"event": "heartbeat"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug(f"WS error for {resource_id}: {e}")
    finally:
        manager.disconnect(resource_id, ws)
        logger.debug(f"WS disconnected: resource={resource_id}")


@router.get("/stats", tags=["WebSocket"])
async def ws_stats():
    """Return current WebSocket connection stats."""
    return {"active_connections": manager.active_count}
