# missions

Missions published by corporations and hero responses to them.

Flow: a corporation creates a mission → heroes respond and land in `new_respondents_uuids` →
the owner marks them as viewed via `/view`, which moves them to `respondents_uuids`.

## Run

```bash
docker compose up -d postgres
cd services/missions
cp .env.example .env
uv run missions-migrate
uv run uvicorn missions.main:app --reload --port 8003
```

### Docker

```bash
docker compose up -d --build missions
```

## Authentication

The service does not work with tokens. The API gateway verifies the token via
`GET /auth/verify` and passes the identity in headers:

- `X-Client-Id` — client UUID
- `X-Client-Role` — `hero` / `corporation`

Public endpoints work without headers; invalid headers → `401` everywhere.
The headers are trusted as is, so the service must be reachable only through the gateway,
and the gateway must strip these headers from incoming client requests.

## Endpoints

| Method | Path                                  | Access       | Description                                   |
|--------|---------------------------------------|--------------|-----------------------------------------------|
| POST   | `/v1/missions`                        | corporation  | Create a mission (owner = `X-Client-Id`)      |
| GET    | `/v1/missions`                        | public       | List missions with filters                    |
| GET    | `/v1/missions/{mission_uuid}`         | public       | Mission                                       |
| PATCH  | `/v1/missions/{mission_uuid}`         | owner        | Update a mission                              |
| DELETE | `/v1/missions/{mission_uuid}`         | owner        | Delete a mission                              |
| POST   | `/v1/missions/{mission_uuid}/view`    | owner        | Move viewed respondents to `respondents_uuids` |
| POST   | `/v1/missions/{mission_uuid}/respond` | hero         | Respond to a mission (`409` if already did)   |
| GET    | `/health`                             | public       | Liveness probe                                |

`respondents_uuids` / `new_respondents_uuids` are returned only to the mission owner, `null` for others.

List filters (all optional, combined with AND):

- `min_offer`, `max_offer` — offer range (missions without an offer are excluded)
- `max_work_experience` — missions requiring at most N years
- `powers_ids` — missions requiring any of these powers, e.g. `?powers_ids=1&powers_ids=3`
- `limit` (1–100, default 50), `offset`

Missions are sorted newest first (`created_at DESC`).

`PATCH` semantics: omitted fields are left unchanged, explicit `null` clears
`descriptions` / `location` / `offer`. Respondents can't be changed via `PATCH`.

`/view` body: `{"respondents_uuids": [...]}`. Only uuids present in `new_respondents_uuids`
are moved (order is kept), unknown ones are ignored, so the call is idempotent.

## Tests

Tests run against a real Postgres: a throwaway schema is created and migrated before
the session and dropped after it. Without a reachable database the tests are skipped.

```bash
docker compose up -d postgres
uv run --package missions pytest
```
