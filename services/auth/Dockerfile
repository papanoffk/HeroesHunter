# Build context: repository root (uv workspace with a shared uv.lock).
#   docker build -f services/auth/Dockerfile .

FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Dependencies only: this layer is rebuilt only when the lockfile changes.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=services/auth/pyproject.toml,target=services/auth/pyproject.toml \
    uv sync --locked --no-dev --no-install-workspace --package auth

COPY pyproject.toml uv.lock ./
COPY services/auth services/auth

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --package auth


FROM python:3.12-slim

RUN groupadd --system app && useradd --system --gid app --no-create-home app

# Same path as in the builder: the venv references the project source there.
COPY --from=builder --chown=app:app /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app/services/auth
USER app

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]

CMD ["uvicorn", "auth.main:app", "--host", "0.0.0.0", "--port", "8000"]
