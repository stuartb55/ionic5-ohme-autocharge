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

- **`main.py`** — async polling loop. Plug/unplug transition tracking lives in the `PlugInDetector` class (shared with `api.poll_loop` so the once-per-session state machine isn't duplicated): `prime()` seeds the startup state, `update()` calls `handle_plugin_event` on plug-in and resets on unplug. To survive container restarts mid-session, `update()` persists a `sessionActive` marker (via `settings.save_session_active`) once a plug-in is handled and clears it on unplug; `prime()` reads it back so a car still connected at startup is treated as already-handled (no duplicate `charge_sessions` row, no repeat ntfy — Ohme keeps its rule server-side) unless the marker is false, meaning the car was plugged in *while the container was down* and the session still needs configuring. `handle_plugin_event` wraps its Ohme `set_target` write in `store.client_lock` so it can't interleave with the dashboard's own target reapply or a charge-summary read; the slow Bluelink SOC fetch stays outside the lock. `bluelink.get_battery_percentage()` is synchronous (third-party SDK limitation) so it runs via `asyncio.to_thread`. Ntfy message uses `client.current_vehicle` (populated by `set_target` → `async_update_device_info`).
- **`ohme_client.py`** — async wrapper around the `ohme` library. `set_target` calculates the top-up amount needed (target - current SOC) and sends only that to Ohme (does NOT send the current SOC itself, as Ohme interprets it as "energy already added"). Must call `async_update_device_info` first before other Ohme calls or internal state won't be populated.
- **`bluelink.py`** — synchronous wrapper around `hyundai_kia_connect_api`. `get_vehicle_state(vehicle_id=None)` returns a `VehicleState` (SOC plus driving range and odometer normalised to miles via `_to_miles`, battery state-of-health %, and read-only lock status + GPS location); SOC is required, the rest are best-effort extras (SoH is captured per plug-in into `charge_sessions.soh_percent` for a degradation trend; lock/location are display-only via `/api/status` `vehicle.isLocked`/`vehicle.location`). `vehicle_id` selects which vehicle when the account has more than one (callers pass `store.selected_vehicle_id`); `list_vehicles()` enumerates them for the dashboard picker (`GET /api/vehicles`, `PUT /api/settings/vehicle`). `get_battery_percentage()` is a thin wrapper returning just `.soc`. Uses a module-level singleton `_manager` so the `VehicleManager` is created and authenticated only once per process lifetime. The SDK isn't thread-safe and the read has two concurrent `asyncio.to_thread` callers (the poll loop and the dashboard's target reapply), so a module-level `threading.Lock` serialises every access to the manager.
- **`octopus.py`** — optional Octopus awareness, two independent features. (1) **Agile tariff** (no auth): `fetch_rates()` pulls upcoming half-hourly unit rates from Octopus's public API and converts pence→£; no-op (returns None) when `OCTOPUS_PRODUCT_CODE`/`OCTOPUS_REGION` are unset or on error. Served via `GET /api/tariff` (cached 30 min, serves stale on failure); the dashboard's tariff card hides when disabled. The fetch also caches the rates onto `store.agile_rates` so `cost_for_slots(slots, rates)` can price the session's Ohme slots against the actual per-slot rate (each slot's energy spread uniformly over its span) — `build_snapshot` uses this for an Agile-accurate `projected_cost` (`projectedCostMethod="agile"`), falling back to the flat `avg_price_per_kwh` (`"average"`) when rates are missing or don't fully cover the schedule. (2) **Household consumption** (needs an account; enabled by `consumption_is_enabled()` when `OCTOPUS_API_KEY`/`OCTOPUS_ACCOUNT_NUMBER` are set): `_discover_meter()` finds the electricity *import* meter (MPAN + serial) once from the account endpoint and caches it (module-level `_meter`, like `bluelink._manager`); `fetch_consumption(from, to)` returns half-hourly whole-house import (`[{from, to, importKwh}]`, following pagination). Both use HTTP Basic auth built by hand (`_auth_headers`, key as username, empty password) to avoid the deprecated `aiohttp.BasicAuth`. Powers the energy-usage feature (see `energy.py`).
- **`energy.py`** — pure (no I/O) helpers for the household-vs-car breakdown. `attribute_car_kwh(telemetry_rows)` reconstructs the car's per-half-hour share from the cumulative `session_energy_wh` in the `telemetry` history (positive deltas split proportionally across the half-hour slots they overlap; a negative delta = a new session, treated as energy-from-zero), keyed by canonical UTC slot-start ISO. `merge_usage(import_rows, car_by_slot)` combines that with the Octopus import to yield `[{start, end, importKwh, carKwh, houseKwh}]` where `houseKwh = max(0, import − car)` and car is capped at the metered import (the clamps absorb timing skew between the two sources). `api._persist_grid_consumption` (poll loop, daily-stats cadence) wires Octopus + telemetry through these into the `grid_consumption` table; `GET /api/energy-usage?date=YYYY-MM-DD` (default yesterday, since Octopus data lags ~a day) serves a day's 48 slots + totals (`enabled: false` when consumption or persistence is off, hiding the dashboard card).
- **`ntfy.py`** — optional push notifications via ntfy.sh, called directly as `ntfy.send(...)` from the notification sites in `main.py`/`api.py`. Silently disabled when `NTFY_TOPIC` is unset. The poll loop also sends a weekly summary digest (`api._maybe_send_weekly_digest`) on `WEEKLY_DIGEST_DAY`/`WEEKLY_DIGEST_HOUR` (local), guarded by `store.last_digest_date` so it fires once per scheduled day.
- **`config.py`** — loads all settings from env/`.env` at import time. Required vars raise `KeyError` on startup if missing; optional vars have defaults.
- **`db.py`** — optional Postgres persistence for charging history (for Grafana). Enabled only when `DATABASE_URL` is set; when unset or the DB is unreachable at startup, every helper is a no-op and the app runs entirely in memory as before (same graceful-degradation pattern as `ntfy`). All writes are best-effort. `main.handle_plugin_event` records a `charge_sessions` row (+ `schedule_snapshots`) per plug-in; `api.poll_loop` appends a `telemetry` row each poll and refreshes `daily_stats` every `DAILY_STATS_INTERVAL`; `api.get_statistics` also upserts `daily_stats` opportunistically. `db.get_soh_history` reads the per-plug-in `soh_percent` column back as a trend (collapsing consecutive unchanged readings to one point per change) for the dashboard's battery-health sparkline via `GET /api/soh-history` (`enabled: false` when persistence is off, mirroring `/api/sessions`). The `grid_consumption` table (half-hourly whole-house import + car/house split) is upserted by `api._persist_grid_consumption` on the daily-stats cadence and read back by `db.get_grid_consumption` for `GET /api/energy-usage`; `db.get_telemetry_between` feeds `energy.attribute_car_kwh` the cumulative session energy it needs. See `docs/grafana.md` for the schema and example queries.
- **`settings.py`** — runtime-adjustable settings persisted to a JSON file (`SETTINGS_PATH`), all keys in one object so each setter does a read-modify-write. Holds the charge target (`PUT /api/settings/target`), an optional "ready-by" departure time (`PUT /api/settings/ready-by`, an `HH:MM` string or null), and optional per-weekday target overrides (`PUT /api/settings/day-targets`, a full `{0(Mon)..6(Sun): percent}` map). The base target lives on `state.store` (`charge_target` property / `set_charge_target`): the runtime override if set, else `config.CHARGE_TARGET`. `store.effective_target` resolves what to use *right now* — today's per-weekday override (in `config.TIMEZONE`) if set, else the base — and is what `main.handle_plugin_event` and `api.build_snapshot` read (never `config.CHARGE_TARGET` directly). Ready-by lives on `store.ready_by` (+ `ready_by_tuple` parsed for Ohme); when set it's passed to `ohme_client.set_target` as `target_time` so the charge completes by then. When the user hasn't set an override, the dashboard field auto-populates from Ohme's own configured time: `build_snapshot` reads `client.target_time` into `snapshot.ohme_ready_by` (valid even when unplugged), and `/api/status` serves `config.readyBy = store.ready_by or ohme_ready_by` plus `readyByIsManual`. Any settings change goes through `api._reapply_target_if_connected` (no args — reads `effective_target`/`ready_by`) so an active session re-plans immediately. The same file also holds a non-user `sessionActive` marker (`load_session_active`/`save_session_active`) that `PlugInDetector` uses to avoid re-recording/re-notifying an already-handled session across a container restart. Persistence is best-effort — if the file can't be written the settings stay in memory only (and a restart could re-record one duplicate session, the pre-fix behaviour).

## Configuration

Copy `.env.example` to `.env`. Required vars: `HYUNDAI_USERNAME`, `HYUNDAI_PASSWORD`, `HYUNDAI_PIN`, `OHME_EMAIL`, `OHME_PASSWORD`. Optional: `CHARGE_TARGET` (default 80, the initial/fallback target), `POLL_INTERVAL` (default 180s), `LIVE_SOC_INTERVAL` (default 30min; how often the poll loop re-reads the SOC from Bluelink *while charging* so the battery ring climbs through the session — reads Hyundai's cached state so it never wakes the car; 0 disables the climb. Independently, `_maybe_refresh_live_soc` *seeds* the SOC once whenever the car is connected but no real reading is held — e.g. after a container restart mid-session, where `prime()` won't re-run `handle_plugin_event` — so the ring shows the real SOC instead of Ohme's unreliable `battery` estimate), `SETTINGS_PATH` (default `/app/data/settings.json`; a named volume is mounted there in both compose files so a dashboard-changed target survives restarts), `NTFY_TOPIC`, `NTFY_URL`, `NTFY_TOKEN`, `CORS_ORIGINS`, `DATABASE_URL` (blank disables Postgres history persistence; both compose files bundle a `postgres` service and default this to it), `DAILY_STATS_INTERVAL` (default 6h; how often the poll loop refreshes Ohme's daily totals into Postgres — also the cadence for the Octopus household-consumption ingest). For the optional Agile tariff card: `OCTOPUS_PRODUCT_CODE`, `OCTOPUS_REGION` (public, no auth). For the optional household-vs-car energy card: `OCTOPUS_API_KEY` + `OCTOPUS_ACCOUNT_NUMBER` (needs an Octopus account; the import meter is auto-discovered) — also requires `DATABASE_URL`, since the car share is reconstructed from the telemetry history.

## Testing

Tests live in `tests/`. `conftest.py` sets stub env vars before `config.py` is imported — any new required env var must be added there too. All tests mock at the module boundary (patch `bluelink._get_manager`, mock `OhmeApiClient`, etc.) rather than hitting real APIs. `pytest.ini` sets `asyncio_mode = auto` so async tests work without decorators.

**Timezone in tests:** CI and the containers run in **UTC**, but local dev machines are often on UK time (BST/GMT). Never assert on a rendered/formatted date or time with a hard-coded clock string (e.g. expecting `"05:00"`) — it will pass locally and fail in CI when the value renders in a different zone (and may even roll to a different calendar day, adding/removing a weekday prefix). Instead match a pattern (`/\d{1,2}:\d{2}/`), compute the expected value through the same formatter, or use offset-free timestamps. The day-bucketing logic itself has the matching production concern — see `config.TIMEZONE` and `api._STATS_TZ`.

## Single-worker constraint

The backend must run as exactly **one uvicorn worker** (the Dockerfile CMD does this). All state is in-process: the `state.store` singleton, the background poll loop, the single authenticated Ohme client and the statistics cache. Running multiple workers would start one poll loop per worker (duplicate Ohme logins, duplicate DB writes) and serve inconsistent snapshots. Never add `--workers` or front it with a multi-worker process manager.

## Docker

`docker-compose.yml` is for local dev (builds from source). `docker-compose.prod.yml` is for the Mac Mini home server and pulls the pre-built image from GHCR. Both bundle a `postgres:16-alpine` service (DB/user `autocharge`, port `5432` published) for charging history; an existing Grafana points at it. The backend `depends_on` Postgres with `condition: service_healthy`. CI (`.github/workflows/docker.yml`) runs tests first, then builds and pushes a multi-platform (`linux/amd64` + `linux/arm64`) image on every push to `main`.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
