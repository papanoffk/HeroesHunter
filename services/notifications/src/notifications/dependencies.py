from typing import Annotated

from fastapi import Depends, Header, WebSocket, WebSocketException, status
from pydantic import ValidationError

from notifications.connections import ConnectionManager
from notifications.schemas import Principal


def get_principal(
    client_id: Annotated[str | None, Header(alias="X-Client-Id")] = None,
    role: Annotated[str | None, Header(alias="X-Client-Role")] = None,
) -> Principal:
    """Identity is set by the API gateway after verifying the token in auth."""
    try:
        return Principal.model_validate({"client_id": client_id, "role": role})
    except ValidationError:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthenticated") from None


def get_connection_manager(websocket: WebSocket) -> ConnectionManager:
    return websocket.app.state.connection_manager


PrincipalDep = Annotated[Principal, Depends(get_principal)]
ConnectionManagerDep = Annotated[ConnectionManager, Depends(get_connection_manager)]
