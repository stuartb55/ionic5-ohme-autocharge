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
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.base import BaseHTTPMiddleware

import bluelink
import config
import db
import main
import ntfy
import octopus
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
    {"/api/health", "/api/status", "/api/schedule", "/api/statistics", "/api/sessions", "/api/tariff"}
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

# Minimum seconds between manual /api/refresh calls. Each one triggers a live
# Ohme request, and the endpoint is unauthenticated on the LAN, so a stuck
# client (or an eager finger) must not be able to hammer the upstream API.
REFRESH_MIN_INTERVAL = 10.0
_last_refresh_at: Optional[float] = None  # monotonic time of the last attempt

# Backoff schedule for the initial Ohme login. Login happens once per process
# start; failures there (the home server booting before its network is up, an
# Ohme outage) must never kill the poll loop permanently.
LOGIN_RETRY_INITIAL = 5.0
LOGIN_RETRY_MAX = 300.0

# Alert via ntfy once this many polls in a row have failed (~15 minutes at the
# default POLL_INTERVAL) — long enough to skip transient blips, short enough to
# hear about a real outage while it still matters. A recovery notice follows
# when polling succeeds again.
POLL_FAILURE_ALERT_AFTER = 5

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

    # Ohme's own configured target time, read back from the charge rule (valid
    # even when unplugged). (0, 0) means no time set.
    try:
        th, tm = client.target_time
        ohme_ready_by = f"{th:02d}:{tm:02d}" if (th or tm) else None
    except Exception:  # noqa: BLE001 - defensive: malformed/absent rule
        ohme_ready_by = None

    slots = client.slots
    # Total energy the charger will draw this session — the sum of all allocated
    # slots is grid-side (watts × hours), so it already includes charging losses.
    # Multiplied by the recent average £/kWh for a session cost estimate.
    planned_energy_kwh = round(sum(s.energy for s in slots), 2) if connected else 0.0
    price = store.avg_price_per_kwh
    projected_cost = (
        round(price * planned_energy_kwh, 2)
        if connected and price and planned_energy_kwh > 0
        else None
    )

    return StatusSnapshot(
        vehicle_name=client.current_vehicle,
        # Prefer the real Bluelink SOC captured at plug-in; Ohme's own `battery`
        # estimate is unreliable. Fall back to it only while the car is plugged
        # in but no plug-in SOC is held yet (before the first plug-in of the
        # session). Once unplugged we report unknown rather than a stale estimate.
        battery_percent=(
            store.last_soc
            if store.last_soc is not None
            else ((client.battery or None) if connected else None)
        ),
        # Driving range is only meaningful while plugged in (it's the reading
        # captured at the last plug-in); once unplugged it goes stale like the SOC.
        range_miles=store.last_range_miles if connected else None,
        soh_percent=store.last_soh_percent if connected else None,
        is_locked=store.last_is_locked if connected else None,
        latitude=store.last_latitude if connected else None,
        longitude=store.last_longitude if connected else None,
        charger_status=status_value,
        connected=connected,
        charger_online=bool(client.available),
        max_charge=bool(client.max_charge),
        charger_model=(client.device_info or {}).get("model"),
        power_watts=float(power.watts or 0),
        power_amps=float(power.amps or 0),
        power_volts=int(power.volts) if power.volts is not None else None,
        # The target in effect right now: today's per-weekday override if set,
        # else the base (runtime override or env default). NB: client.target_soc
        # holds the *top-up* amount (target − SOC) we send to Ohme, not the
        # absolute target, so never use it.
        target_percent=store.effective_target,
        session_energy_wh=float(client.energy or 0),
        planned_energy_kwh=planned_energy_kwh,
        projected_cost=projected_cost,
        projected_cost_currency=store.price_currency if projected_cost is not None else None,
        slots=[s.to_dict() for s in slots],
        next_slot_start=_iso(client.next_slot_start),
        next_slot_end=_iso(client.next_slot_end),
        # The charge is done when the last allocated slot ends. Slots may be
        # out of order, so take the max rather than the final list entry.
        projected_finish=(
            _iso(max((s.end for s in slots), default=None)) if connected else None
        ),
        ohme_ready_by=ohme_ready_by,
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


# Prior charger statuses that represent a live, in-progress session. A move from
# any of these to "finished" means a charge just completed and is worth a
# notification. "unknown" is intentionally excluded so a restart that boots
# straight into a finished session (unknown→finished) doesn't re-notify.
_ACTIVE_STATUSES = frozenset({"charging", "plugged_in", "paused"})


async def _maybe_refresh_live_soc(status: Any) -> None:
    """Re-read the SOC from Bluelink so the battery ring shows the real value.

    Fires in two situations:

    * **Seed** — the car is connected but we hold no real SOC. This is the
      restart-mid-session case: ``prime()`` treats an already-handled session as
      handled and never re-runs ``handle_plugin_event`` (which is what captures
      the SOC), yet ``store.last_soc`` is in-memory only and was lost on restart.
      Without a re-read the ring falls back to Ohme's unreliable ``battery``
      estimate (e.g. a bogus 9%). Seed it once, regardless of charging state or
      ``LIVE_SOC_INTERVAL`` — this is correctness, not the climb feature.
    * **Climb** — actively charging and the held reading is older than
      ``LIVE_SOC_INTERVAL`` (0 disables): keep the ring climbing through the
      session. The plug-in read and this share ``store.last_soc_at``, so the
      first climb lands one interval after plug-in.

    Reads Hyundai's cached state, so it never wakes the car. Display-only — it
    does not reconfigure the Ohme target (that was set at plug-in).
    """
    need_seed = ohme_client.is_connected(status) and store.last_soc is None
    if not need_seed:
        if config.LIVE_SOC_INTERVAL <= 0 or not ohme_client.is_charging(status):
            return
        last = store.last_soc_at
        if last is not None and time.monotonic() - last < config.LIVE_SOC_INTERVAL:
            return
    try:
        vehicle = await asyncio.to_thread(bluelink.get_vehicle_state, store.selected_vehicle_id)
    except Exception:  # noqa: BLE001 - a failed refresh just leaves the prior reading
        logger.warning("Live SOC refresh from Bluelink failed — keeping last reading", exc_info=True)
        return
    store.record_vehicle_state(vehicle)
    logger.info("Live SOC refreshed: %s%%", vehicle.soc)


async def _maybe_notify_finished(prev_status: str, snap: StatusSnapshot) -> None:
    """Send a session summary when an active charge transitions to finished.

    Triggered on an active→finished transition where energy was actually added —
    so a short top-up that goes plugged_in→finished between two polls still
    notifies, but a plug-in skipped at target (0 kWh) doesn't. unknown→finished
    is excluded too, so a restart into a finished session doesn't re-notify.
    """
    if prev_status not in _ACTIVE_STATUSES or snap.charger_status != "finished":
        return
    if snap.session_energy_wh <= 0:
        return
    name = snap.vehicle_name or "EV"
    kwh = snap.session_energy_wh / 1000
    await ntfy.send(f"{name} charging finished — {kwh:.1f} kWh added this session")


# Signature of the last telemetry row written, to skip identical idle repeats.
_last_telemetry_sig: Optional[tuple] = None


async def _maybe_record_telemetry(snap: StatusSnapshot) -> None:
    """Append a telemetry row, but skip identical consecutive rows while the car
    is disconnected so the table doesn't fill with unchanging idle points. While
    connected every poll is kept (power/energy keep moving)."""
    global _last_telemetry_sig
    sig = (
        snap.connected,
        snap.charger_status,
        snap.battery_percent,
        snap.power_watts,
        snap.power_amps,
        snap.session_energy_wh,
        snap.target_percent,
    )
    if not snap.connected and sig == _last_telemetry_sig:
        return
    _last_telemetry_sig = sig
    await db.record_telemetry(snap)


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
    main.load_persisted_settings()
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

    # The plug-in transition state machine is shared with main.run_loop.
    detector = main.PlugInDetector()
    try:
        initial_status = await ohme_client.get_charger_status(client)
        detector.prime(initial_status)
    except Exception:
        logger.warning("Could not determine initial charge state", exc_info=True)

    last_daily_sync = 0.0  # monotonic time of the last daily-stats persist (0 = never)
    try:
        while True:
            try:
                async with store.client_lock:
                    status = await ohme_client.get_charger_status(client)
                # detector.update may call handle_plugin_event, which makes a slow
                # Bluelink SOC fetch (in a thread) that doesn't use the Ohme client —
                # so it runs OUTSIDE client_lock to avoid stalling /api/statistics for
                # the whole plug-in event. The event acquires client_lock itself around
                # just its quick Ohme write, so that write is still serialised against
                # the dashboard's set_target and the charge-summary readers.
                now_connected = await detector.update(client, status)

                # Keep the battery ring climbing during a charge by re-reading the
                # SOC on a slow cadence (outside client_lock — Bluelink only).
                await _maybe_refresh_live_soc(status)

                prev_status = store.status.charger_status
                recovered = store.consecutive_poll_failures >= POLL_FAILURE_ALERT_AFTER
                async with store.client_lock:
                    store.update(build_snapshot(client, connected=now_connected))
                if recovered:
                    await ntfy.send("Autocharge reconnected to Ohme — live data restored")
                await _maybe_notify_finished(prev_status, store.status)

                # Append a telemetry point for Grafana (best-effort, no-op when
                # persistence is disabled). Outside the lock: it doesn't touch the
                # Ohme client. Identical idle rows are de-duplicated.
                await _maybe_record_telemetry(store.status)

                # Refresh Ohme's daily totals into Postgres on a slow cadence so
                # the history is populated even when nobody opens the dashboard.
                if db.is_enabled():
                    now_mono = time.monotonic()
                    if now_mono - last_daily_sync >= config.DAILY_STATS_INTERVAL:
                        await _persist_daily_stats(client)
                        # Same slow cadence: stop the per-poll telemetry table
                        # from growing without bound.
                        await db.prune_telemetry(config.TELEMETRY_RETENTION_DAYS)
                        last_daily_sync = now_mono

                # Send the weekly summary digest if it's due (no-op otherwise).
                await _maybe_send_weekly_digest(client)
            except Exception:
                # Keep the last good snapshot: a transient Ohme hiccup shouldn't
                # blank the dashboard. The failure is surfaced via lastError and
                # the snapshot's updatedAt simply stops advancing.
                logger.exception("Error during poll — will retry next interval")
                store.record_poll_failure("poll_failed")
                # Alert exactly once when the failure streak crosses the
                # threshold; ntfy.send swallows its own errors, so this can
                # never make the poll failure worse.
                if store.consecutive_poll_failures == POLL_FAILURE_ALERT_AFTER:
                    await ntfy.send(
                        f"Autocharge can't reach Ohme — {POLL_FAILURE_ALERT_AFTER} polls "
                        "have failed; plug-in detection and dashboard data are stale.",
                        title="Autocharge problem",
                        priority="high",
                    )

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


# Ohme's per-day stats buckets start at midnight in the account's home timezone.
# Convert bucket timestamps in that zone — not the host's — so a bucket starting
# at 23:00 UTC during BST isn't attributed to the previous calendar date.
try:
    _STATS_TZ: Optional[ZoneInfo] = ZoneInfo(config.TIMEZONE)
except Exception:  # noqa: BLE001 - bad TIMEZONE value; fall back to host-local
    logger.warning("Unknown TIMEZONE %r — using host-local time for daily stats", config.TIMEZONE)
    _STATS_TZ = None

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
            date = (
                datetime.datetime.fromtimestamp(start_ms / 1000, tz=_STATS_TZ)
                .date()
                .isoformat()
            )
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


class ReadyByUpdate(BaseModel):
    """Request body for PUT /api/settings/ready-by.

    ``readyBy`` is a 24h ``HH:MM`` string, or null to clear it (charge ASAP on
    Ohme's smart schedule).
    """

    readyBy: Optional[str] = Field(default=None, pattern=r"^([01]\d|2[0-3]):([0-5]\d)$")


class DayTargetsUpdate(BaseModel):
    """Request body for PUT /api/settings/day-targets.

    ``dayTargets`` maps weekday (0=Mon … 6=Sun) to a target percent. The map is
    a full replacement; omit a day to fall back to the base target.
    """

    dayTargets: dict[int, int]

    @field_validator("dayTargets")
    @classmethod
    def _check_bounds(cls, value: dict[int, int]) -> dict[int, int]:
        for day, pct in value.items():
            if not 0 <= day <= 6:
                raise ValueError("weekday must be 0 (Mon) to 6 (Sun)")
            if not settings.TARGET_MIN <= pct <= settings.TARGET_MAX:
                raise ValueError(f"target must be {settings.TARGET_MIN}–{settings.TARGET_MAX}")
        return value


class VehicleUpdate(BaseModel):
    """Request body for PUT /api/settings/vehicle (null selects the first vehicle)."""

    vehicleId: Optional[str] = None


async def _reapply_target_if_connected() -> bool:
    """Push the current effective target/ready-by to Ohme if the car is plugged in.

    Reads ``store.effective_target`` (and ``store.ready_by``) so any settings
    change — base target, per-weekday override, or ready-by — re-plans the active
    session. Returns True only if Ohme was reconfigured. Best-effort: failure
    here doesn't fail the request; the settings still apply on the next plug-in.
    """
    client = store.client
    if client is None or not store.status.connected:
        return False
    target = store.effective_target
    # The SOC recorded at plug-in goes stale as the session charges, and the
    # top-up sent to Ohme is computed from it — so re-read the real SOC first.
    # Target changes are rare (someone clicking save), so the extra Bluelink
    # round-trip is fine; fall back to the plug-in reading if it fails. The full
    # vehicle read also refreshes the displayed range/odometer.
    try:
        vehicle = await asyncio.to_thread(bluelink.get_vehicle_state, store.selected_vehicle_id)
        store.record_vehicle_state(vehicle)
        soc = vehicle.soc
    except Exception:  # noqa: BLE001
        logger.warning(
            "Could not refresh SOC from Bluelink — using the plug-in reading",
            exc_info=True,
        )
        soc = store.last_soc
    if soc is None or soc >= target:
        return False
    try:
        async with store.client_lock:
            await ohme_client.set_target(
                client, current_soc=soc, target_percent=target, target_time=store.ready_by_tuple
            )
        return True
    except Exception:  # noqa: BLE001 - never let an Ohme hiccup fail the settings write
        logger.warning("Could not re-apply charge target to Ohme", exc_info=True)
        return False


@app.get("/api/version")
async def version() -> JSONResponse:
    """Build version (git SHA), or 'dev' when unset (local run)."""
    return JSONResponse({"version": config.APP_VERSION or "dev"})


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


def _reflect_effective_target() -> None:
    """Update the cached snapshot's target so a GET /api/status right after a
    settings change sees the new effective target immediately, not next poll."""
    if store.ready:
        store.status.target_percent = store.effective_target


@app.put("/api/settings/target")
async def set_charge_target(update: TargetUpdate) -> JSONResponse:
    target = update.targetPercent
    store.set_charge_target(target)
    persisted = settings.save_target(target)
    applied = await _reapply_target_if_connected()
    _reflect_effective_target()
    logger.info(
        "Charge target set to %s%% (persisted=%s, applied=%s)", target, persisted, applied
    )
    return JSONResponse({"targetPercent": target, "persisted": persisted, "applied": applied})


@app.put("/api/settings/ready-by")
async def set_ready_by(update: ReadyByUpdate) -> JSONResponse:
    """Set (or clear, with null) the ready-by departure time.

    Persisted and, if the car is plugged in, pushed to Ohme immediately so the
    active session re-plans to finish by the new time.
    """
    ready_by = update.readyBy
    store.set_ready_by(ready_by)
    persisted = settings.save_ready_by(ready_by)
    # Reuse the target reapply: it re-reads the SOC and calls set_target, which
    # now carries the ready-by time.
    applied = await _reapply_target_if_connected()
    logger.info("Ready-by time set to %s (persisted=%s, applied=%s)", ready_by, persisted, applied)
    return JSONResponse({"readyBy": ready_by, "persisted": persisted, "applied": applied})


@app.put("/api/settings/day-targets")
async def set_day_targets(update: DayTargetsUpdate) -> JSONResponse:
    """Replace the per-weekday target overrides (0=Mon … 6=Sun).

    The full map is replaced: include every day you want overridden; omit a day
    to fall back to the base target. Persisted and re-applied to an active
    session if today's effective target changed.
    """
    day_targets = update.dayTargets
    store.set_day_targets(day_targets)
    persisted = settings.save_day_targets(day_targets)
    applied = await _reapply_target_if_connected()
    _reflect_effective_target()
    logger.info("Per-weekday targets set to %s (persisted=%s, applied=%s)", day_targets, persisted, applied)
    return JSONResponse(
        {
            "dayTargets": {str(d): p for d, p in day_targets.items()},
            "persisted": persisted,
            "applied": applied,
        }
    )


@app.get("/api/vehicles")
async def get_vehicles() -> JSONResponse:
    """List the Hyundai vehicles on the account, with the selected one flagged.

    Used by the dashboard's vehicle picker (shown only when there's more than
    one). A live Bluelink call, so fetched on demand rather than polled.
    """
    try:
        vehicles = await asyncio.to_thread(bluelink.list_vehicles)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not list vehicles from Bluelink", exc_info=True)
        raise HTTPException(status_code=502, detail="Could not list vehicles from Bluelink") from exc
    return JSONResponse({"vehicles": vehicles, "selected": store.selected_vehicle_id})


@app.put("/api/settings/vehicle")
async def set_vehicle(update: VehicleUpdate) -> JSONResponse:
    """Select which Hyundai vehicle to read (null = first). Persisted; re-reads
    the new vehicle's SOC and re-applies to an active session."""
    vehicle_id = update.vehicleId or None
    store.set_vehicle_id(vehicle_id)
    persisted = settings.save_vehicle_id(vehicle_id)
    applied = await _reapply_target_if_connected()
    logger.info("Vehicle selection set to %s (persisted=%s, applied=%s)", vehicle_id, persisted, applied)
    return JSONResponse({"vehicleId": vehicle_id, "persisted": persisted, "applied": applied})


@app.get("/api/status")
async def get_status() -> JSONResponse:
    payload = {
        "vehicle": {
            "name": store.status.vehicle_name,
            "batteryPercent": store.status.battery_percent,
            "rangeMiles": store.status.range_miles,
            "sohPercent": store.status.soh_percent,
            # Read-only lock status and last-known location (null when unknown).
            "isLocked": store.status.is_locked,
            "location": (
                {"latitude": store.status.latitude, "longitude": store.status.longitude}
                if store.status.latitude is not None and store.status.longitude is not None
                else None
            ),
        },
        "charger": {
            "status": store.status.charger_status,
            "connected": store.status.connected,
            "online": store.status.charger_online,
            "maxCharge": store.status.max_charge,
            "model": store.status.charger_model,
            "power": {
                "watts": store.status.power_watts,
                "amps": store.status.power_amps,
                "volts": store.status.power_volts,
            },
            "targetPercent": store.status.target_percent,
            "sessionEnergyKwh": round(store.status.session_energy_wh / 1000, 2),
            # When the charge is projected to finish (end of the last slot).
            "projectedFinish": store.status.projected_finish,
            # Estimated total energy + cost for the session (null cost until a
            # price is known). Currency mirrors the statistics endpoint.
            "plannedEnergyKwh": store.status.planned_energy_kwh,
            "projectedCost": store.status.projected_cost,
            "projectedCostCurrency": store.status.projected_cost_currency,
        },
        "config": {
            "chargeTarget": store.charge_target,
            "pollIntervalSeconds": config.POLL_INTERVAL,
            # Bounds for the target editor, so the UI stays in sync with the
            # validation on PUT /api/settings/target rather than hardcoding them.
            "targetMin": settings.TARGET_MIN,
            "targetMax": settings.TARGET_MAX,
            # Ready-by departure time (HH:MM): the user's override if set, else
            # Ohme's own configured time (which exists even when unplugged), else
            # null. readyByIsManual flags whether the value is our stored override.
            "readyBy": store.ready_by if store.ready_by is not None else store.status.ohme_ready_by,
            "readyByIsManual": store.ready_by is not None,
            # Per-weekday target overrides {"0".."6": percent}; empty when none.
            # charger.targetPercent reflects today's effective target.
            "dayTargets": {str(d): p for d, p in store.day_targets.items()},
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


_TARIFF_CACHE_TTL = 1800  # 30 min; Agile rates change at most once a day
_tariff_cache: dict[str, Any] = {"value": None, "at": 0.0}


@app.get("/api/tariff")
async def get_tariff() -> JSONResponse:
    """Upcoming Octopus Agile half-hourly rates and the cheapest upcoming slots.

    ``enabled`` is false when the tariff feature is unconfigured — the dashboard
    hides the card. Cached for 30 min; a transient fetch failure serves the last
    good payload (or empty) rather than erroring.
    """
    if not octopus.is_enabled():
        return JSONResponse({"enabled": False, "rates": [], "cheapest": []})
    now = time.time()
    if _tariff_cache["value"] is not None and now - _tariff_cache["at"] < _TARIFF_CACHE_TTL:
        return JSONResponse(_tariff_cache["value"])
    rates = await octopus.fetch_rates()
    if rates is None:
        if _tariff_cache["value"] is not None:
            return JSONResponse(_tariff_cache["value"])
        return JSONResponse({"enabled": True, "currency": "GBP", "rates": [], "cheapest": []})
    upcoming = rates[:24]  # next ~12 hours
    cheapest = sorted(upcoming, key=lambda r: r["pricePerKwh"])[:3]
    payload = {"enabled": True, "currency": "GBP", "rates": upcoming, "cheapest": cheapest}
    _tariff_cache.update(value=payload, at=now)
    return JSONResponse(payload)


@app.get("/api/sessions")
async def get_sessions(limit: int = Query(default=10, ge=1, le=50)) -> JSONResponse:
    """Recent plug-in sessions from the Postgres history.

    ``enabled`` is false when persistence is off (or unreadable) — the
    dashboard hides the history card entirely rather than showing an empty one.
    """
    sessions = await db.get_recent_sessions(limit)
    if sessions is None:
        return JSONResponse({"enabled": False, "sessions": []})
    return JSONResponse({"enabled": True, "sessions": sessions})


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
    _cache_avg_price(parsed)
    await db.record_daily_stats(parsed["daily"], parsed["currency"])


def _cache_avg_price(parsed: dict[str, Any]) -> None:
    """Remember the average £/kWh (and currency) so build_snapshot can estimate
    the current session's cost without making its own upstream call."""
    price = parsed["totals"].get("averageKwhPrice")
    if price and price > 0:
        store.avg_price_per_kwh = price
        store.price_currency = parsed["currency"]


def _now_local() -> datetime.datetime:
    """Current time in the configured timezone (host-local if it's unset/bad)."""
    return datetime.datetime.now(_STATS_TZ) if _STATS_TZ else datetime.datetime.now()


def _format_digest(parsed: dict[str, Any]) -> str:
    """One-line weekly summary from a parsed charge summary."""
    totals = parsed["totals"]
    currency = parsed["currency"]
    symbol = "£" if currency == "GBP" else ""

    def money(value: float) -> str:
        return f"{symbol}{value:.2f}" if symbol else f"{value:.2f} {currency or ''}".strip()

    return (
        f"Last 7 days: {totals['energyKwh']:.1f} kWh charged · "
        f"cost {money(totals['costTotal'])} · "
        f"saved {money(totals['savingsVsStandard'])} vs standard · "
        f"{totals['carbonSavedKgVsGasCar']:.0f} kg CO₂ saved"
    )


async def _maybe_send_weekly_digest(client: Any) -> None:
    """Send a weekly ntfy summary of the last 7 days, once on its scheduled slot.

    No-op unless ntfy is configured, the digest day is valid (0–6), and it's the
    configured weekday + hour in the local timezone. ``store.last_digest_date``
    guards against re-sending across the polls within that hour.
    """
    if not config.NTFY_TOPIC or not (0 <= config.WEEKLY_DIGEST_DAY <= 6):
        return
    now_local = _now_local()
    if now_local.weekday() != config.WEEKLY_DIGEST_DAY or now_local.hour != config.WEEKLY_DIGEST_HOUR:
        return
    today = now_local.date()
    if store.last_digest_date == today:
        return

    end_ts = int(time.time() * 1000)
    start_ts = end_ts - 7 * 24 * 60 * 60 * 1000
    try:
        async with store.client_lock:
            summary = await client.async_get_charge_summary(start_ts=start_ts, end_ts=end_ts)
    except Exception:
        logger.warning("Weekly digest: could not fetch charge summary", exc_info=True)
        return
    parsed = parse_summary({k: v for k, v in summary.items() if k != "granularity"}, 7)
    # Mark sent before awaiting ntfy so a slow/failed send can't double-fire.
    store.last_digest_date = today
    await ntfy.send(_format_digest(parsed), title="Weekly charging summary")
    logger.info("Sent weekly charging digest")


async def _previous_period_totals(client: Any, current_start_ts: int, days: int) -> Optional[dict[str, Any]]:
    """Totals for the equal-length window immediately before the current one.

    Used for the month-over-month comparison. Best-effort: None on any failure,
    so the comparison simply hides rather than failing the statistics request.
    """
    prev_end = current_start_ts
    prev_start = prev_end - days * 24 * 60 * 60 * 1000
    try:
        async with store.client_lock:
            summary = await client.async_get_charge_summary(start_ts=prev_start, end_ts=prev_end)
    except Exception:  # noqa: BLE001
        logger.warning("Could not fetch previous-period summary for comparison", exc_info=True)
        return None
    totals = parse_summary({k: v for k, v in summary.items() if k != "granularity"}, days)["totals"]
    return {
        "energyKwh": totals["energyKwh"],
        "costTotal": totals["costTotal"],
        "savingsVsStandard": totals["savingsVsStandard"],
    }


async def _compute_efficiency(days: int, energy_kwh: float) -> Optional[dict[str, Any]]:
    """Driving efficiency (mi/kWh) over the window.

    Miles driven (the odometer span across this window's charge sessions)
    divided by the energy charged. Over a long enough window energy charged ≈
    energy consumed, so this is a fair real-world figure. None when there isn't
    enough to compute it: persistence off, no energy, or fewer than two odometer
    readings to span.
    """
    if not db.is_enabled() or energy_kwh <= 0:
        return None
    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    miles = await db.get_miles_driven(since)
    if not miles or miles <= 0:
        return None
    return {"milesDriven": miles, "milesPerKwh": round(miles / energy_kwh, 2)}


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
    _cache_avg_price(parsed)
    # Driving efficiency from the odometer history (null when unavailable).
    parsed["efficiency"] = await _compute_efficiency(days, parsed["totals"]["energyKwh"])
    # Period-over-period comparison: the previous equal-length window (best-effort).
    previous = await _previous_period_totals(client, start_ts, days)
    parsed["comparison"] = {"previous": previous} if previous is not None else None
    _summary_cache.update(key=cache_key, value=parsed, at=now)
    # Opportunistically persist the day totals we just fetched (no-op when disabled).
    await db.record_daily_stats(parsed["daily"], parsed["currency"])
    return JSONResponse(parsed)


# --- charge controls -------------------------------------------------------------


class MaxChargeUpdate(BaseModel):
    """Request body for PUT /api/charge/max-charge."""

    enabled: bool


async def _charge_action(name: str, action: Any) -> JSONResponse:
    """Run an Ohme charge-control call, then refresh the cached snapshot.

    ``action`` is an async callable taking the client. The session re-read after
    the action means the next GET /api/status reflects the new charger state
    immediately instead of after the next poll interval.
    """
    client = store.client
    if client is None:
        raise HTTPException(status_code=503, detail="Backend not connected to Ohme yet")
    try:
        async with store.client_lock:
            await action(client)
            charger_status = await ohme_client.get_charger_status(client)
            store.update(
                build_snapshot(client, connected=ohme_client.is_connected(charger_status))
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Charge control '%s' failed", name, exc_info=True)
        raise HTTPException(status_code=502, detail=f"Could not {name} via Ohme") from exc
    logger.info("Charge control '%s' requested from the dashboard", name)
    return JSONResponse(
        {
            "ok": True,
            "status": store.status.charger_status,
            "maxCharge": store.status.max_charge,
        }
    )


@app.post("/api/charge/pause")
async def pause_charge() -> JSONResponse:
    """Pause the active charge session."""
    return await _charge_action("pause charging", lambda c: c.async_pause_charge())


@app.post("/api/charge/resume")
async def resume_charge() -> JSONResponse:
    """Resume a paused charge session."""
    return await _charge_action("resume charging", lambda c: c.async_resume_charge())


@app.put("/api/charge/max-charge")
async def set_max_charge(update: MaxChargeUpdate) -> JSONResponse:
    """Toggle Ohme's max-charge (boost) mode.

    Enabling abandons the smart schedule and charges flat-out at full rate;
    disabling returns to smart charging.
    """
    action = "enable max charge" if update.enabled else "disable max charge"
    return await _charge_action(action, lambda c: c.async_max_charge(update.enabled))


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

    global _last_refresh_at
    now = time.monotonic()
    if _last_refresh_at is not None and now - _last_refresh_at < REFRESH_MIN_INTERVAL:
        retry_after = int(REFRESH_MIN_INTERVAL - (now - _last_refresh_at)) + 1
        raise HTTPException(
            status_code=429,
            detail="Refreshed too recently — try again shortly",
            headers={"Retry-After": str(retry_after)},
        )
    _last_refresh_at = now

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
