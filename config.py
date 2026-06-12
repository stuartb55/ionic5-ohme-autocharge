import os
from dotenv import load_dotenv

load_dotenv()

# Validate all required vars up front so a missing one produces a single clear
# message naming everything that needs fixing, instead of a KeyError traceback
# for whichever happened to be read first. Empty values count as missing — an
# empty credential can never work.
_REQUIRED = ("HYUNDAI_USERNAME", "HYUNDAI_PASSWORD", "HYUNDAI_PIN", "OHME_EMAIL", "OHME_PASSWORD")
_missing = [name for name in _REQUIRED if not os.getenv(name)]
if _missing:
    raise SystemExit(
        "Missing required environment variables: "
        + ", ".join(_missing)
        + ". Copy .env.example to .env and fill in your credentials."
    )

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

# Timezone used to bucket Ohme's per-day statistics: Ohme days start at local
# midnight, so attributing a bucket to a calendar date must use this zone, not
# the host's (containers default to UTC). Defaults to the UK since this app is
# GBP/UK-only. Respects TZ when set so one variable can drive logs and stats.
TIMEZONE = os.getenv("TIMEZONE") or os.getenv("TZ") or "Europe/London"
