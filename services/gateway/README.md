# gateway

The single entry point: routes requests to the services and turns tokens into identity headers
via `auth`.

```
client ──Bearer──▶ gateway ──GET /auth/verify──▶ auth
                      │◀── X-Client-Id, X-Client-Role
                      └──── X-Client-Id, X-Client-Role ──▶ heroes / corporations / missions / resumes / notifications
```

## Routing

| Prefix               | Service        | Token handling                               |
|----------------------|----------------|----------------------------------------------|
| `/auth`              | auth           | passed through as is (login, register, `me`) |
| `/v1/heroes`         | heroes         | replaced with identity headers               |
| `/v1/corporations`   | corporations   | replaced with identity headers               |
| `/v1/missions`       | missions       | replaced with identity headers               |
| `/v1/resumes`        | resumes        | replaced with identity headers               |
| `/v1/notifications`  | notifications  | replaced with identity headers (WebSocket)   |

The longest matching prefix wins, unknown paths → `404`.

## Authentication

- `X-Client-Id` / `X-Client-Role` from the client are always stripped, so identity can't be spoofed.
- `Authorization: Bearer <token>` → verified via `GET /auth/verify`; invalid token → `401` and the
  request doesn't reach the service. On success the identity headers are added and the token itself
  is not forwarded (services never see tokens, except `auth`).
- No token → the request is forwarded anonymously. The gateway keeps no list of public routes:
  each service decides whether an endpoint is public (e.g. `GET /v1/missions`) or requires identity (`401`).
- auth unavailable → `502`.

### WebSocket

Browsers can't set headers on a WebSocket, so the token can be passed as a query parameter:

```
ws://localhost:8080/v1/notifications/ws?token=<access_token>
```

`Authorization` works as well for non-browser clients. The `token` parameter is removed before the
connection is proxied. An invalid token or a rejection by the service closes the connection with `1008`.

Note: a token in the URL may end up in access logs; the tokens are short-lived (30 min by default).

## Proxying

- Response bodies are streamed without buffering; request bodies are limited by
  `MAX_BODY_SIZE_BYTES` (10 MB by default) → `413`.
- Hop-by-hop headers are removed, `X-Forwarded-For` / `-Proto` / `-Host` are added.
- Upstream unavailable → `502`, timeout (`UPSTREAM_TIMEOUT_SECONDS`) → `504`.
- CORS is configured here for all services via `CORS_ORIGINS`.

## Run

```bash
cd services/gateway
cp .env.example .env
uv run uvicorn gateway.main:app --reload --port 8080
```

### Docker

```bash
docker compose up -d --build gateway   # http://localhost:8080
```

## Tests

```bash
uv run --package gateway pytest
```

Services are faked with `httpx2.MockTransport`; the WebSocket proxy is tested against a real
uvicorn server started in a background thread.
