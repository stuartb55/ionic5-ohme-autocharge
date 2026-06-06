# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

Polls the Ohme home charger every N seconds. When it detects the car transitioning from unplugged → plugged in, it fetches the Hyundai IONIC 5's battery SOC from the Hyundai Bluelink EU API and configures Ohme to stop charging at the target percentage (default 80%).

## Git workflow

Always start a new branch for each distinct feature or fix — one branch (and one PR) per change. Never reuse an existing branch for an unrelated change, and never reuse a branch whose PR has already been merged (new commits won't be added to a merged PR; they need a fresh branch and PR).

## Commands

```bash
# Install runtime dependencies
pip install -r requirements.txt

# Install dev dependencies (includes pytest)
pip install -r requirements-dev.txt

# Run all tests
pytest

# Run a single test file
pytest tests/test_bluelink.py

# Run a single test by name
pytest tests/test_bluelink.py::test_returns_battery_percentage

# Run the app continuously
python main.py

# Run once (fetch SOC and set target immediately, then exit — used in CI/smoke tests)
python main.py --once
```

## Architecture

The app has these modules that form a thin pipeline:

- **`main.py`** — async polling loop. Tracks plug/unplug state transitions with `was_connected` / `session_handled` flags, calls `handle_plugin_event` on plug-in, resets on unplug. `bluelink.get_battery_percentage()` is synchronous (third-party SDK limitation) so it runs via `asyncio.to_thread`. Ntfy message uses `client.current_vehicle` (populated by `set_target` → `async_update_device_info`).
- **`ohme_client.py`** — async wrapper around the `ohme` library. `set_target` calculates the top-up amount needed (target - current SOC) and sends only that to Ohme (does NOT send the current SOC itself, as Ohme interprets it as "energy already added"). Must call `async_update_device_info` first before other Ohme calls or internal state won't be populated.
- **`bluelink.py`** — synchronous wrapper around `hyundai_kia_connect_api`. Uses a module-level singleton `_manager` so the `VehicleManager` is created and authenticated only once per process lifetime.
- **`ntfy.py`** — optional push notifications via ntfy.sh. Silently disabled when `NTFY_TOPIC` is unset.
- **`config.py`** — loads all settings from env/`.env` at import time. Required vars raise `KeyError` on startup if missing; optional vars have defaults.
- **`db.py`** — optional Postgres persistence for charging history (for Grafana). Enabled only when `DATABASE_URL` is set; when unset or the DB is unreachable at startup, every helper is a no-op and the app runs entirely in memory as before (same graceful-degradation pattern as `ntfy`). All writes are best-effort. `main.handle_plugin_event` records a `charge_sessions` row (+ `schedule_snapshots`) per plug-in; `api.poll_loop` appends a `telemetry` row each poll and refreshes `daily_stats` every `DAILY_STATS_INTERVAL`; `api.get_statistics` also upserts `daily_stats` opportunistically. See `docs/grafana.md` for the schema and example queries.
- **`settings.py`** — runtime-adjustable settings persisted to a JSON file (`SETTINGS_PATH`). Currently just the charge target, which the dashboard can change via `PUT /api/settings/target`. The active target lives on `state.store` (`charge_target` property / `set_charge_target`): the runtime override if set, else `config.CHARGE_TARGET`. `main.handle_plugin_event` and `api.build_snapshot` read `store.charge_target`, never `config.CHARGE_TARGET` directly. Persistence is best-effort — if the file can't be written the target stays in memory only.

## Configuration

Copy `.env.example` to `.env`. Required vars: `HYUNDAI_USERNAME`, `HYUNDAI_PASSWORD`, `HYUNDAI_PIN`, `OHME_EMAIL`, `OHME_PASSWORD`. Optional: `CHARGE_TARGET` (default 80, the initial/fallback target), `POLL_INTERVAL` (default 180s), `SETTINGS_PATH` (default `/app/data/settings.json`; a named volume is mounted there in both compose files so a dashboard-changed target survives restarts), `NTFY_TOPIC`, `NTFY_URL`, `NTFY_TOKEN`, `CORS_ORIGINS`, `DATABASE_URL` (blank disables Postgres history persistence; both compose files bundle a `postgres` service and default this to it), `DAILY_STATS_INTERVAL` (default 6h; how often the poll loop refreshes Ohme's daily totals into Postgres).

## Testing

Tests live in `tests/`. `conftest.py` sets stub env vars before `config.py` is imported — any new required env var must be added there too. All tests mock at the module boundary (patch `bluelink._get_manager`, mock `OhmeApiClient`, etc.) rather than hitting real APIs. `pytest.ini` sets `asyncio_mode = auto` so async tests work without decorators.

## Docker

`docker-compose.yml` is for local dev (builds from source). `docker-compose.prod.yml` is for the Mac Mini home server and pulls the pre-built image from GHCR. Both bundle a `postgres:16-alpine` service (DB/user `autocharge`, port `5432` published) for charging history; an existing Grafana points at it. The backend `depends_on` Postgres with `condition: service_healthy`. CI (`.github/workflows/docker.yml`) runs tests first, then builds and pushes a multi-platform (`linux/amd64` + `linux/arm64`) image on every push to `main`.
