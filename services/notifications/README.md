# notifications

Delivers events from RabbitMQ to connected clients over WebSocket.

```
missions  POST /v1/missions/{id}/respond   ──▶ mission.responded ─┐
                                                                 ├─▶ exchange heroes_hunter.events (topic)
resumes   POST /v1/resumes/{id}/invitation ──▶ resume.invited ────┘            │
                                                                               ▼
                                                  per-instance queue ─▶ notifications ─ws─▶ recipient
```

If the recipient (`recipient_uuid`) has an open connection on this instance, the event is sent
to all of their connections (e.g. several browser tabs); otherwise it is skipped.
Every instance has its own temporary (exclusive, auto-delete) queue bound to the exchange,
so the service scales horizontally: each instance gets every event and delivers it only to its
own connections.

## Run

```bash
docker compose up -d rabbitmq
cd services/notifications
cp .env.example .env
uv run uvicorn notifications.main:app --reload --port 8005
```

### Docker

```bash
docker compose up -d --build notifications
```

## WebSocket

`ws://<gateway>/v1/notifications/ws`

The identity comes from the API gateway headers `X-Client-Id` / `X-Client-Role`
(the gateway verifies the token via `GET /auth/verify`). Without valid headers the handshake is
rejected with close code `1008`. Browsers can't set headers on a WebSocket, so the gateway has to
take the token from a cookie or a query parameter for this route.

The connection is server-push only, incoming messages are ignored. Messages are the event
payloads as published:

```json
{"event": "mission.responded", "occurred_at": "...", "recipient_uuid": "<corporation>", "mission_uuid": "...", "hero_uuid": "..."}
{"event": "resume.invited", "occurred_at": "...", "recipient_uuid": "<hero>", "resume_uuid": "...", "corp_uuid": "..."}
```

Delivery is best-effort: events for offline clients are not stored.

## Tests

```bash
uv run --package notifications pytest
```
