import asyncio
import json
import uuid

from fastapi import WebSocket


# In-process only: connections live in this one server's memory, so this
# only fans out changes within a single running instance. Fine for this
# app's scale (one shop, a handful of devices) and for a study project —
# a multi-instance deployment would need a shared layer (e.g. Redis pub/sub)
# instead, which is a real jump in complexity, not something to add
# speculatively before it's ever needed.
class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, owner_id: uuid.UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.setdefault(owner_id, set()).add(websocket)

    async def disconnect(self, owner_id: uuid.UUID, websocket: WebSocket) -> None:
        async with self._lock:
            sockets = self._connections.get(owner_id)
            if sockets is not None:
                sockets.discard(websocket)
                if not sockets:
                    del self._connections[owner_id]

    # Tells every open connection for this owner which table changed, so the
    # frontend can refetch just that one (mirrors what a Supabase
    # postgres_changes subscription already did per table). Every open tab
    # gets the message, including the one that made the change — a redundant
    # refetch of data it already has locally is harmless, and it keeps this
    # simple: no need to track "which socket made this request" through every
    # endpoint that calls broadcast().
    async def broadcast(self, owner_id: uuid.UUID, table: str) -> None:
        async with self._lock:
            sockets = list(self._connections.get(owner_id, ()))
        message = json.dumps({"table": table})
        for websocket in sockets:
            try:
                await websocket.send_text(message)
            except Exception:
                pass  # a dead socket is cleaned up by its own receive loop


manager = ConnectionManager()
