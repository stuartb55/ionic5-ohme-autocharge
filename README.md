# Hyundai → Ohme Auto-Charge

[![CI](https://github.com/stuartb55/ionic5-ohme-autocharge/actions/workflows/docker.yml/badge.svg)](https://github.com/stuartb55/ionic5-ohme-autocharge/actions/workflows/docker.yml)
[![Python](https://img.shields.io/badge/python-3.12+-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-ghcr.io-2496ED?logo=docker&logoColor=white)](https://github.com/stuartb55/ionic5-ohme-autocharge/pkgs/container/ionic5-ohme-autocharge)
[![Platforms](https://img.shields.io/badge/platform-linux%2Famd64%20%7C%20linux%2Farm64-lightgrey)](https://github.com/stuartb55/ionic5-ohme-autocharge/pkgs/container/ionic5-ohme-autocharge)

Automatically sets your **Ohme** home charger to charge your **Hyundai EV** to a target battery percentage (default 80%) — without manual intervention.

When the car is plugged in, the app reads the real battery state-of-charge from the Hyundai Bluelink API and configures the Ohme charger to add exactly the energy needed to reach your target. It ships with an installable **web dashboard** for live status, controls, charge schedule, and energy/savings statistics, and optional Postgres history for Grafana.

## Features

- **Hands-off charging** — detects plug-in, reads the real SOC, and tells Ohme how much to add to hit the target.
- **Live dashboard** — state-of-charge ring, driving range, battery health, charge rate, energy added, and an estimated session cost.
- **Charge controls** — adjust the target, pause/resume, toggle max-charge ("boost"), and force a live refresh.
- **Ready-by time** — finish charging by a chosen time (auto-populates from Ohme's own configured time).
- **Per-weekday targets** — e.g. 80% on weekdays, 100% before the weekend, applied automatically at plug-in.
- **One-time trip charge** — temporarily raise the target and optionally set a departure time for the current or next session; the override survives restarts and clears automatically on unplug.
- **Live SOC while charging** — the ring climbs through the session (re-reads Bluelink on a slow cadence; never wakes the car).
- **Single-vehicle focus** — one clear vehicle dashboard, without fleet selection or duplicate per-vehicle settings.
- **Vehicle health** — read-only 12V auxiliary battery level plus the car's own tyre-pressure, washer-fluid and key-fob-battery warnings and anything left open (door/bonnet/boot), shown on the dashboard with an optional ntfy when a warning first appears.
- **Configurable notifications** — optional [ntfy](https://ntfy.sh) alerts with dashboard controls for plug-in, completion, problems/recovery, vehicle health and weekly summaries; tune failure, minimum-energy and optional 12V-battery thresholds.
- **Octopus Agile** *(optional)* — upcoming half-hourly prices and the cheapest slots, plus an Agile-accurate session cost (each charge slot priced against the rate it falls in, not a flat average).
- **Reconciled actual cost** *(Octopus Agile + Postgres)* — persists tariff windows in the background and prices measured session-energy intervals after charging finishes; incomplete tariff or telemetry coverage is reported instead of guessed.
- **House vs car energy** *(optional, needs Postgres)* — splits Octopus import into car, household and explicitly unattributed energy; telemetry gaps and inconsistencies remain visible instead of being silently forced into a plausible split.
- **History & Grafana** *(optional)* — per-session and telemetry data persisted to Postgres.
- **Data-quality dashboard** *(needs Postgres)* — shows missing measured energy/cost, session-linkage problems, uncertain attribution, ingestion freshness and statistics-cache age, with a direct path to session records needing review.
- **Session audit view** *(needs Postgres)* — expands each history row into measured energy/cost, reconciliation quality, lifecycle events, schedule revisions, priced tariff intervals and the charge curve.
- **Monthly evidence reports** *(needs Postgres)* — download JSON or spreadsheet-friendly CSV for any local calendar month, keeping account totals and measured home-session figures separate with explicit coverage and missing-data counts.
- **Battery health trend** *(needs Postgres)* — a state-of-health sparkline on the dashboard showing degradation over time, not just the current figure.
- **Installable PWA** — add to your phone/desktop home screen; works offline (app shell cached).

## How it works

1. Polls the Ohme API every 3 minutes (configurable).
2. Detects when the car transitions from unplugged → plugged in.
3. Reads the current battery % (and range / odometer / state-of-health) from Hyundai Bluelink (EU).
4. Calculates how much charge is needed to reach the effective target — today's per-weekday override if set, else the base target — and tells Ohme to add that amount (carrying any ready-by time).
5. While charging, re-reads the SOC periodically so the dashboard stays live; records the session to Postgres if enabled.
6. Resets after unplug, ready for the next session.

## Prerequisites

- Python 3.12+ (Docker image uses 3.14)
- Hyundai Bluelink account (European region)
- Ohme account (the email/password used in the Ohme app)

## Security model

The API has no user authentication — it assumes the **trusted LAN or Tailscale tailnet** it runs on. Every
state-changing endpoint requires `X-Requested-With: autocharge-ui`, unknown request fields are
rejected, CORS is same-origin by default, and `TRUSTED_HOSTS` rejects arbitrary Host headers to
limit DNS-rebinding access.

For Tailscale, add the exact MagicDNS name used in the browser to `TRUSTED_HOSTS`, for example
`autocharge.your-tailnet.ts.net`. Keep the backend port private; expose the nginx frontend only.

## Setup

**1. Clone the repository**

```bash
git clone https://github.com/stuartb55/ionic5-ohme-autocharge.git
cd ionic5-ohme-autocharge
```

**2. Install dependencies**

```bash
pip install -r requirements.txt
```

**3. Configure credentials**

```bash
cp .env.example .env
```

Fill in at least the required credentials (see [Configuration](#configuration) for the full list):

```env
# Hyundai Bluelink credentials (European account)
HYUNDAI_USERNAME=your_email@example.com
HYUNDAI_PASSWORD=your_password
HYUNDAI_PIN=1234

# Ohme account credentials
OHME_EMAIL=your_email@example.com
OHME_PASSWORD=your_password
```

## Configuration

All settings come from environment variables (or `.env`). Only the five credentials are required; everything else has a sensible default. `.env.example` documents them all.

**Required**

| Variable | Description |
|---|---|
| `HYUNDAI_USERNAME` / `HYUNDAI_PASSWORD` / `HYUNDAI_PIN` | Hyundai Bluelink (EU) credentials |
| `OHME_EMAIL` / `OHME_PASSWORD` | Ohme account credentials |

**Optional**

| Variable | Default | Description |
|---|---|---|
| `CHARGE_TARGET` | `80` | Initial/fallback target %. The dashboard can change it at runtime (persisted). |
| `POLL_INTERVAL` | `180` | Seconds between Ohme polls. |
| `UPSTREAM_TIMEOUT` | `30` | Maximum seconds for each individual Ohme or Bluelink network operation. |
| `OHME_RECONNECT_FAILURES` | `3` | Consecutive session failures before replacing the authenticated Ohme client. |
| `LIVE_SOC_INTERVAL` | `1800` | Seconds between mid-charge SOC re-reads (so the ring climbs). `0` disables. |
| `MAX_SOC_AGE` | `1800` | Maximum age in seconds of a cached Bluelink SOC accepted for target-setting. `0` disables the freshness guard. |
| `HYUNDAI_VEHICLE_ID` | *(first)* | Pin the single tracked vehicle when the Hyundai account contains more than one (id from `GET /api/vehicles`). |
| `TIMEZONE` / `TZ` | `Europe/London` | Zone for log timestamps, daily-stats bucketing, and per-weekday targets. |
| `SETTINGS_PATH` | `/app/data/settings.json` | Where runtime settings (target, ready-by, per-day targets, selected vehicle) persist. A named volume is mounted here. |
| `NTFY_TOPIC` / `NTFY_URL` / `NTFY_TOKEN` | *(off)* | [ntfy](https://ntfy.sh) notifications. Blank `NTFY_TOPIC` disables them. |
| `WEEKLY_DIGEST_DAY` / `WEEKLY_DIGEST_HOUR` | `0` / `8` | Weekday (0=Mon … 6=Sun) and local hour for the weekly digest. Day outside 0–6 disables it. Needs ntfy. |
| `OCTOPUS_PRODUCT_CODE` / `OCTOPUS_REGION` | *(off)* | Octopus Agile product code + single-letter DNO region (A–P) to enable the tariff card. |
| `OCTOPUS_API_KEY` / `OCTOPUS_ACCOUNT_NUMBER` | *(off)* | Octopus account API key + account number (e.g. `A-AAAA1111`) to enable the house-vs-car energy card. The import meter is auto-discovered. Needs `DATABASE_URL` too. |
| `CONSUMPTION_BACKFILL_DAYS` | `90` | Initial Octopus consumption history to ingest. Later runs resume from a durable cursor with overlap for corrections. |
| `DATABASE_URL` | *(off)* | Postgres connection string for charging history. Blank runs entirely in memory. The compose files default this to the bundled Postgres. |
| `DATABASE_RECONNECT_INITIAL` / `DATABASE_RECONNECT_MAX` | `5` / `300` | Bounded background reconnect backoff when optional Postgres is unavailable. |
| `DAILY_STATS_INTERVAL` | `21600` | Seconds between background refreshes of Ohme's daily totals into Postgres (6h). |
| `TELEMETRY_RETENTION_DAYS` | `365` | How long to keep per-poll telemetry rows. `0` keeps forever. |
| `CORS_ORIGINS` | *(same-origin)* | Comma-separated allowed origins; blank means same-origin only (the default deployment). |
| `TRUSTED_HOSTS` | localhost + Docker names | Allowed HTTP Host headers. Add the exact LAN or Tailscale MagicDNS names used to open the UI. |
| `POSTGRES_PASSWORD` | `autocharge` | Password for the bundled compose Postgres service. |

## Usage

### Docker (recommended)

```bash
docker compose up -d      # start in the background (auto-restarts on crash/reboot)
docker compose logs -f    # live logs
docker compose down       # stop
```

`docker compose up -d` starts **three** services:

| Service    | Description                                                    | Port |
|------------|----------------------------------------------------------------|------|
| `backend`  | FastAPI app — runs the polling loop **and** serves `/api`       | 8000 |
| `frontend` | nginx serving the dashboard SPA, proxying `/api` to the backend | 8080 |
| `postgres` | Charging-history database (for the sessions card + Grafana)     | 5432 (loopback) |

Open the dashboard at **http://localhost:8080**. `restart: unless-stopped` brings everything back after a reboot. Postgres is optional in spirit — set `DATABASE_URL` blank to run history-free — but the compose files bundle it and wire it up by default.

### Python directly

```bash
python main.py             # run continuously (auto-detects plug-in events)
python main.py --once      # fetch SOC and set the target once, then exit
uvicorn api:app --host 0.0.0.0 --port 8000   # web API + poll loop (docs at /docs)
```

## Web dashboard

A React + TypeScript single-page app (in `frontend/`) served by a hardened, non-root nginx image. It polls the backend and renders:

1. **At-a-glance live status** — one state-of-charge view with the active target, expected finish, range, charge speed, energy added, planned energy and estimated cost. Pause/resume and boost controls stay beside the live session.
2. **Tonight’s plan & preferences** — a home-timezone schedule with start, ready-by time and charging windows, followed by the everyday target and departure time. Weekly targets, trip charge and notifications remain available under one disclosure.
3. **Costs & energy** — account-wide Ohme cost, savings, energy and average unit price for the last 7/30/90 **complete local calendar days**, plus vehicle-scoped home-energy efficiency and actual home running cost from complete charge-to-next-plug-in intervals. Missing upstream daily buckets stay missing rather than being displayed as zero usage. Daily charts include period-over-period deltas and CSV export; a month picker downloads auditable monthly JSON/CSV reports. DST days follow `TIMEZONE` rather than assuming every day is 24 hours.
4. **Recent sessions** *(when Postgres is enabled)* — the last plug-ins with SOC, target, top-up and odometer, with a CSV/JSON export of the full history.
   Each row expands into a **session audit**: measured energy/cost and reconciliation, lifecycle events, schedule revisions, tariff-priced intervals, and the SOC/power charge curve. Missing evidence stays explicitly unavailable rather than being estimated.
5. **Agile prices** *(when Octopus is configured)* — the current price and cheapest upcoming slots.
6. **House vs car** *(when Octopus consumption + Postgres are configured)* — a stacked half-hourly chart of whole-house import split into car charging vs the rest of the household, with a day selector.

The header has an explicit live/stale indicator, a full-dashboard **refresh**, a **theme** toggle, and the build version in the footer. Diagnostics and evidence remain available without competing with everyday metrics.

> All figures come straight from the Ohme/Bluelink APIs. Metrics those APIs don't expose are intentionally omitted rather than faked.

### Frontend development

```bash
cd frontend
nvm use           # Node 24, matching CI (see .nvmrc)
npm install
npm run dev      # Vite dev server on :5173, proxies /api to http://localhost:8000
npm run test     # Vitest component + MSW integration tests
npm run lint
npm run build    # type-check + production build to dist/
```

### API endpoints

| Endpoint | Description |
|---|---|
| `GET /api/health` | Liveness probe (503 if the poll loop has died) |
| `GET /api/ready` | Operational readiness (Ohme/poll status plus optional persistence availability) |
| `GET /api/data-quality` | Read-only persistence completeness counters, ingestion freshness, and statistics-cache age for monitoring |
| `GET /api/reports/monthly?month=YYYY-MM&format=json\|csv` | Calendar-month persisted account/day and measured home-session evidence; defaults to the previous month (404 when persistence is off) |
| `GET /api/version` | Build git SHA (`dev` when unset) |
| `GET /api/status` | Vehicle/charger data plus independent plug-in automation state (`idle`, `pending`, `configured`, or `error`) |
| `GET /api/schedule` | Allocated charge slots + next slot times |
| `GET /api/statistics?days=N` | Typed complete-calendar-day totals plus provenance and coverage; serves the last validated snapshot with explicit `stale` quality during a temporary Ohme outage (N = 1–90) |
| `GET /api/sessions?limit=N` | Recent plug-in sessions from Postgres (N = 1–50; `enabled: false` when persistence is off) |
| `GET /api/sessions/export?format=csv\|json` | Download the **full** plug-in history as a CSV or JSON attachment (404 when persistence is off) |
| `GET /api/sessions/{id}/telemetry` | Per-poll charge curve (SOC + power over time) for one session (404 when the id is unknown; `enabled: false` when persistence is off) |
| `GET /api/sessions/{id}/audit` | Typed session provenance: identity record, lifecycle events, schedule revisions and priced charging intervals (404 when persistence is off or the id is unknown) |
| `GET /api/soh-history?limit=N` | Battery state-of-health readings over time, one point per change (N = 1–365; `enabled: false` when persistence is off) |
| `GET /api/tariff` | Upcoming Octopus Agile rates + cheapest slots (`enabled: false` when unconfigured) |
| `GET /api/energy-usage?date=YYYY-MM-DD` | A day's half-hourly whole-house import split into car vs rest-of-house + totals (default yesterday; `enabled: false` when unconfigured) |
| `GET /api/vehicles` | Vehicles on the Hyundai account, with the selected one flagged |
| `POST /api/refresh` | Force a live re-read from Ohme (rate-limited) |
| `POST /api/charge/pause` · `POST /api/charge/resume` | Pause / resume the active charge session |
| `PUT /api/charge/max-charge` | Toggle max-charge ("boost") — `{"enabled": true\|false}` |
| `PUT /api/settings/target` | Set the charge target — `{"targetPercent": N}` |
| `PUT /api/settings/ready-by` | Set/clear the ready-by time — `{"readyBy": "HH:MM"\|null}` |
| `PUT /api/settings/day-targets` | Replace per-weekday overrides — `{"dayTargets": {"4": 100}}` |
| `PUT /api/settings/trip-mode` | Enable/update or cancel the durable one-session override — `{"enabled": true, "targetPercent": 100, "readyBy": "06:30"}` |
| `PUT /api/settings/notifications` | Replace ntfy category choices and validated alert thresholds; persisted in runtime settings |
| `PUT /api/settings/vehicle` | Select the tracked vehicle — `{"vehicleId": "…"\|null}` |
| `PUT /api/settings/vehicle-profile` | Create/update or remove target and ready-by defaults for a stable Hyundai vehicle ID |

## Notifications (ntfy)

The app can send push notifications via [ntfy](https://ntfy.sh) — plug-in / charge-target-set, charge finished, problem/recovery, vehicle-health, and weekly-summary alerts. Set `NTFY_TOPIC` to enable delivery; blank disables it silently. The dashboard’s **Notifications** settings can independently enable each category and configure the number of failed polls before a problem alert, the minimum delivered kWh for a completion alert, and an optional user-chosen 12V battery threshold. Preferences persist across restarts even when delivery is not configured yet.

```env
NTFY_TOPIC=your-topic-name
NTFY_URL=https://your-ntfy-instance.com   # defaults to https://ntfy.sh
NTFY_TOKEN=your-access-token              # for self-hosted instances with auth
```

A typical message:

> Hyundai IONIQ 5 plugged in at 62% → 80% (ready by 07:30). Charge schedule: 01:00-03:30

**Weekly digest** — when ntfy is on, a once-a-week summary of the last 7 days (energy, cost, savings, CO₂) is sent on `WEEKLY_DIGEST_DAY` at `WEEKLY_DIGEST_HOUR` (default Monday 08:00).

## Octopus Agile tariff (optional)

Set both `OCTOPUS_PRODUCT_CODE` (e.g. `AGILE-24-10-01`) and `OCTOPUS_REGION` (your single-letter DNO region, A–P) to show an **Agile prices** card with the current price and cheapest upcoming half-hourly slots. It uses Octopus's public unit-rate API — no account or key needed. Leave either blank to hide the card.

## House vs car energy (optional)

Set `OCTOPUS_API_KEY` (your account API key, from [octopus.energy/dashboard/developer](https://octopus.energy/dashboard/developer/)) and `OCTOPUS_ACCOUNT_NUMBER` (e.g. `A-AAAA1111`) to show a **House vs car** card: your whole-house grid import for a day, broken half-hour by half-hour into the car-charging share and the rest of the household. The car portion is reconstructed from charge telemetry, so this also needs `DATABASE_URL`. Every import serial on the current property is rediscovered daily, allowing history to span a meter exchange. The first successful run backfills `CONSUMPTION_BACKFILL_DAYS`; an `ingestion_cursors` row then makes later runs resumable while overlapping recent days for late corrections. Because Octopus publishes consumption in arrears, the card defaults to **yesterday**. Leave either credential blank to hide the card.

## Charging history & Grafana (optional)

The Postgres schema is versioned with Alembic and upgraded automatically before
the backend opens its connection pool. Existing installations are adopted
idempotently. Physical plug-ins have durable session keys, lifecycle timestamps,
vehicle/charger identity, quality state, schedule revisions and an event audit
trail so retries cannot create duplicate sessions.

GitHub CI upgrades a legacy revision against PostgreSQL 18, verifies exact-unit
backfill and the current Alembic head, then exercises session idempotency, linked
telemetry, completion, reconciliation, report queries, and reconnect behaviour.

Set `DATABASE_URL` (the compose files default it to the bundled Postgres) to persist per-plug-in sessions, schedule snapshots, per-poll telemetry, and daily totals. A startup outage leaves charging operational and triggers bounded background reconnect attempts; session rows are staged in the settings volume and replayed idempotently, so a plug-in during the outage is not lost. Daily energy is stored exactly in Wh and money in integer minor units; legacy floating columns remain for compatibility. This powers the dashboard's recent-sessions card and lets you build Grafana panels (energy/cost/savings over time, driving efficiency, battery-health trend). See [`docs/grafana.md`](docs/grafana.md) for the schema and example queries. With `DATABASE_URL` blank, the app runs entirely in memory — every history feature simply switches off.

## Progressive web app

The dashboard is installable (web app manifest + icons) and registers a service worker that caches the app shell for offline use. On a phone, "Add to Home Screen"; on desktop Chrome/Edge, use the install icon in the address bar.

## Deploying to a home server

Every push to `main` triggers a GitHub Actions workflow that builds multi-platform images (`linux/amd64` + `linux/arm64`) and pushes them to the GitHub Container Registry. A home server pulls the pre-built images — no code or build tools needed on the server.

**One-time setup on the server:**

```bash
mkdir ~/autocharge && cd ~/autocharge

# Copy your .env across (fill in credentials as per .env.example)
scp yourpc:path/to/.env .

# Download the production compose file
curl -O https://raw.githubusercontent.com/stuartb55/ionic5-ohme-autocharge/main/docker-compose.prod.yml

docker compose -f docker-compose.prod.yml up -d
```

> **Note:** After the first push to `main`, set both GHCR packages (`ionic5-ohme-autocharge` and `ionic5-ohme-autocharge-ui`) to **Public** so the server can pull without logging in. In `docker-compose.prod.yml` the dashboard is published on **port 8084**.

**Update after a code change:**

```bash
docker compose -f docker-compose.prod.yml pull && docker compose -f docker-compose.prod.yml up -d
```

## Project structure

```
├── main.py                        # Async poll loop, plug-in handler, PlugInDetector (CLI + shared)
├── api.py                         # FastAPI app: runs the poll loop + serves /api
├── api_contracts.py               # Typed dashboard response contracts exposed through OpenAPI
├── state.py                       # In-memory snapshot + runtime settings shared by loop and API
├── settings.py                    # Persisted runtime settings (charging, alerts, vehicle, session marker)
├── bluelink.py                    # Hyundai Bluelink wrapper (SOC, range, odometer, SoH, lock/location)
├── ohme_client.py                 # Ohme charger wrapper (ohme)
├── ntfy.py                        # Ntfy notification client + weekly digest
├── octopus.py                     # Optional Octopus tariff (Agile) + household consumption client
├── energy.py                      # Pure helpers: per-half-hour car share + house-vs-car merge
├── db.py                          # Optional Postgres history (sessions, telemetry, daily stats, grid consumption)
├── config.py                      # Loads settings from .env
├── Dockerfile                     # Backend image (uvicorn)
├── docker-compose.yml             # Local dev: backend + frontend + postgres
├── docker-compose.prod.yml        # Home server: pulls pre-built images from GHCR
├── docs/grafana.md                # Postgres schema + example Grafana queries
├── .github/workflows/docker.yml   # Tests + multi-platform image builds on push to main
├── tests/                         # pytest suite (backend + API)
└── frontend/                      # React + TypeScript dashboard SPA (+ service worker, manifest, icons)
    ├── src/{api,components,utils,hooks,test}
    ├── public/                    # manifest.webmanifest, icons, sw.js
    ├── Dockerfile                 # Multi-stage build → non-root nginx
    └── nginx.conf                 # Security headers, /api proxy, SPA fallback
```

## Dependencies

| Package | Purpose |
|---|---|
| [hyundai-kia-connect-api](https://github.com/Hyundai-Kia-Connect/hyundai_kia_connect_api) | Reads battery SOC (and range, odometer, SoH, lock/location) from Hyundai Bluelink (EU) |
| [ohme](https://github.com/dan-r/ohmepy) | Controls the Ohme home charger |
| [FastAPI](https://fastapi.tiangolo.com/) + [uvicorn](https://www.uvicorn.org/) | Web API and ASGI server |
| [psycopg](https://www.psycopg.org/) | Postgres access for optional charging history |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | Loads credentials from `.env` |

## Notes

- The Hyundai API returns **cached** vehicle state, so a freshly-read SOC can be slightly stale; for normal daily use (drive home → plug in) this is fine. Mid-charge refreshes also read cached state, so they never wake or drain the car.
- If the SOC is already at or above the target when you plug in, the app logs this and takes no action.
- The backend must run as exactly **one** uvicorn worker — all state is in-process (the snapshot, poll loop, single Ohme client). The Dockerfile does this; don't add `--workers`.
- Ohme credentials are your Ohme app email/password (authenticated via Google Identity Toolkit).
