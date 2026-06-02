# Hyundai → Ohme Auto-Charge

[![CI](https://github.com/stuartb55/ionic5-ohme-autocharge/actions/workflows/docker.yml/badge.svg)](https://github.com/stuartb55/ionic5-ohme-autocharge/actions/workflows/docker.yml)
[![Python](https://img.shields.io/badge/python-3.12+-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-ghcr.io-2496ED?logo=docker&logoColor=white)](https://github.com/stuartb55/ionic5-ohme-autocharge/pkgs/container/ionic5-ohme-autocharge)
[![Platforms](https://img.shields.io/badge/platform-linux%2Famd64%20%7C%20linux%2Farm64-lightgrey)](https://github.com/stuartb55/ionic5-ohme-autocharge/pkgs/container/ionic5-ohme-autocharge)

Automatically sets your **Ohme Pro** home charger to charge your **Hyundai EV** to a target battery percentage (default 80%) — without manual intervention.

When the car is plugged in, the app fetches the current battery state-of-charge from the Hyundai Bluelink API and configures the Ohme charger to stop at your target level.

It also ships with a **web dashboard** (a single-page app served by nginx) showing live vehicle/charger status, the allocated charge schedule, and historical energy & savings statistics.

## How it works

1. Polls the Ohme API every 3 minutes (configurable)
2. Detects when the car transitions from unplugged → plugged in
3. Fetches the current battery % from Hyundai Bluelink (EU)
4. Calculates how much charge is needed to reach the target (default 80%) and tells Ohme to add that amount
5. Resets after unplug, ready for the next session

## Prerequisites

- Python 3.10+
- Hyundai Bluelink account (European region)
- Ohme account (the email/password used in the Ohme app)

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

Copy `.env.example` to `.env` and fill in your details:

```bash
cp .env.example .env
```

```env
# Hyundai Bluelink credentials (European account)
HYUNDAI_USERNAME=your_email@example.com
HYUNDAI_PASSWORD=your_password
HYUNDAI_PIN=1234

# Ohme account credentials
OHME_EMAIL=your_email@example.com
OHME_PASSWORD=your_password

# Charge target percentage (default: 80)
CHARGE_TARGET=80

# How often to poll Ohme for plug-in events, in seconds (default: 180)
POLL_INTERVAL=180

# Ntfy notifications (optional) — leave NTFY_TOPIC blank to disable
NTFY_TOPIC=
NTFY_URL=https://ntfy.sh
NTFY_TOKEN=
```

## Usage

### Docker (recommended)

```bash
# Start in the background — auto-restarts on crash or reboot
docker compose up -d

# View live logs
docker compose logs -f

# Stop
docker compose down
```

`docker compose up -d` starts **two** services:

| Service    | Description                                              | Port |
|------------|----------------------------------------------------------|------|
| `backend`  | FastAPI app — runs the polling loop **and** serves `/api` | 8000 |
| `frontend` | nginx serving the dashboard SPA, proxying `/api` to the backend | 8080 |

Open the dashboard at **http://localhost:8080**. Docker's `restart: unless-stopped` policy means both services come back automatically after a reboot or crash — no startup scripts needed.

### Python directly

**Run continuously** (detects plug-in events automatically):

```bash
python main.py
```

**Run once** (fetches SOC and sets target immediately, then exits):

```bash
python main.py --once
```

**Run the web API** (also runs the polling loop; interactive docs at `/docs`):

```bash
uvicorn api:app --host 0.0.0.0 --port 8000
```

## Web dashboard

The dashboard is a React + TypeScript single-page app (in `frontend/`) served by a
hardened, non-root nginx image. It polls the backend and renders three sections:

1. **Vehicle & charger status** — a state-of-charge ring (with target marker),
   connection state, live charge rate (kW / A), and energy added this session.
2. **Schedule** — a timeline of the allocated charging slots, showing when charging
   is active vs paused (off-peak tariff windows), plus a slot-by-slot breakdown.
3. **Statistics & savings** — total energy charged, money saved vs the standard
   tariff, average price per kWh, CO₂ saved, and a daily energy/savings chart over a
   selectable 7/30/90-day window.

> All figures come straight from the Ohme/Bluelink APIs. Metrics those APIs don't
> expose (e.g. a "scheduling success rate") are intentionally omitted rather than
> faked.

### Frontend development

```bash
cd frontend
npm install
npm run dev      # Vite dev server on :5173, proxies /api to http://localhost:8000
npm run test     # Vitest component + MSW integration tests
npm run lint
npm run build    # type-check + production build to dist/
```

### API endpoints

| Endpoint | Description |
|---|---|
| `GET /api/health` | Liveness probe |
| `GET /api/status` | Vehicle SOC, connection state, charge rate, target, session energy |
| `GET /api/schedule` | Allocated charge slots + next slot times |
| `GET /api/statistics?days=N` | Energy, savings, cost, CO₂ and a daily series (N = 1–90) |

## Ntfy notifications

The app can send a push notification via [ntfy](https://ntfy.sh) each time the Ohme charge target is updated. Set `NTFY_TOPIC` in your `.env` to enable it — if left blank, notifications are silently disabled.

```env
NTFY_TOPIC=your-topic-name
NTFY_URL=https://your-ntfy-instance.com   # defaults to https://ntfy.sh
NTFY_TOKEN=your-access-token              # required for self-hosted instances with auth
```

When running, the startup log will confirm whether notifications are enabled:

```
Ntfy notifications enabled (url=https://your-ntfy-instance.com, topic=your-topic-name)
```

On a successful charge target update you will receive a notification such as:

> Hyundai IONIQ 5 (2021-) plugged in at 62% — Ohme target set to 80%

The vehicle name is read automatically from your Ohme account.

## Deploying to a home server

Every push to `main` triggers a GitHub Actions workflow that builds a multi-platform image (`linux/amd64` + `linux/arm64`) and pushes it to the GitHub Container Registry. A home server can pull this pre-built image — no code or build tools required on the server itself.

**One-time setup on the server:**

```bash
# Create a folder for the config
mkdir ~/autocharge && cd ~/autocharge

# Copy your .env across (fill in credentials as per .env.example)
scp yourwindowspc:path/to/hyundai/.env .

# Download the production compose file
curl -O https://raw.githubusercontent.com/stuartb55/ionic5-ohme-autocharge/main/docker-compose.prod.yml

# Start
docker compose -f docker-compose.prod.yml up -d
```

> **Note:** After the first push to `main`, go to `https://github.com/stuartb55?tab=packages`, find the `ionic5-ohme-autocharge` **and** `ionic5-ohme-autocharge-ui` packages, and set their visibility to **Public** — this allows the Mac Mini to pull the images without logging in to GHCR. The dashboard is then available on **port 8080** of the server.

**Updating after a code change:**

```bash
docker compose -f docker-compose.prod.yml pull && docker compose -f docker-compose.prod.yml up -d
```

**Useful commands:**

```bash
# View live logs
docker compose -f docker-compose.prod.yml logs -f

# Stop
docker compose -f docker-compose.prod.yml down
```

## Project structure

```
├── main.py                        # Async polling loop and plug-in event handler (CLI)
├── api.py                         # FastAPI app: runs the poll loop + serves /api
├── state.py                       # In-memory snapshot shared by loop and API
├── bluelink.py                    # Hyundai Bluelink wrapper (hyundai-kia-connect-api)
├── ohme_client.py                 # Ohme charger wrapper (ohme)
├── ntfy.py                        # Ntfy push notification client
├── config.py                      # Loads settings from .env
├── Dockerfile                     # Backend image (uvicorn)
├── docker-compose.yml             # Local dev: builds backend + frontend
├── docker-compose.prod.yml        # Home server: pulls pre-built images from GHCR
├── .github/workflows/docker.yml   # Tests + multi-platform image builds on push to main
├── requirements.txt
├── .env.example                   # Credential template
├── tests/                         # pytest suite (backend + API)
└── frontend/                      # React + TypeScript dashboard SPA
    ├── src/
    │   ├── api/                    # Typed API client + polling hook
    │   ├── components/             # Dashboard sections + SVG charts
    │   ├── utils/                  # Formatting + schedule timeline maths
    │   └── test/                   # MSW mocks + integration test
    ├── Dockerfile                  # Multi-stage build → non-root nginx
    ├── nginx.conf                  # Security headers, /api proxy, SPA fallback
    └── package.json
```

## Dependencies

| Package | Purpose |
|---|---|
| [hyundai-kia-connect-api](https://github.com/Hyundai-Kia-Connect/hyundai_kia_connect_api) | Reads battery SOC from Hyundai Bluelink (EU) |
| [ohme](https://github.com/dan-r/ohmepy) | Controls the Ohme home charger |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | Loads credentials from `.env` |

## Notes

- The Hyundai API returns **cached** vehicle state. If your car has been parked without a connection for a long time, the SOC reading may be slightly stale. For normal daily use (drive home → plug in) this is not an issue.
- If the SOC is already at or above the target when you plug in, the app logs this and takes no action — Ohme will continue with whatever schedule you have set.
- Ohme credentials are your Ohme app email/password (authenticated via Google Identity Toolkit).
