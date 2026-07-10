"""Persist tariff intervals and reconciled actual session cost."""

from alembic import op

revision = "0002_actual_cost"
down_revision = "0001_session_model"
branch_labels = None
depends_on = None


def upgrade() -> None:
    statements = (
        "ALTER TABLE charge_sessions ADD COLUMN IF NOT EXISTS actual_cost_minor BIGINT",
        "ALTER TABLE charge_sessions ADD COLUMN IF NOT EXISTS cost_currency TEXT",
        "ALTER TABLE charge_sessions ADD COLUMN IF NOT EXISTS cost_method TEXT",
        "ALTER TABLE charge_sessions ADD COLUMN IF NOT EXISTS tariff_coverage DOUBLE PRECISION",
        "ALTER TABLE charge_sessions ADD COLUMN IF NOT EXISTS reconstructed_energy_wh BIGINT",
        "ALTER TABLE charge_sessions ADD COLUMN IF NOT EXISTS reconciliation_delta_wh BIGINT",
        """
        CREATE TABLE IF NOT EXISTS tariff_rates (
            valid_from TIMESTAMPTZ NOT NULL,
            valid_to TIMESTAMPTZ NOT NULL,
            price_minor_per_kwh NUMERIC(12, 6) NOT NULL,
            currency TEXT NOT NULL,
            source TEXT NOT NULL,
            ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (valid_from, source)
        )
        """,
        "CREATE INDEX IF NOT EXISTS tariff_rates_window_idx ON tariff_rates (valid_from, valid_to)",
        """
        CREATE TABLE IF NOT EXISTS charging_intervals (
            session_id BIGINT NOT NULL REFERENCES charge_sessions(id) ON DELETE CASCADE,
            interval_start TIMESTAMPTZ NOT NULL,
            interval_end TIMESTAMPTZ NOT NULL,
            energy_wh BIGINT NOT NULL,
            cost_minor BIGINT,
            rate_minor_per_kwh NUMERIC(12, 6),
            currency TEXT,
            quality_status TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'ohme_counter',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (session_id, interval_start)
        )
        """,
        """
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'charging_intervals_energy_check') THEN
            ALTER TABLE charging_intervals ADD CONSTRAINT charging_intervals_energy_check
              CHECK (energy_wh >= 0) NOT VALID;
          END IF;
        END $$
        """,
    )
    for statement in statements:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS charging_intervals")
    op.execute("DROP TABLE IF EXISTS tariff_rates")
    for column in (
        "reconciliation_delta_wh", "reconstructed_energy_wh", "tariff_coverage",
        "cost_method", "cost_currency", "actual_cost_minor",
    ):
        op.execute(f"ALTER TABLE charge_sessions DROP COLUMN IF EXISTS {column}")
