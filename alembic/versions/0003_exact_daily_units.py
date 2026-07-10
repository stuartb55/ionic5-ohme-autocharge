"""Store daily energy and money in exact base/minor units."""

from alembic import op

revision = "0003_exact_daily_units"
down_revision = "0002_actual_cost"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE daily_stats ADD COLUMN IF NOT EXISTS energy_wh BIGINT")
    op.execute("ALTER TABLE daily_stats ADD COLUMN IF NOT EXISTS savings_minor BIGINT")
    op.execute("ALTER TABLE daily_stats ADD COLUMN IF NOT EXISTS cost_minor BIGINT")
    # Backfill the historical float columns once. Future writes populate both so
    # existing Grafana dashboards remain compatible during the transition.
    op.execute(
        "UPDATE daily_stats SET "
        "energy_wh = COALESCE(energy_wh, ROUND(COALESCE(energy_kwh, 0) * 1000)), "
        "savings_minor = COALESCE(savings_minor, ROUND(COALESCE(savings, 0) * "
        "CASE currency WHEN 'JPY' THEN 1 WHEN 'KWD' THEN 1000 ELSE 100 END)), "
        "cost_minor = COALESCE(cost_minor, ROUND(COALESCE(cost, 0) * "
        "CASE currency WHEN 'JPY' THEN 1 WHEN 'KWD' THEN 1000 ELSE 100 END))"
    )
    op.execute("ALTER TABLE daily_stats ALTER COLUMN energy_wh SET DEFAULT 0")
    op.execute("ALTER TABLE daily_stats ALTER COLUMN savings_minor SET DEFAULT 0")
    op.execute("ALTER TABLE daily_stats ALTER COLUMN cost_minor SET DEFAULT 0")
    op.execute("ALTER TABLE daily_stats ALTER COLUMN energy_wh SET NOT NULL")
    op.execute("ALTER TABLE daily_stats ALTER COLUMN savings_minor SET NOT NULL")
    op.execute("ALTER TABLE daily_stats ALTER COLUMN cost_minor SET NOT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE daily_stats DROP COLUMN IF EXISTS cost_minor")
    op.execute("ALTER TABLE daily_stats DROP COLUMN IF EXISTS savings_minor")
    op.execute("ALTER TABLE daily_stats DROP COLUMN IF EXISTS energy_wh")
