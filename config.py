import os
from dotenv import load_dotenv

load_dotenv()

HYUNDAI_USERNAME = os.environ["HYUNDAI_USERNAME"]
HYUNDAI_PASSWORD = os.environ["HYUNDAI_PASSWORD"]
HYUNDAI_PIN = os.environ["HYUNDAI_PIN"]

OHME_EMAIL = os.environ["OHME_EMAIL"]
OHME_PASSWORD = os.environ["OHME_PASSWORD"]

CHARGE_TARGET = int(os.getenv("CHARGE_TARGET", "80"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "180"))

NTFY_TOPIC = os.getenv("NTFY_TOPIC", "")
NTFY_URL = os.getenv("NTFY_URL", "https://ntfy.sh")
NTFY_TOKEN = os.getenv("NTFY_TOKEN", "")

# Optional Postgres persistence for charging history (consumed by Grafana). When
# blank, history persistence is disabled and the app runs entirely in memory as
# before. Example: postgresql://autocharge:secret@postgres:5432/autocharge
DATABASE_URL = os.getenv("DATABASE_URL", "")

# How often (seconds) the poll loop refreshes Ohme's daily totals into Postgres.
# Independent of the dashboard being open. Default 6h.
DAILY_STATS_INTERVAL = int(os.getenv("DAILY_STATS_INTERVAL", str(6 * 60 * 60)))

# How long (days) to keep per-poll telemetry rows in Postgres. One row per poll
# is ~175k rows/year at the default POLL_INTERVAL, so without pruning the table
# grows forever. Pruning runs on the daily-stats cadence; 0 keeps rows forever.
TELEMETRY_RETENTION_DAYS = int(os.getenv("TELEMETRY_RETENTION_DAYS", "365"))
