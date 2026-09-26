from pathlib import Path

import psycopg
from psycopg import sql
from yoyo import get_backend, read_migrations

from auth.config import Settings, get_settings

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def create_schema(settings: Settings) -> None:
    # yoyo only sets search_path to the schema, it does not create it.
    with psycopg.connect(settings.dsn(), autocommit=True) as conn:
        conn.execute(
            sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(settings.db_schema))
        )


def main() -> None:
    settings = get_settings()
    create_schema(settings)
    backend = get_backend(f"{settings.dsn(scheme='postgresql+psycopg')}?schema={settings.db_schema}")
    migrations = read_migrations(str(MIGRATIONS_DIR))
    with backend.lock():
        pending = backend.to_apply(migrations)
        if not pending:
            print(f"No pending migrations, schema {settings.db_schema!r} is up to date")
            return
        backend.apply_migrations(pending)
    for migration in pending:
        print(f"Applied migration to schema {settings.db_schema!r}: {migration.id}")


if __name__ == "__main__":
    main()
