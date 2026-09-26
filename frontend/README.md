# frontend

A minimal UI for manual end-to-end testing: plain HTML/CSS/JS without a build step, served by nginx.

```
browser ──▶ nginx :3000 ──/auth, /v1 (HTTP + WebSocket)──▶ gateway :8000
             └── static files from ./public
```

nginx proxies the API, so the page and the API share one origin: no CORS setup in the gateway is needed.

## Features

- Register / log in as `hero` or `corporation`.
- Notifications WebSocket (`/v1/notifications/ws?token=…`) with auto-reconnect and a live feed.
- Profile: create / update the hero or corporation card (name, description, image).
- Hero: own resumes (CRUD, invitations from corporations, mark as viewed) and mission search with responding.
- Corporation: own missions (CRUD, hero respondents, mark as viewed) and resume search with inviting.
- `API log` at the bottom left shows every request with its status and timing.

The session is kept in `sessionStorage`, so every browser tab has its own login: open a hero in one tab
and a corporation in another to watch the notifications going both ways.

## Run

```bash
docker compose up -d frontend
open http://localhost:3000
```

The files are mounted into the container, so changes are visible after a page reload.
