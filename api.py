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
import time
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

import config
import db
import main
import ohme_client
import settings
from state import StatusSnapshot, store

logger = logging.getLogger(__name__)

# Read-only endpoints that are polled constantly (the container HEALTHCHECK hits
# /api/health every 30s; the SPA refreshes the others on a timer). A successful
# GET to any of these is pure noise in the container log and buries the plug-in
# events we actually care about, so we drop those access-log lines. Anything that
# errors (status >= 400) is still logged.
_QUIET_ACCESS_PATHS = frozenset(
    {"/api/health", "/api/status", "/api/schedule", "/api/statistics"}
)


class _QuietAccessLogFilter(logging.Filter):
    """Suppress uvicorn access-log lines for successful GETs to polling endpoints.

    uvicorn logs each request as ``'%s - "%s %s HTTP/%s" %d'`` with
    ``record.args == (client_addr, method, full_path, http_version, status)``.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if not isinstance(args, tuple) or len(args) < 5:
            return True
        method, full_path, status = args[1], args[2], args[4]
        if method != "GET":
            return True
        try:
            if int(status) >= 400:
                return True
        except (TypeError, ValueError):
            return True
        path = str(full_path).split("?", 1)[0]
        return path not in _QUIET_ACCESS_PATHS


_quiet_access_filter = _QuietAccessLogFilter()

# Comma-separated list of allowed CORS origins. Empty (default) means same-origin
# only — which is the production setup, where nginx serves the SPA and proxies /api.
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
# Set to "1" in tests to construct the app without starting the background loop.
DISABLE_POLLING = os.getenv("AUTOCHARGE_DISABLE_POLLING") == "1"

# Charge summary is cached this many seconds to avoid repeated upstream calls.
SUMMARY_CACHE_TTL = 300

# Backoff schedule for the initial Ohme login. Login happens once per process
# start; failures there (the home server booting before its network is up, an
# Ohme outage) must never kill the poll loop permanently.
LOGIN_RETRY_INITIAL = 5.0
LOGIN_RETRY_MAX = 300.0

# The running poll task, so /api/health can report whether it is still alive.
_poll_task: Optional[asyncio.Task] = None


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
        # The active target (runtime override or env default). NB: client.target_soc
        # holds the *top-up* amount (target − SOC) we send to Ohme, not the absolute
        # target, so never use it.
        target_percent=store.charge_target,
        session_energy_wh=float(client.energy or 0),
        slots=[s.to_dict() for s in client.slots],
        next_slot_start=_iso(client.next_slot_start),
        next_slot_end=_iso(client.next_slot_end),
        updated_at=now,
    )


async def _make_client_with_retry() -> Any:
    """Create the Ohme client, retrying forever with exponential backoff."""
    delay = LOGIN_RETRY_INITIAL
    while True:
        try:
            return await ohme_client.make_client()
        except asyncio.CancelledError:
            raise
        except Exception:
            store.record_poll_failure("login_failed")
            logger.exception("Ohme login failed — retrying in %.0fs", delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, LOGIN_RETRY_MAX)


def _on_poll_task_done(task: asyncio.Task) -> None:
    """Log loudly if the poll loop ever exits unexpectedly.

    /api/health reports the task as dead (HTTP 503) so the container
    HEALTHCHECK fails and Docker restarts the service.
    """
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.critical(
            "Poll loop crashed — plug-in detection is down until the container restarts",
            exc_info=exc,
        )


async def poll_loop() -> None:
    """Background task: detect plug-in events and refresh the status snapshot."""
    main.load_persisted_target()
    logger.info(
        "API poll loop starting (interval=%ss, target=%s%%)",
        config.POLL_INTERVAL,
        store.charge_target,
    )
    client = await _make_client_with_retry()
    store.client = client

    # Populate vehicle name / model / serial once up front.
    try:
        await client.async_update_device_info()
    except Exception:
        logger.warning("Could not fetch device info on startup", exc_info=True)

    was_connected = False
    session_handled = False
    try:
        initial_status = await ohme_client.get_charger_status(client)
        was_connected = ohme_client.is_connected(initial_status)
        if was_connected:
            logger.info("Car already connected on startup — will reconfigure on next poll")
    except Exception:
        logger.warning("Could not determine initial charge state", exc_info=True)

    last_daily_sync = 0.0  # monotonic time of the last daily-stats persist (0 = never)
    try:
        while True:
            try:
                async with store.client_lock:
                    status = await ohme_client.get_charger_status(client)
                now_connected = ohme_client.is_connected(status)

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
                    logger.info("Car unplugged (status=%s)", status)
                    session_handled = False
                was_connected = now_connected

                async with store.client_lock:
                    store.update(build_snapshot(client, connected=now_connected))

                # Append a telemetry point for Grafana (best-effort, no-op when
                # persistence is disabled). Outside the lock: it doesn't touch the
                # Ohme client.
                await db.record_telemetry(store.status)

                # Refresh Ohme's daily totals into Postgres on a slow cadence so
                # the history is populated even when nobody opens the dashboard.
                if db.is_enabled():
                    now_mono = time.monotonic()
                    if now_mono - last_daily_sync >= config.DAILY_STATS_INTERVAL:
                        await _persist_daily_stats(client)
                        last_daily_sync = now_mono
            except Exception:
                # Keep the last good snapshot: a transient Ohme hiccup shouldn't
                # blank the dashboard. The failure is surfaced via lastError and
                # the snapshot's updatedAt simply stops advancing.
                logger.exception("Error during poll — will retry next interval")
                store.record_poll_failure("poll_failed")

            await asyncio.sleep(config.POLL_INTERVAL)
    finally:
        await client.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Added here (not at import time) so it survives uvicorn configuring its own
    # loggers, which happens after the app module is imported.
    access_logger = logging.getLogger("uvicorn.access")
    if _quiet_access_filter not in access_logger.filters:
        access_logger.addFilter(_quiet_access_filter)

    await db.init()

    global _poll_task
    task: Optional[asyncio.Task] = None
    if not DISABLE_POLLING:
        task = asyncio.create_task(poll_loop())
        task.add_done_callback(_on_poll_task_done)
        _poll_task = task
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:  # noqa: BLE001 - already logged by _on_poll_task_done
                pass
            _poll_task = None
        await db.close()


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
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["*"],
    )


# --- summary parsing + cache ---------------------------------------------------

_summary_cache: dict[str, Any] = {"key": None, "value": None, "at": 0.0}


# Ohme returns Money amounts in the currency's *minor* unit (pence for GBP), so
# e.g. a 7.284 p/kWh price comes back as amount "7.284" and a £13.97 cost as
# "1396.663". Divide by 100 to convert to major units (pounds) here, once, so the
# whole pipeline downstream works in pounds. (This app is GBP-only.)
_MINOR_UNITS_PER_MAJOR = 100


def _money(node: Any) -> tuple[float, Optional[str]]:
    """Return (amount_in_major_units, currencyCode) from an Ohme Money dict."""
    if not isinstance(node, dict):
        return 0.0, None
    try:
        amount = float(node.get("amount") or 0)
    except (TypeError, ValueError):
        amount = 0.0
    return amount / _MINOR_UNITS_PER_MAJOR, node.get("currencyCode")


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


class TargetUpdate(BaseModel):
    """Request body for PUT /api/settings/target."""

    targetPercent: int = Field(ge=settings.TARGET_MIN, le=settings.TARGET_MAX)


async def _reapply_target_if_connected(target: int) -> bool:
    """Push a newly-set target to Ohme immediately if the car is plugged in.

    Returns True only if Ohme was reconfigured. Best-effort: failure here doesn't
    fail the request — the target still takes effect on the next plug-in/poll.
    """
    client = store.client
    soc = store.last_soc
    if client is None or not store.status.connected or soc is None or soc >= target:
        return False
    try:
        async with store.client_lock:
            await ohme_client.set_target(client, current_soc=soc, target_percent=target)
        return True
    except Exception:  # noqa: BLE001 - never let an Ohme hiccup fail the settings write
        logger.warning("Could not re-apply charge target to Ohme", exc_info=True)
        return False


@app.get("/api/health")
async def health() -> JSONResponse:
    """Liveness for the container HEALTHCHECK.

    Returns 503 once the poll loop has died, so Docker marks the container
    unhealthy and restarts it — a dead loop means plug-in detection is down
    even though the web server itself still responds.
    """
    poll_alive = DISABLE_POLLING or (_poll_task is not None and not _poll_task.done())
    return JSONResponse(
        {
            "status": "ok" if poll_alive else "error",
            "ready": store.ready,
            "pollAlive": poll_alive,
            "lastSuccessfulPoll": store.status.updated_at,
            "lastError": store.last_poll_error,
        },
        status_code=200 if poll_alive else 503,
    )


@app.put("/api/settings/target")
async def set_charge_target(update: TargetUpdate) -> JSONResponse:
    target = update.targetPercent
    store.set_charge_target(target)
    persisted = settings.save_target(target)
    applied = await _reapply_target_if_connected(target)
    # Reflect the new target in the cached snapshot so a subsequent GET /api/status
    # sees it immediately rather than after the next poll.
    if store.ready:
        store.status.target_percent = target
    logger.info(
        "Charge target set to %s%% (persisted=%s, applied=%s)", target, persisted, applied
    )
    return JSONResponse({"targetPercent": target, "persisted": persisted, "applied": applied})


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
            "chargeTarget": store.charge_target,
            "pollIntervalSeconds": config.POLL_INTERVAL,
        },
        "updatedAt": store.status.updated_at,
        "ready": store.ready,
        # Why the most recent poll failed, or null when it succeeded. The data
        # above is the last good snapshot, so the UI can flag it as stale.
        "lastError": store.last_poll_error,
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


async def _persist_daily_stats(client: Any, days: int = 90) -> None:
    """Fetch Ohme's charge summary and upsert its per-day totals into Postgres.

    Best-effort and only does work when persistence is enabled. Used by the poll
    loop so Grafana's daily history stays current without the dashboard open.
    """
    if not db.is_enabled():
        return
    end_ts = int(time.time() * 1000)
    start_ts = end_ts - days * 24 * 60 * 60 * 1000
    try:
        async with store.client_lock:
            summary = await client.async_get_charge_summary(start_ts=start_ts, end_ts=end_ts)
    except Exception:
        logger.warning("Could not fetch charge summary for daily-stats persist", exc_info=True)
        return
    parsed = parse_summary({k: v for k, v in summary.items() if k != "granularity"}, days)
    await db.record_daily_stats(parsed["daily"], parsed["currency"])


@app.get("/api/statistics")
async def get_statistics(days: int = Query(default=7, ge=1, le=90)) -> JSONResponse:
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
    # Opportunistically persist the day totals we just fetched (no-op when disabled).
    await db.record_daily_stats(parsed["daily"], parsed["currency"])
    return JSONResponse(parsed)


@app.post("/api/refresh")
async def refresh() -> JSONResponse:
    """Force an immediate live re-read from Ohme and rebuild the cached snapshot.

    The read endpoints (``/api/status``, ``/api/schedule``) serve a snapshot that
    the background loop only refreshes every ``POLL_INTERVAL`` seconds. This lets
    the UI pull a fresh reading on demand. It re-queries the charge session under
    ``client_lock`` (so it never races the poll loop) and invalidates the
    statistics cache so the next ``/api/statistics`` call also re-fetches.

    Plug-in detection stays the responsibility of the background loop; this only
    refreshes the displayed snapshot, it does not (re)configure the charge target.
    """
    client = store.client
    if client is None:
        raise HTTPException(status_code=503, detail="Backend not connected to Ohme yet")

    try:
        async with store.client_lock:
            charger_status = await ohme_client.get_charger_status(client)
            connected = ohme_client.is_connected(charger_status)
            store.update(build_snapshot(client, connected=connected))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Manual refresh failed", exc_info=True)
        raise HTTPException(status_code=502, detail="Could not refresh from Ohme") from exc

    # Drop the statistics cache so the next request re-fetches from Ohme.
    _summary_cache.update(key=None, value=None, at=0.0)

    return JSONResponse({"ok": True, "updatedAt": store.status.updated_at, "ready": store.ready})
