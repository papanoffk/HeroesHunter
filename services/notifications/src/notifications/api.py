from fastapi import APIRouter, WebSocket

from notifications.dependencies import ConnectionManagerDep, PrincipalDep

router = APIRouter(prefix="/v1/notifications", tags=["notifications"])


@router.websocket("/ws")
async def notifications_ws(websocket: WebSocket, principal: PrincipalDep, manager: ConnectionManagerDep) -> None:
    await websocket.accept()
    manager.connect(principal.client_id, websocket)
    try:
        # Server-push only: incoming messages are ignored, the loop just waits for the disconnect.
        while (await websocket.receive())["type"] != "websocket.disconnect":
            pass
    finally:
        manager.disconnect(principal.client_id, websocket)
