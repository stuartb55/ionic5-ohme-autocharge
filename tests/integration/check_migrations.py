"""Exercise the real Alembic chain against an isolated CI PostgreSQL service."""

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
import psycopg


def migration_config(url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).parents[2] / "alembic"))
    sqlalchemy_url = "postgresql+psycopg://" + url.removeprefix("postgresql://")
    cfg.set_main_option("sqlalchemy.url", sqlalchemy_url.replace("%", "%%"))
    return cfg


def main() -> None:
    if os.getenv("CI_MIGRATION_TEST") != "1":
        raise SystemExit("Refusing to reset a database without CI_MIGRATION_TEST=1")
    url = os.environ["DATABASE_URL"]
    cfg = migration_config(url)
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")

    # Simulate an installation stopped at the pre-exact-units revision.
    command.upgrade(cfg, "0002_actual_cost")
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO daily_stats (stat_date, energy_kwh, savings, cost, currency) "
            "VALUES ('2026-07-01', 1.25, 1.23, 0.46, 'GBP')"
        )

    command.upgrade(cfg, "head")
    command.upgrade(cfg, "head")  # deployments may safely rerun startup migration
    with psycopg.connect(url) as conn:
        revision = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        exact = conn.execute(
            "SELECT energy_wh, savings_minor, cost_minor FROM daily_stats "
            "WHERE stat_date = '2026-07-01'"
        ).fetchone()
        cursor_table = conn.execute("SELECT to_regclass('public.ingestion_cursors')").fetchone()[0]
        nullable = conn.execute(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_name = 'daily_stats' "
            "AND column_name IN ('energy_wh', 'savings_minor', 'cost_minor') "
            "AND is_nullable <> 'NO'"
        ).fetchone()[0]
    assert revision == "0004_ingestion_cursors"
    assert exact == (1250, 123, 46)
    assert cursor_table == "ingestion_cursors"
    assert nullable == 0


if __name__ == "__main__":
    main()
