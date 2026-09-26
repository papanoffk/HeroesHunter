# heroes

Hero profiles (for clients with the `hero` role) and the powers catalog.

## Run

```bash
docker compose up -d postgres
cd services/heroes
cp .env.example .env
uv run heroes-migrate
uv run uvicorn heroes.main:app --reload --port 8001
```

## Authentication

The service does not work with tokens. The API gateway verifies the token via
`GET /auth/verify` and passes the identity in headers:

- `X-Client-Id` — client UUID
- `X-Client-Role` — `hero` / `corporation`

Missing or invalid headers → `401`. The headers are trusted as is, so the service
must be reachable only through the gateway, and the gateway must strip these
headers from incoming client requests.

### Docker

```bash
cp services/heroes/.env.example services/heroes/.env
docker compose up -d --build heroes
```

## Endpoints

| Method | Path                            | Access      | Description                                       |
|--------|---------------------------------|-------------|---------------------------------------------------|
| POST   | `/v1/heroes`                    | hero, self  | Create a hero (multipart: `client_uuid`, `name`, `image?`) |
| GET    | `/v1/heroes/{client_uuid}`      | owner       | Hero profile                                      |
| PATCH  | `/v1/heroes/{client_uuid}`      | owner       | Update profile (multipart: `name?`, `image?`)     |
| GET    | `/v1/heroes/{client_uuid}/image`| owner       | Hero image bytes                                  |
| GET    | `/v1/heroes/powers`             | public      | All powers                                        |
| GET    | `/v1/heroes/powers/{power_id}`  | public      | Single power                                      |
| GET    | `/health`                       | public      | Liveness probe                                    |

Images: PNG, JPEG, GIF or WebP (detected by content, not by the client's content type),
up to `MAX_IMAGE_SIZE_BYTES` (5 MB by default).

## Tests

```bash
uv run --package heroes pytest
```
