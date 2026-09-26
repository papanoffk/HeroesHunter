from pathlib import Path

from yoyo import get_backend, read_migrations

from auth.config import get_settings

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def main() -> None:
    backend = get_backend(get_settings().dsn(scheme="postgresql+psycopg"))
    migrations = read_migrations(str(MIGRATIONS_DIR))
    with backend.lock():
        pending = backend.to_apply(migrations)
        if not pending:
            print("No pending migrations, database is up to date")
            return
        backend.apply_migrations(pending)
    for migration in pending:
        print(f"Applied migration: {migration.id}")


if __name__ == "__main__":
    main()
