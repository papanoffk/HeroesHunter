import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

import aio_pika
from aio_pika.abc import AbstractExchange, AbstractRobustConnection

from missions.config import Settings

logger = logging.getLogger(__name__)

MISSION_RESPONDED = "mission.responded"


class EventPublisher:
    """Best-effort publisher: a failed publish is logged and never breaks the request."""

    def __init__(self, connection: AbstractRobustConnection, exchange: AbstractExchange, timeout: float) -> None:
        self._connection = connection
        self._exchange = exchange
        self._timeout = timeout

    async def publish(self, routing_key: str, payload: dict[str, Any]) -> None:
        event = {"event": routing_key, "occurred_at": datetime.now(UTC).isoformat(), **payload}
        message = aio_pika.Message(json.dumps(event, default=str).encode(), content_type="application/json")
        try:
            await asyncio.wait_for(self._exchange.publish(message, routing_key=routing_key), self._timeout)
        except Exception:
            logger.exception("Failed to publish %s event", routing_key)

    async def close(self) -> None:
        await self._connection.close()


async def connect_publisher(settings: Settings) -> EventPublisher:
    connection = await aio_pika.connect_robust(settings.rabbitmq_url.get_secret_value())
    channel = await connection.channel()
    exchange = await channel.declare_exchange(settings.events_exchange, aio_pika.ExchangeType.TOPIC, durable=True)
    return EventPublisher(connection, exchange, settings.events_publish_timeout_seconds)
