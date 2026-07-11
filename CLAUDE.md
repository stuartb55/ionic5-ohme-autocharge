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
- **`bluelink.py`** — synchronous wrapper around `hyundai_kia_connect_api`. `get_vehicle_state(vehicle_id=None)` returns a `VehicleState` (SOC plus driving range and odometer normalised to miles via `_to_miles`, battery state-of-health %, read-only lock status + GPS location, and read-only health: 12V auxiliary battery % plus the SDK's own tyre-pressure/washer-fluid/key-fob-battery warning flags and an `open_items` list of any door/bonnet/boot reported open); SOC is required, the rest are best-effort extras (SoH is captured per plug-in into `charge_sessions.soh_percent` for a degradation trend; lock/location and health are display-only via `/api/status` `vehicle.isLocked`/`vehicle.location`/`vehicle.health`). Health is captured at plug-in like the other extras and only surfaced while connected; `api._maybe_notify_vehicle_health` fires one ntfy when a warning flag (or open item) newly appears (edge-triggered by comparing the previous snapshot), never on the 12V %, which has no vendor threshold. `vehicle_id` selects which vehicle when the account has more than one (callers pass `store.selected_vehicle_id`); `list_vehicles()` enumerates them for the dashboard picker (`GET /api/vehicles`, `PUT /api/settings/vehicle`). `get_battery_percentage()` is a thin wrapper returning just `.soc`. Uses a module-level singleton `_manager` so the `VehicleManager` is created and authenticated only once per process lifetime. The SDK isn't thread-safe and the read has two concurrent `asyncio.to_thread` callers (the poll loop and the dashboard's target reapply), so a module-level `threading.Lock` serialises every access to the manager.
- **`octopus.py`** — optional Octopus awareness. Agile rates are fetched in the background every 30 minutes, cached for projections, and persisted to `tariff_rates` so actual pricing never depends on opening the dashboard. `cost_for_slots` prices the planned schedule with Decimal arithmetic; after completion, `price_energy_buckets` prices reconstructed delivered Wh into integer pence only when every interval is covered exactly once. Gaps, overlaps or telemetry mismatch withhold the actual total and set a quality state. Household consumption discovers every import serial on the current property, refreshes that identity cache daily for meter exchanges, and aggregates same-slot readings before feeding `energy.py`.
- **`energy.py`** — pure helpers for household-vs-car attribution. Telemetry carries an explicit durable `session_id`; `attribute_car_kwh` only diffs counters within that session and rejects missing baselines, resets, implausible jumps and long gaps. `merge_usage` preserves uncertain meter intervals as `unattributedKwh` with a quality status, maintaining `import = car + house + unattributed` rather than silently clamping errors. `GET /api/energy-usage?date=YYYY-MM-DD` serves the local calendar day (46/48/50 half-hours across DST) and totals.
- **Statistics API contract** — `GET /api/statistics` returns the Pydantic-validated `StatisticsResponseModel`; do not bypass it with a raw `JSONResponse`. Its `metadata` records source, calculation type, observed-at/complete-through timestamps, quality and concrete coverage for summary, daily, efficiency, running-cost and comparison families. Keep the frontend `StatisticsResponse` and visible “Sources & methods” disclosure aligned whenever a metric changes.
- **Data-quality UI** — `Dashboard` polls `/api/data-quality` every five minutes and renders `DataQualitySection` only when persistence is available. Missing actual cost is applicable only when Agile pricing is configured; unavailable optional integrations must not be presented as failures. Session-related warnings link to the history section.
- **`ntfy.py`** — optional push notifications via ntfy.sh, called directly as `ntfy.send(...)` from the notification sites in `main.py`/`api.py`. Silently disabled when `NTFY_TOPIC` is unset. Every notification carries a `title` and an emoji `tags` value (the ntfy `X-Tags` header — e.g. `electric_plug` plug-in, `white_check_mark` finished/reconnected, `warning` problems, `bar_chart` digest — which renders as an icon on all clients, unlike markdown which phones show raw); multi-fact messages (the plug-in event and the weekly digest) use one-fact-per-line bodies. The poll loop also sends a weekly summary digest (`api._maybe_send_weekly_digest` → `_format_digest`) on `WEEKLY_DIGEST_DAY`/`WEEKLY_DIGEST_HOUR` (local), guarded by `store.last_digest_date` so it fires once per scheduled day.
- **`config.py`** — loads all settings from env/`.env` at import time. Missing required or invalid bounded numeric settings stop startup with one actionable message; optional vars have defaults.
- **`db.py`** — optional Postgres persistence for charging history (for Grafana). Enabled only when `DATABASE_URL` is set; when unset or the DB is unreachable at startup, every helper is a no-op and the app runs entirely in memory as before. Alembic migrations run automatically before the async pool opens; CI exercises the real chain and exact-unit legacy backfill on PostgreSQL. Each physical plug-in receives a durable `session_key`, lifecycle fields and an event audit trail. All writes remain best-effort. Daily energy/money have exact Wh/integer-minor-unit columns. Statistics use complete local days and same-vehicle fully-contained charge-to-drive intervals. `ingestion_cursors` advances only after successful consumption upserts, making the configurable initial backfill resumable. `GET /api/data-quality` aggregates applicable missing actuals, connected-but-unlinked telemetry, recent uncertain consumption, complete-day freshness, cursor progress and cache age without exposing raw sensitive data. `GET /api/sessions/{id}/audit` joins the typed session record, lifecycle events, schedule revisions and priced intervals for the on-demand dashboard audit; the UI deliberately omits durable vehicle/session identifiers. Session history/export, SoH and charge-curve behavior remain documented in `docs/grafana.md`.
- **`settings.py`** — runtime-adjustable settings persisted to a JSON file (`SETTINGS_PATH`), all keys in one object so each setter does a read-modify-write. Holds the charge target (`PUT /api/settings/target`), an optional "ready-by" departure time (`PUT /api/settings/ready-by`, an `HH:MM` string or null), and optional per-weekday target overrides (`PUT /api/settings/day-targets`, a full `{0(Mon)..6(Sun): percent}` map). The base target lives on `state.store` (`charge_target` property / `set_charge_target`): the runtime override if set, else `config.CHARGE_TARGET`. `store.effective_target` resolves what to use *right now* — today's per-weekday override (in `config.TIMEZONE`) if set, else the base — and is what `main.handle_plugin_event` and `api.build_snapshot` read (never `config.CHARGE_TARGET` directly). Ready-by lives on `store.ready_by` (+ `ready_by_tuple` parsed for Ohme); when set it's passed to `ohme_client.set_target` as `target_time` so the charge completes by then. When the user hasn't set an override, the dashboard field auto-populates from Ohme's own configured time: `build_snapshot` reads `client.target_time` into `snapshot.ohme_ready_by` (valid even when unplugged), and `/api/status` serves `config.readyBy = store.ready_by or ohme_ready_by` plus `readyByIsManual`. Any settings change goes through `api._reapply_target_if_connected` (no args — reads `effective_target`/`ready_by`) so an active session re-plans immediately. The same file also holds a non-user `sessionActive` marker (`load_session_active`/`save_session_active`) that `PlugInDetector` uses to avoid re-recording/re-notifying an already-handled session across a container restart. Persistence is best-effort — if the file can't be written the settings stay in memory only (and a restart could re-record one duplicate session, the pre-fix behaviour).

## Configuration

Copy `.env.example` to `.env`. Required vars: `HYUNDAI_USERNAME`, `HYUNDAI_PASSWORD`, `HYUNDAI_PIN`, `OHME_EMAIL`, `OHME_PASSWORD`. Optional: `CHARGE_TARGET` (default 80, the initial/fallback target), `POLL_INTERVAL` (default 180s), `UPSTREAM_TIMEOUT` (default 30s; max seconds to wait on a single Bluelink/Ohme call before treating it as a failed read — the per-poll Bluelink reads go through `bluelink.get_vehicle_state_async`/`list_vehicles_async` and the Ohme status read through `ohme_client.get_charger_status`, all bounded by `asyncio.wait_for` so a hung upstream can't stall the loop or hold the Bluelink SDK lock from the caller's view; on timeout the loop keeps last-known-good and retries), `MAX_POLL_BACKOFF` (default 30min; upper bound on the poll loop's back-off during a sustained upstream outage — `api._next_poll_delay(consecutive_failures)` returns `POLL_INTERVAL * 2**(n-1)` capped here, and `store.update` zeroes the failure counter on a good poll so the cadence snaps back to `POLL_INTERVAL` on the first success), `LIVE_SOC_INTERVAL` (default 30min; how often the poll loop re-reads the SOC from Bluelink *while charging* so the battery ring climbs through the session — reads Hyundai's cached state so it never wakes the car; 0 disables the climb. Independently, `_maybe_refresh_live_soc` *seeds* the SOC once whenever the car is connected but no real reading is held — e.g. after a container restart mid-session, where `prime()` won't re-run `handle_plugin_event` — so the ring shows the real SOC instead of Ohme's unreliable `battery` estimate), `SETTINGS_PATH` (default `/app/data/settings.json`; a named volume is mounted there in both compose files so a dashboard-changed target survives restarts), `NTFY_TOPIC`, `NTFY_URL`, `NTFY_TOKEN`, `CORS_ORIGINS`, `DATABASE_URL` (blank disables Postgres history persistence; both compose files bundle a `postgres` service and default this to it), `DAILY_STATS_INTERVAL` (default 6h; how often the poll loop refreshes Ohme's daily totals into Postgres — also the cadence for the Octopus household-consumption ingest). For the optional Agile tariff card: `OCTOPUS_PRODUCT_CODE`, `OCTOPUS_REGION` (public, no auth). For the optional household-vs-car energy card: `OCTOPUS_API_KEY` + `OCTOPUS_ACCOUNT_NUMBER` (needs an Octopus account; the import meter is auto-discovered) — also requires `DATABASE_URL`, since the car share is reconstructed from the telemetry history.

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
