# Copilot Instructions for `ionic5-ohme-autocharge`

## Build, test, and lint commands

### Backend (Python)
```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt

pytest
pytest tests/test_bluelink.py
pytest tests/test_bluelink.py::test_returns_battery_percentage

python main.py
python main.py --once
```

### Frontend (`frontend/`)
```bash
cd frontend
npm install

npm run lint
npm run test
npm run test -- src/components/TariffSection.test.tsx
npm run build
```

## High-level architecture

- The backend is a single-process FastAPI + polling system. `main.py` / `api.poll_loop` watch Ohme connection state and trigger a one-time per plug-in flow: fetch Hyundai SOC (Bluelink) and configure Ohme target charging.
- `state.store` is the in-process source of truth for live snapshot data, settings overlays, API cache, and poll-loop state. This is why deployment must stay single-worker.
- `bluelink.py` wraps a synchronous third-party SDK behind async helpers (`asyncio.to_thread`) and serializes SDK access with a module-level lock; `ohme_client.py` is async and handles charger reads/writes.
- `settings.py` persists runtime-overridable config (target, ready-by, day-targets, selected vehicle, session marker) to a JSON file; API setting changes reapply target immediately when connected.
- `db.py` is optional Postgres persistence: session history, telemetry, daily stats, SOH trend, exports, and energy-usage backing data. With no DB, functions degrade to no-ops and APIs return `enabled: false` where applicable.
- `octopus.py` adds two optional features: Agile pricing (public rates) and household import consumption (account API). `energy.py` is pure attribution/merge logic for house-vs-car half-hour slots.
- `ntfy.py` is optional notifications; blank topic disables sending without failing app flow.
- Frontend is a React + TypeScript SPA (`frontend/`) that polls `/api/*`, renders status/schedule/stats/cards, and is served in production by nginx.

## Key repository-specific conventions

- **Plug-in event handling is edge-triggered and session-aware**: use `PlugInDetector` (`prime` + `update`) and the persisted `sessionActive` marker to avoid duplicate per-session actions after restarts.
- **Never use `config.CHARGE_TARGET` directly for runtime decisions**: use `store.effective_target` so weekday overrides and runtime settings are honored.
- **Ohme target writes must send top-up amount (`target - current_soc`)**: do not send current SOC to Ohme as an “already added” value.
- **Hold `store.client_lock` only around Ohme client operations**: keep slow Bluelink fetches outside the lock so dashboard reapply/read paths are not blocked.
- **Treat optional integrations as graceful degradation paths** (`db`, `ntfy`, `octopus`): preserve no-op behavior instead of hard-failing when unconfigured/unavailable.
- **Testing style**: mock at module boundaries (no real Hyundai/Ohme calls), keep `tests/conftest.py` in sync with required env vars, and avoid hard-coded local-time formatted assertions (CI runs in UTC).
- **Graph-first exploration**: when investigating code, start with `graphify query/explain/path` against `graphify-out/graph.json` before broad raw-file reads.
- **Git workflow**: one branch per distinct feature/fix; do not reuse merged-PR branches.
