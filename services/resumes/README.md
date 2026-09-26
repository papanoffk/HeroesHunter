# resumes

Hero resumes and invitations from corporations.

Flow: a hero creates a resume → corporations invite and land in `new_invitations_corp_uuids` →
the owner (hero) marks them as viewed via `/view`, which moves them to `invitations_corp_uuids`.

## Run

```bash
docker compose up -d postgres
cd services/resumes
cp .env.example .env
uv run resumes-migrate
uv run uvicorn resumes.main:app --reload --port 8004
```

### Docker

```bash
docker compose up -d --build resumes
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

| Method | Path                                    | Access       | Description                                              |
|--------|-----------------------------------------|--------------|----------------------------------------------------------|
| POST   | `/v1/resumes`                           | hero         | Create a resume (owner = `X-Client-Id`)                  |
| GET    | `/v1/resumes`                           | public       | List resumes with filters                                |
| GET    | `/v1/resumes/{resume_uuid}`             | public       | Resume                                                   |
| PATCH  | `/v1/resumes/{resume_uuid}`             | owner        | Update a resume                                          |
| DELETE | `/v1/resumes/{resume_uuid}`             | owner        | Delete a resume                                          |
| POST   | `/v1/resumes/{resume_uuid}/view`        | owner        | Move viewed invitations to `invitations_corp_uuids`      |
| POST   | `/v1/resumes/{resume_uuid}/invitation`  | corporation  | Invite the hero (`409` if already invited)               |
| GET    | `/health`                               | public       | Liveness probe                                           |

`invitations_corp_uuids` / `new_invitations_corp_uuids` are returned only to the resume owner, `null` for others.

List filters (all optional, combined with AND):

- `min_offer`, `max_offer` — expected offer range (resumes without an offer are excluded)
- `min_work_experience` — heroes with at least N years
- `powers_ids` — heroes having any of these powers, e.g. `?powers_ids=1&powers_ids=3`
- `limit` (1–100, default 50), `offset`

Resumes are sorted newest first (`created_at DESC`).

`PATCH` semantics: omitted fields are left unchanged, explicit `null` clears
`descriptions` / `previous_works` / `offer`. Invitations can't be changed via `PATCH`.

`/view` body: `{"invitations_corp_uuids": [...]}`. Only uuids present in `new_invitations_corp_uuids`
are moved (order is kept), unknown ones are ignored, so the call is idempotent.

## Tests

Tests run against a real Postgres: a throwaway schema is created and migrated before
the session and dropped after it. Without a reachable database the tests are skipped.

```bash
docker compose up -d postgres
uv run --package resumes pytest
```
