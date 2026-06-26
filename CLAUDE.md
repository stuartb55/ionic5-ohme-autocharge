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

- **`main.py`** — async polling loop. Plug/unplug transition tracking lives in the `PlugInDetector` class (shared with `api.poll_loop` so the once-per-session state machine isn't duplicated): `prime()` seeds the startup state, `update()` calls `handle_plugin_event` on plug-in and resets on unplug. `handle_plugin_event` wraps its Ohme `set_target` write in `store.client_lock` so it can't interleave with the dashboard's own target reapply or a charge-summary read; the slow Bluelink SOC fetch stays outside the lock. `bluelink.get_battery_percentage()` is synchronous (third-party SDK limitation) so it runs via `asyncio.to_thread`. Ntfy message uses `client.current_vehicle` (populated by `set_target` → `async_update_device_info`).
- **`ohme_client.py`** — async wrapper around the `ohme` library. `set_target` calculates the top-up amount needed (target - current SOC) and sends only that to Ohme (does NOT send the current SOC itself, as Ohme interprets it as "energy already added"). Must call `async_update_device_info` first before other Ohme calls or internal state won't be populated.
- **`bluelink.py`** — synchronous wrapper around `hyundai_kia_connect_api`. `get_vehicle_state(vehicle_id=None)` returns a `VehicleState` (SOC plus driving range and odometer normalised to miles via `_to_miles`, and battery state-of-health %); SOC is required, the rest are best-effort extras (SoH is captured per plug-in into `charge_sessions.soh_percent` for a degradation trend and shown on the dashboard). `vehicle_id` selects which vehicle when the account has more than one (callers pass `store.selected_vehicle_id`); `list_vehicles()` enumerates them for the dashboard picker (`GET /api/vehicles`, `PUT /api/settings/vehicle`). `get_battery_percentage()` is a thin wrapper returning just `.soc`. Uses a module-level singleton `_manager` so the `VehicleManager` is created and authenticated only once per process lifetime. The SDK isn't thread-safe and the read has two concurrent `asyncio.to_thread` callers (the poll loop and the dashboard's target reapply), so a module-level `threading.Lock` serialises every access to the manager.
- **`ntfy.py`** — optional push notifications via ntfy.sh. Silently disabled when `NTFY_TOPIC` is unset. The poll loop also sends a weekly summary digest (`api._maybe_send_weekly_digest`) on `WEEKLY_DIGEST_DAY`/`WEEKLY_DIGEST_HOUR` (local), guarded by `store.last_digest_date` so it fires once per scheduled day.
- **`config.py`** — loads all settings from env/`.env` at import time. Required vars raise `KeyError` on startup if missing; optional vars have defaults.
- **`db.py`** — optional Postgres persistence for charging history (for Grafana). Enabled only when `DATABASE_URL` is set; when unset or the DB is unreachable at startup, every helper is a no-op and the app runs entirely in memory as before (same graceful-degradation pattern as `ntfy`). All writes are best-effort. `main.handle_plugin_event` records a `charge_sessions` row (+ `schedule_snapshots`) per plug-in; `api.poll_loop` appends a `telemetry` row each poll and refreshes `daily_stats` every `DAILY_STATS_INTERVAL`; `api.get_statistics` also upserts `daily_stats` opportunistically. See `docs/grafana.md` for the schema and example queries.
- **`settings.py`** — runtime-adjustable settings persisted to a JSON file (`SETTINGS_PATH`), all keys in one object so each setter does a read-modify-write. Holds the charge target (`PUT /api/settings/target`), an optional "ready-by" departure time (`PUT /api/settings/ready-by`, an `HH:MM` string or null), and optional per-weekday target overrides (`PUT /api/settings/day-targets`, a full `{0(Mon)..6(Sun): percent}` map). The base target lives on `state.store` (`charge_target` property / `set_charge_target`): the runtime override if set, else `config.CHARGE_TARGET`. `store.effective_target` resolves what to use *right now* — today's per-weekday override (in `config.TIMEZONE`) if set, else the base — and is what `main.handle_plugin_event` and `api.build_snapshot` read (never `config.CHARGE_TARGET` directly). Ready-by lives on `store.ready_by` (+ `ready_by_tuple` parsed for Ohme); when set it's passed to `ohme_client.set_target` as `target_time` so the charge completes by then. When the user hasn't set an override, the dashboard field auto-populates from Ohme's own configured time: `build_snapshot` reads `client.target_time` into `snapshot.ohme_ready_by` (valid even when unplugged), and `/api/status` serves `config.readyBy = store.ready_by or ohme_ready_by` plus `readyByIsManual`. Any settings change goes through `api._reapply_target_if_connected` (no args — reads `effective_target`/`ready_by`) so an active session re-plans immediately. Persistence is best-effort — if the file can't be written the settings stay in memory only.

## Configuration

Copy `.env.example` to `.env`. Required vars: `HYUNDAI_USERNAME`, `HYUNDAI_PASSWORD`, `HYUNDAI_PIN`, `OHME_EMAIL`, `OHME_PASSWORD`. Optional: `CHARGE_TARGET` (default 80, the initial/fallback target), `POLL_INTERVAL` (default 180s), `LIVE_SOC_INTERVAL` (default 30min; how often the poll loop re-reads the SOC from Bluelink *while charging* so the battery ring climbs through the session — reads Hyundai's cached state so it never wakes the car; 0 disables it), `SETTINGS_PATH` (default `/app/data/settings.json`; a named volume is mounted there in both compose files so a dashboard-changed target survives restarts), `NTFY_TOPIC`, `NTFY_URL`, `NTFY_TOKEN`, `CORS_ORIGINS`, `DATABASE_URL` (blank disables Postgres history persistence; both compose files bundle a `postgres` service and default this to it), `DAILY_STATS_INTERVAL` (default 6h; how often the poll loop refreshes Ohme's daily totals into Postgres).

## Testing

Tests live in `tests/`. `conftest.py` sets stub env vars before `config.py` is imported — any new required env var must be added there too. All tests mock at the module boundary (patch `bluelink._get_manager`, mock `OhmeApiClient`, etc.) rather than hitting real APIs. `pytest.ini` sets `asyncio_mode = auto` so async tests work without decorators.

**Timezone in tests:** CI and the containers run in **UTC**, but local dev machines are often on UK time (BST/GMT). Never assert on a rendered/formatted date or time with a hard-coded clock string (e.g. expecting `"05:00"`) — it will pass locally and fail in CI when the value renders in a different zone (and may even roll to a different calendar day, adding/removing a weekday prefix). Instead match a pattern (`/\d{1,2}:\d{2}/`), compute the expected value through the same formatter, or use offset-free timestamps. The day-bucketing logic itself has the matching production concern — see `config.TIMEZONE` and `api._STATS_TZ`.

## Single-worker constraint

The backend must run as exactly **one uvicorn worker** (the Dockerfile CMD does this). All state is in-process: the `state.store` singleton, the background poll loop, the single authenticated Ohme client and the statistics cache. Running multiple workers would start one poll loop per worker (duplicate Ohme logins, duplicate DB writes) and serve inconsistent snapshots. Never add `--workers` or front it with a multi-worker process manager.

## Docker

`docker-compose.yml` is for local dev (builds from source). `docker-compose.prod.yml` is for the Mac Mini home server and pulls the pre-built image from GHCR. Both bundle a `postgres:16-alpine` service (DB/user `autocharge`, port `5432` published) for charging history; an existing Grafana points at it. The backend `depends_on` Postgres with `condition: service_healthy`. CI (`.github/workflows/docker.yml`) runs tests first, then builds and pushes a multi-platform (`linux/amd64` + `linux/arm64`) image on every push to `main`.
