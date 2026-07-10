"""Baseline existing tables and add durable session identity.

The CREATE/ALTER statements are deliberately idempotent so an existing deployment
that predates Alembic can adopt the migration without being stamped by hand.
"""

from alembic import op

revision = "0001_session_model"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    statements = (
        """
        CREATE TABLE IF NOT EXISTS charge_sessions (
            id BIGSERIAL PRIMARY KEY,
            plugged_in_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            vehicle_name TEXT,
            soc_percent INTEGER,
            target_percent INTEGER,
            topup_percent INTEGER,
            action TEXT,
            odometer_miles INTEGER,
            soh_percent INTEGER
        )
        """,
        "ALTER TABLE charge_sessions ADD COLUMN IF NOT EXISTS odometer_miles INTEGER",
        "ALTER TABLE charge_sessions ADD COLUMN IF NOT EXISTS soh_percent INTEGER",
        "ALTER TABLE charge_sessions ADD COLUMN IF NOT EXISTS session_key TEXT",
        "ALTER TABLE charge_sessions ADD COLUMN IF NOT EXISTS vehicle_id TEXT",
        "ALTER TABLE charge_sessions ADD COLUMN IF NOT EXISTS vin TEXT",
        "ALTER TABLE charge_sessions ADD COLUMN IF NOT EXISTS charger_id TEXT",
        "ALTER TABLE charge_sessions ADD COLUMN IF NOT EXISTS source_observed_at TIMESTAMPTZ",
        "ALTER TABLE charge_sessions ADD COLUMN IF NOT EXISTS unplugged_at TIMESTAMPTZ",
        "ALTER TABLE charge_sessions ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ",
        "ALTER TABLE charge_sessions ADD COLUMN IF NOT EXISTS end_soc_percent INTEGER",
        "ALTER TABLE charge_sessions ADD COLUMN IF NOT EXISTS actual_energy_wh BIGINT",
        "ALTER TABLE charge_sessions ADD COLUMN IF NOT EXISTS completion_reason TEXT",
        "ALTER TABLE charge_sessions ADD COLUMN IF NOT EXISTS quality_status TEXT NOT NULL DEFAULT 'unknown'",
        "ALTER TABLE charge_sessions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()",
        "CREATE UNIQUE INDEX IF NOT EXISTS charge_sessions_session_key_uidx ON charge_sessions (session_key) WHERE session_key IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS charge_sessions_vehicle_time_idx ON charge_sessions (vehicle_id, plugged_in_at)",
        """
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'charge_sessions_soc_check') THEN
            ALTER TABLE charge_sessions ADD CONSTRAINT charge_sessions_soc_check
              CHECK (soc_percent IS NULL OR soc_percent BETWEEN 0 AND 100) NOT VALID;
          END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'charge_sessions_target_check') THEN
            ALTER TABLE charge_sessions ADD CONSTRAINT charge_sessions_target_check
              CHECK (target_percent IS NULL OR target_percent BETWEEN 0 AND 100) NOT VALID;
          END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'charge_sessions_energy_check') THEN
            ALTER TABLE charge_sessions ADD CONSTRAINT charge_sessions_energy_check
              CHECK (actual_energy_wh IS NULL OR actual_energy_wh >= 0) NOT VALID;
          END IF;
        END $$
        """,
        """
        CREATE TABLE IF NOT EXISTS schedule_snapshots (
            id BIGSERIAL PRIMARY KEY,
            session_id BIGINT REFERENCES charge_sessions(id) ON DELETE CASCADE,
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            next_slot_start TIMESTAMPTZ,
            next_slot_end TIMESTAMPTZ,
            slots JSONB
        )
        """,
        "ALTER TABLE schedule_snapshots ADD COLUMN IF NOT EXISTS revision INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE schedule_snapshots ADD COLUMN IF NOT EXISTS reason TEXT NOT NULL DEFAULT 'initial'",
        "CREATE INDEX IF NOT EXISTS schedule_snapshots_session_idx ON schedule_snapshots (session_id, recorded_at)",
        """
        CREATE TABLE IF NOT EXISTS telemetry (
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            vehicle_name TEXT,
            battery_percent INTEGER,
            charger_status TEXT,
            connected BOOLEAN,
            charger_online BOOLEAN,
            power_watts DOUBLE PRECISION,
            power_amps DOUBLE PRECISION,
            power_volts INTEGER,
            target_percent INTEGER,
            session_energy_wh DOUBLE PRECISION
        )
        """,
        "ALTER TABLE telemetry ADD COLUMN IF NOT EXISTS session_id BIGINT REFERENCES charge_sessions(id) ON DELETE SET NULL",
        "ALTER TABLE telemetry ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'ohme'",
        "ALTER TABLE telemetry ADD COLUMN IF NOT EXISTS quality_status TEXT NOT NULL DEFAULT 'unknown'",
        "CREATE INDEX IF NOT EXISTS telemetry_recorded_at_idx ON telemetry (recorded_at)",
        "CREATE INDEX IF NOT EXISTS telemetry_session_time_idx ON telemetry (session_id, recorded_at)",
        """
        CREATE TABLE IF NOT EXISTS session_events (
            id BIGSERIAL PRIMARY KEY,
            session_id BIGINT NOT NULL REFERENCES charge_sessions(id) ON DELETE CASCADE,
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            event_type TEXT NOT NULL,
            details JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """,
        "CREATE INDEX IF NOT EXISTS session_events_session_time_idx ON session_events (session_id, occurred_at)",
        """
        CREATE TABLE IF NOT EXISTS daily_stats (
            stat_date DATE PRIMARY KEY,
            energy_kwh DOUBLE PRECISION,
            savings DOUBLE PRECISION,
            cost DOUBLE PRECISION,
            currency TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        "ALTER TABLE daily_stats ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'ohme_summary'",
        "ALTER TABLE daily_stats ADD COLUMN IF NOT EXISTS is_complete BOOLEAN NOT NULL DEFAULT false",
        """
        CREATE TABLE IF NOT EXISTS grid_consumption (
            interval_start TIMESTAMPTZ PRIMARY KEY,
            interval_end TIMESTAMPTZ,
            import_kwh DOUBLE PRECISION,
            car_kwh DOUBLE PRECISION,
            house_kwh DOUBLE PRECISION,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        "ALTER TABLE grid_consumption ADD COLUMN IF NOT EXISTS unattributed_kwh DOUBLE PRECISION NOT NULL DEFAULT 0",
        "ALTER TABLE grid_consumption ADD COLUMN IF NOT EXISTS quality_status TEXT NOT NULL DEFAULT 'unknown'",
    )
    for statement in statements:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS session_events")
    op.execute("DROP INDEX IF EXISTS telemetry_session_time_idx")
    op.execute("ALTER TABLE telemetry DROP COLUMN IF EXISTS quality_status")
    op.execute("ALTER TABLE telemetry DROP COLUMN IF EXISTS source")
    op.execute("ALTER TABLE telemetry DROP COLUMN IF EXISTS session_id")
    op.execute("ALTER TABLE schedule_snapshots DROP COLUMN IF EXISTS reason")
    op.execute("ALTER TABLE schedule_snapshots DROP COLUMN IF EXISTS revision")
    op.execute("ALTER TABLE grid_consumption DROP COLUMN IF EXISTS quality_status")
    op.execute("ALTER TABLE grid_consumption DROP COLUMN IF EXISTS unattributed_kwh")
    op.execute("ALTER TABLE daily_stats DROP COLUMN IF EXISTS is_complete")
    op.execute("ALTER TABLE daily_stats DROP COLUMN IF EXISTS source")
    for column in (
        "updated_at", "quality_status", "completion_reason", "actual_energy_wh",
        "end_soc_percent", "completed_at", "unplugged_at", "source_observed_at",
        "charger_id", "vin", "vehicle_id", "session_key",
    ):
        op.execute(f"ALTER TABLE charge_sessions DROP COLUMN IF EXISTS {column}")
