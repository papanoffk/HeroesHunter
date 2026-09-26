# auth

Registration, authentication and authorization of clients (JWT).

## Run

```bash
docker compose up -d postgres
cd services/auth
cp .env.example .env
uv run auth-migrate
uv run uvicorn auth.main:app --reload
```

Swagger UI: http://localhost:8000/docs

### Docker

```bash
cp services/auth/.env.example services/auth/.env
docker compose up -d --build auth
```

The image is built from the repository root, since the uv workspace lockfile lives there:
`docker build -f services/auth/Dockerfile .`

## Endpoints

| Method | Path             | Description                                  |
|--------|------------------|----------------------------------------------|
| POST   | `/auth/register` | Create a client (`email`, `password`, `role`) |
| POST   | `/auth/login`    | Get an access token                          |
| GET    | `/auth/me`       | Current client (requires `Bearer` token)     |
| GET    | `/auth/verify`   | Forward auth for the API gateway: `200` with `X-Client-Id` / `X-Client-Role` headers, or `401` |
| GET    | `/health`        | Liveness probe                               |

Token payload: `client_id`, `role` (`hero` / `corporation`), `exp`.


## Tests

```bash
uv run pytest
```
