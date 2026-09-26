# corporations

Corporation profiles (hero employers) for clients with the `corporation` role.

## Run

```bash
docker compose up -d postgres
cd services/corporations
cp .env.example .env
uv run corporations-migrate
uv run uvicorn corporations.main:app --reload --port 8002
```

### Docker

```bash
docker compose up -d --build corporations
```

## Authentication

The service does not work with tokens. The API gateway verifies the token via
`GET /auth/verify` and passes the identity in headers:

- `X-Client-Id` — client UUID
- `X-Client-Role` — `hero` / `corporation`

Missing or invalid headers → `401`. The headers are trusted as is, so the service
must be reachable only through the gateway, and the gateway must strip these
headers from incoming client requests.

## Endpoints

| Method | Path                              | Access            | Description               |
|--------|-----------------------------------|-------------------|---------------------------|
| POST   | `/v1/corporations`                | corporation, self | Create a corporation      |
| GET    | `/v1/corporations/{client_uuid}`  | owner             | Corporation profile       |
| PATCH  | `/v1/corporations/{client_uuid}`  | owner             | Update profile            |
| GET    | `/v1/corporations/{client_uuid}/image` | owner        | Logo image bytes          |
| GET    | `/health`                         | public            | Liveness probe            |

Body (multipart/form-data): `client_uuid` (POST only), `name` (1–150), `description?`, `image?`.
`PATCH` updates only the passed fields.

Images: PNG, JPEG, GIF or WebP (detected by content, not by the client's content type),
up to `MAX_IMAGE_SIZE_BYTES` (5 MB by default).

## Tests

```bash
uv run --package corporations pytest
```
