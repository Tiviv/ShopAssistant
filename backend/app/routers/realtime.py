from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.auth import decode_user_id
from app.database import async_session
from app.models import User
from app.realtime import manager

router = APIRouter()


@router.websocket("/ws")
async def realtime_socket(websocket: WebSocket, token: str) -> None:
    # A WebSocket handshake can't carry a bearer token in the Authorization
    # header the way a normal request does (the browser WebSocket API
    # doesn't let JS set custom headers), so the token travels as a query
    # param instead — ws://.../ws?token=...
    owner_id = decode_user_id(token)
    if owner_id is None:
        await websocket.close(code=4401)
        return

    async with async_session() as db:
        user = await db.get(User, owner_id)
    if user is None:
        await websocket.close(code=4401)
        return

    await manager.connect(owner_id, websocket)
    try:
        while True:
            # The frontend never sends anything meaningful — this just blocks
            # until the client disconnects, which is how we notice and clean
            # the connection up. A dropped connection raises here too.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(owner_id, websocket)
