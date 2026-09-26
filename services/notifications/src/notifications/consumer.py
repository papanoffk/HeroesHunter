import logging

import aio_pika
from aio_pika.abc import AbstractIncomingMessage, AbstractRobustConnection
from pydantic import ValidationError

from notifications.config import Settings
from notifications.connections import ConnectionManager
from notifications.schemas import Event

logger = logging.getLogger(__name__)


class EventConsumer:
    def __init__(self, manager: ConnectionManager) -> None:
        self._manager = manager
        self._connection: AbstractRobustConnection | None = None

    async def start(self, settings: Settings) -> None:
        self._connection = await aio_pika.connect_robust(settings.rabbitmq_url.get_secret_value())
        channel = await self._connection.channel()
        await channel.set_qos(prefetch_count=settings.events_prefetch_count)
        exchange = await channel.declare_exchange(
            settings.events_exchange, aio_pika.ExchangeType.TOPIC, durable=True
        )
        # Every instance needs every event (it can't know where the client is connected),
        # and events for offline clients are dropped anyway, so the queue is per instance and temporary.
        queue = await channel.declare_queue(exclusive=True, auto_delete=True)
        for routing_key in settings.events_routing_keys:
            await queue.bind(exchange, routing_key=routing_key)
        await queue.consume(self._on_message)

    async def stop(self) -> None:
        if self._connection is not None:
            await self._connection.close()

    async def _on_message(self, message: AbstractIncomingMessage) -> None:
        async with message.process(requeue=False):
            await self.handle(message.body)

    async def handle(self, body: bytes) -> None:
        try:
            event = Event.model_validate_json(body)
        except ValidationError:
            logger.warning("Skipping malformed event: %r", body[:500])
            return
        delivered = await self._manager.send(event.recipient_uuid, event.model_dump(mode="json"))
        logger.debug("Event %s for %s delivered to %d connection(s)", event.event, event.recipient_uuid, delivered)


async def start_consumer(settings: Settings, manager: ConnectionManager) -> EventConsumer:
    consumer = EventConsumer(manager)
    await consumer.start(settings)
    return consumer
