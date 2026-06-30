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

# Optional: pin which vehicle to read when the account has more than one (the
# vehicle id from GET /api/vehicles). Blank = use the first vehicle. The
# dashboard can override this at runtime (persisted in settings.json).
HYUNDAI_VEHICLE_ID = os.getenv("HYUNDAI_VEHICLE_ID", "")

OHME_EMAIL = os.environ["OHME_EMAIL"]
OHME_PASSWORD = os.environ["OHME_PASSWORD"]

# Build version (git SHA), baked into the image at build time (see Dockerfile).
# Empty in local/dev runs; surfaced via GET /api/version.
APP_VERSION = os.getenv("APP_VERSION", "")

CHARGE_TARGET = int(os.getenv("CHARGE_TARGET", "80"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "180"))

# Maximum seconds to wait on a single upstream call (Hyundai Bluelink / Ohme)
# before giving up and treating it as a failed read. Stops a hung or very slow
# upstream from stalling the poll loop — and, for Bluelink (a blocking SDK run in
# a worker thread under a module lock), from holding that lock from the caller's
# view. On timeout the loop keeps the last-known-good snapshot and retries next
# interval. Default 30s.
UPSTREAM_TIMEOUT = int(os.getenv("UPSTREAM_TIMEOUT", "30"))

# Upper bound (seconds) on the poll loop's back-off when upstreams are failing.
# After a run of consecutive failed polls the loop waits POLL_INTERVAL * 2**(n-1),
# capped here, so a sustained Ohme/Bluelink outage isn't hammered every interval;
# it snaps back to POLL_INTERVAL on the first success. Default 30 min.
MAX_POLL_BACKOFF = int(os.getenv("MAX_POLL_BACKOFF", str(30 * 60)))

# How often (seconds) to re-read the live SOC from Bluelink while a charge is
# actively running, so the dashboard battery ring climbs during the session
# instead of sitting at the plug-in reading. Reads Hyundai's server-side cached
# state (the car pushes updates while charging), so it never wakes/drains the
# car. Default 30 min; 0 disables mid-charge refresh (SOC stays at plug-in).
LIVE_SOC_INTERVAL = int(os.getenv("LIVE_SOC_INTERVAL", str(30 * 60)))

NTFY_TOPIC = os.getenv("NTFY_TOPIC", "")
NTFY_URL = os.getenv("NTFY_URL", "https://ntfy.sh")
NTFY_TOKEN = os.getenv("NTFY_TOKEN", "")

# Weekly charging-summary digest via ntfy. Sent once a week on this weekday
# (0=Mon … 6=Sun) at this local hour. -1 (or any value outside 0–6) disables it;
# it also requires NTFY_TOPIC. Default: Monday 08:00.
WEEKLY_DIGEST_DAY = int(os.getenv("WEEKLY_DIGEST_DAY", "0"))
WEEKLY_DIGEST_HOUR = int(os.getenv("WEEKLY_DIGEST_HOUR", "8"))

# Optional Postgres persistence for charging history (consumed by Grafana). When
# blank, history persistence is disabled and the app runs entirely in memory as
# before. Example: postgresql://autocharge:secret@postgres:5432/autocharge
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Optional Octopus Agile (dynamic tariff) awareness. Both must be set to enable;
# blank disables the tariff card. PRODUCT_CODE is the Agile product (e.g.
# "AGILE-24-10-01"); REGION is the single-letter DNO region (A–P). Used to build
# the public unit-rate URL — no account/auth needed.
OCTOPUS_PRODUCT_CODE = os.getenv("OCTOPUS_PRODUCT_CODE", "")
OCTOPUS_REGION = os.getenv("OCTOPUS_REGION", "")

# Optional Octopus household-consumption awareness (separate from the Agile rates
# above — this needs an account). Both must be set to enable the energy-usage card
# and its Postgres persistence. The API key is the account-level key from your
# Octopus dashboard; the account number (e.g. "A-AAAA1111") lets the app discover
# your electricity import meter (MPAN + serial) automatically. Used with HTTP Basic
# auth (key as username, empty password) against the authenticated consumption API.
OCTOPUS_API_KEY = os.getenv("OCTOPUS_API_KEY", "")
OCTOPUS_ACCOUNT_NUMBER = os.getenv("OCTOPUS_ACCOUNT_NUMBER", "")

# How often (seconds) the poll loop refreshes Ohme's daily totals into Postgres.
# Independent of the dashboard being open. Default 6h.
DAILY_STATS_INTERVAL = int(os.getenv("DAILY_STATS_INTERVAL", str(6 * 60 * 60)))

# How long (days) to keep per-poll telemetry rows in Postgres. One row per poll
# is ~175k rows/year at the default POLL_INTERVAL, so without pruning the table
# grows forever. Pruning runs on the daily-stats cadence; 0 keeps rows forever.
TELEMETRY_RETENTION_DAYS = int(os.getenv("TELEMETRY_RETENTION_DAYS", "365"))

# Timezone used to bucket Ohme's per-day statistics: Ohme days start at local
# midnight, so attributing a bucket to a calendar date must use this zone, not
# the host's (containers default to UTC). Defaults to the UK since this app is
# GBP/UK-only. Respects TZ when set so one variable can drive logs and stats.
TIMEZONE = os.getenv("TIMEZONE") or os.getenv("TZ") or "Europe/London"
