"""HTTP API for the autocharge dashboard.

This is the production entrypoint for the *backend* container. It:

1. Authenticates a single Ohme client and runs the same plug-in detection loop
   as ``main.py`` (reusing :func:`main.handle_plugin_event`).
2. Refreshes an in-memory :class:`state.StatusSnapshot` on every poll.
3. Serves read-only JSON the SPA consumes.

The browser only ever reads the cached snapshot, so the UI is fast and we never
hammer the upstream APIs on a per-request basis. The charge-summary endpoint is
the one live call; it is cached briefly and serialised behind ``client_lock``.

Run:  uvicorn api:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

import config
import main
import ohme_client
from state import StatusSnapshot, store

logger = logging.getLogger(__name__)

# Comma-separated list of allowed CORS origins. Empty (default) means same-origin
# only — which is the production setup, where nginx serves the SPA and proxies /api.
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
# Set to "1" in tests to construct the app without starting the background loop.
DISABLE_POLLING = os.getenv("AUTOCHARGE_DISABLE_POLLING") == "1"

# Charge summary is cached this many seconds to avoid repeated upstream calls.
SUMMARY_CACHE_TTL = 300


def _iso(dt: Optional[datetime.datetime]) -> Optional[str]:
    return dt.isoformat() if dt is not None else None


def build_snapshot(client: Any, *, connected: bool, error: Optional[str] = None) -> StatusSnapshot:
    """Translate the live Ohme client state into a serialisable snapshot.

    Assumes ``async_get_charge_session`` (and, once at startup,
    ``async_update_device_info``) have already populated the client.
    """
    now = datetime.datetime.now().astimezone().isoformat()
    if error is not None:
        return StatusSnapshot(updated_at=now, error=error)

    power = client.power
    try:
        status_value = client.status.value
    except Exception:  # pragma: no cover - defensive: malformed session
        status_value = "unknown"

    return StatusSnapshot(
        vehicle_name=client.current_vehicle,
        # Prefer the real Bluelink SOC captured at plug-in; Ohme's own `battery`
        # estimate is unreliable. Fall back to it only until the first plug-in.
        battery_percent=(store.last_soc if store.last_soc is not None else (client.battery or None)),
        charger_status=status_value,
        connected=connected,
        charger_online=bool(client.available),
        charger_model=(client.device_info or {}).get("model"),
        power_watts=float(power.watts or 0),
        power_amps=float(power.amps or 0),
        power_volts=power.volts,
        # The configured target. NB: client.target_soc holds the *top-up* amount
        # (target − SOC) we send to Ohme, not the absolute target, so never use it.
        target_percent=config.CHARGE_TARGET,
        session_energy_wh=float(client.energy or 0),
        slots=[s.to_dict() for s in client.slots],
        next_slot_start=_iso(client.next_slot_start),
        next_slot_end=_iso(client.next_slot_end),
        updated_at=now,
    )


async def poll_loop() -> None:
    """Background task: detect plug-in events and refresh the status snapshot."""
    logger.info(
        "API poll loop starting (interval=%ss, target=%s%%)",
        config.POLL_INTERVAL,
        config.CHARGE_TARGET,
    )
    client = await ohme_client.make_client()
    store.client = client

    # Populate vehicle name / model / serial once up front.
    try:
        await client.async_update_device_info()
    except Exception:
        logger.warning("Could not fetch device info on startup", exc_info=True)

    was_connected = False
    session_handled = False
    try:
        initial_mode = await ohme_client.get_session_mode(client)
        was_connected = ohme_client.is_connected(initial_mode)
        if was_connected:
            logger.info("Car already connected on startup — will reconfigure on next poll")
    except Exception:
        logger.warning("Could not determine initial charge state", exc_info=True)

    try:
        while True:
            try:
                async with store.client_lock:
                    mode = await ohme_client.get_session_mode(client)
                now_connected = ohme_client.is_connected(mode)

                if now_connected and not was_connected:
                    session_handled = False
                if now_connected and not session_handled:
                    # Deliberately NOT under client_lock: handle_plugin_event makes a
                    # slow Bluelink SOC fetch (in a thread) that doesn't use the Ohme
                    # client, so holding the lock here would stall /api/statistics for
                    # the whole plug-in event. Its Ohme writes (set_target) touch state
                    # disjoint from the charge-summary call, so this is safe to run
                    # unlocked, and the loop awaits it before the next snapshot build.
                    session_handled = await main.handle_plugin_event(client)
                if not now_connected and was_connected:
                    logger.info("Car unplugged (mode=%s)", mode)
                    session_handled = False
                was_connected = now_connected

                async with store.client_lock:
                    store.update(build_snapshot(client, connected=now_connected))
            except Exception:
                logger.exception("Error during poll — will retry next interval")
                store.update(build_snapshot(client, connected=False, error="poll_failed"))

            await asyncio.sleep(config.POLL_INTERVAL)
    finally:
        await client.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    task: Optional[asyncio.Task] = None
    if not DISABLE_POLLING:
        task = asyncio.create_task(poll_loop())
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add a baseline set of security headers to every response."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Cache-Control", "no-store, no-cache, must-revalidate"
        )
        return response


app = FastAPI(
    title="Ohme Autocharge API",
    version="1.0.0",
    summary="Read-only status, schedule and statistics for the EV charging scheduler.",
    lifespan=lifespan,
)
app.add_middleware(SecurityHeadersMiddleware)
if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_methods=["GET"],
        allow_headers=["*"],
    )


# --- summary parsing + cache ---------------------------------------------------

_summary_cache: dict[str, Any] = {"key": None, "value": None, "at": 0.0}


def _money(node: Any) -> tuple[float, Optional[str]]:
    """Return (amount, currencyCode) from an Ohme Money dict."""
    if not isinstance(node, dict):
        return 0.0, None
    try:
        amount = float(node.get("amount") or 0)
    except (TypeError, ValueError):
        amount = 0.0
    return amount, node.get("currencyCode")


def parse_summary(summary: dict[str, Any], days: int) -> dict[str, Any]:
    """Shape an Ohme ChargeSummary into the JSON the dashboard expects."""
    total = summary.get("totalStats") or {}
    cost = total.get("costStats") or {}
    carbon = total.get("carbonStats") or {}

    saved, currency = _money(cost.get("moneySavedVsStandardTariff"))
    cost_total, currency2 = _money(cost.get("moneyCostTotal"))
    avg_price, currency3 = _money(cost.get("averageKwhPrice"))
    currency = currency or currency2 or currency3

    daily = []
    for stat in summary.get("stats") or []:
        day_saved, _ = _money((stat.get("costStats") or {}).get("moneySavedVsStandardTariff"))
        day_cost, _ = _money((stat.get("costStats") or {}).get("moneyCostTotal"))
        start_ms = stat.get("startTime")
        date = None
        if start_ms:
            date = datetime.datetime.fromtimestamp(start_ms / 1000).date().isoformat()
        daily.append(
            {
                "date": date,
                "energyKwh": round((stat.get("energyChargedTotalWh") or 0) / 1000, 2),
                "savings": round(day_saved, 2),
                "cost": round(day_cost, 2),
            }
        )

    return {
        "rangeDays": days,
        "currency": currency,
        "totals": {
            "energyKwh": round((total.get("energyChargedTotalWh") or 0) / 1000, 2),
            "savingsVsStandard": round(saved, 2),
            "costTotal": round(cost_total, 2),
            "averageKwhPrice": round(avg_price, 4),
            "carbonSavedKgVsGasCar": round(
                (carbon.get("carbonSavedVsGasCarGrams") or 0) / 1000, 2
            ),
        },
        "daily": daily,
    }


# --- endpoints -----------------------------------------------------------------


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "ready": store.ready}


@app.get("/api/status")
async def get_status() -> JSONResponse:
    payload = {
        "vehicle": {
            "name": store.status.vehicle_name,
            "batteryPercent": store.status.battery_percent,
        },
        "charger": {
            "status": store.status.charger_status,
            "connected": store.status.connected,
            "online": store.status.charger_online,
            "model": store.status.charger_model,
            "power": {
                "watts": store.status.power_watts,
                "amps": store.status.power_amps,
                "volts": store.status.power_volts,
            },
            "targetPercent": store.status.target_percent,
            "sessionEnergyKwh": round(store.status.session_energy_wh / 1000, 2),
        },
        "config": {
            "chargeTarget": config.CHARGE_TARGET,
            "pollIntervalSeconds": config.POLL_INTERVAL,
        },
        "updatedAt": store.status.updated_at,
        "ready": store.ready,
    }
    return JSONResponse(payload)


@app.get("/api/schedule")
async def get_schedule() -> JSONResponse:
    return JSONResponse(
        {
            "slots": store.status.slots,
            "nextSlotStart": store.status.next_slot_start,
            "nextSlotEnd": store.status.next_slot_end,
            "connected": store.status.connected,
            "updatedAt": store.status.updated_at,
        }
    )


@app.get("/api/statistics")
async def get_statistics(days: int = Query(default=7, ge=1, le=90)) -> JSONResponse:
    import time

    client = store.client
    if client is None:
        raise HTTPException(status_code=503, detail="Backend not connected to Ohme yet")

    cache_key = f"days={days}"
    now = time.time()
    if (
        _summary_cache["key"] == cache_key
        and _summary_cache["value"] is not None
        and now - _summary_cache["at"] < SUMMARY_CACHE_TTL
    ):
        return JSONResponse(_summary_cache["value"])

    end_ts = int(now * 1000)
    start_ts = end_ts - days * 24 * 60 * 60 * 1000
    try:
        async with store.client_lock:
            summary = await client.async_get_charge_summary(start_ts=start_ts, end_ts=end_ts)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to fetch charge summary", exc_info=True)
        raise HTTPException(status_code=502, detail="Could not fetch statistics from Ohme") from exc

    # async_get_charge_summary returns granularity as an enum; drop it before serialising.
    parsed = parse_summary({k: v for k, v in summary.items() if k != "granularity"}, days)
    _summary_cache.update(key=cache_key, value=parsed, at=now)
    return JSONResponse(parsed)
