from typing import Annotated

import httpx2
from fastapi import Depends
from starlette.requests import HTTPConnection

from gateway.config import Settings, get_settings
from gateway.routing import Route

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_http_client(connection: HTTPConnection) -> httpx2.AsyncClient:
    return connection.app.state.http_client


def get_routes(connection: HTTPConnection) -> list[Route]:
    return connection.app.state.routes


HttpClientDep = Annotated[httpx2.AsyncClient, Depends(get_http_client)]
RoutesDep = Annotated[list[Route], Depends(get_routes)]
