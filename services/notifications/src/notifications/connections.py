import logging
from collections import defaultdict
from typing import Any
from uuid import UUID

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket connections of this instance; a client may have several (e.g. browser tabs)."""

    def __init__(self) -> None:
        self._connections: defaultdict[UUID, set[WebSocket]] = defaultdict(set)

    def connect(self, client_id: UUID, websocket: WebSocket) -> None:
        self._connections[client_id].add(websocket)

    def disconnect(self, client_id: UUID, websocket: WebSocket) -> None:
        sockets = self._connections.get(client_id)
        if sockets is None:
            return
        sockets.discard(websocket)
        if not sockets:
            del self._connections[client_id]

    async def send(self, client_id: UUID, message: dict[str, Any]) -> int:
        """Returns the number of connections the message was delivered to, 0 if the client is offline."""
        delivered = 0
        for websocket in list(self._connections.get(client_id, ())):
            try:
                await websocket.send_json(message)
                delivered += 1
            except Exception:
                logger.warning("Dropping a broken connection of client %s", client_id, exc_info=True)
                self.disconnect(client_id, websocket)
        return delivered
