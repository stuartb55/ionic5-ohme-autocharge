"""Persist external ingestion progress for resumable historical backfills."""

from alembic import op

revision = "0004_ingestion_cursors"
down_revision = "0003_exact_daily_units"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ingestion_cursors (
            source TEXT PRIMARY KEY,
            cursor_at TIMESTAMPTZ NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ingestion_cursors")
