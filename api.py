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
import copy
import csv
import datetime
import io
import json
import logging
import os
import time
from decimal import Decimal, ROUND_HALF_UP
from contextlib import asynccontextmanager
from typing import Any, Literal, Optional
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

import bluelink
from api_contracts import (
    ApplyStatus,
    ChargeActionResponseModel,
    DataQualityResponseModel,
    DayTargetsUpdate,
    DayTargetsUpdateResponseModel,
    MaxChargeUpdate,
    MonthlyReportResponseModel,
    NotificationPreferencesUpdate,
    NotificationPreferencesUpdateResponseModel,
    PersistenceStatus,
    ReadyByUpdate,
    ReadyByUpdateResponseModel,
    RefreshResponseModel,
    ScheduleResponseModel,
    SessionAuditResponseModel,
    SessionsResponseModel,
    StatisticsResponseModel,
    StatusResponseModel,
    TargetUpdate,
    TargetUpdateResponseModel,
    TripModeUpdate,
    TripModeUpdateResponseModel,
    VehicleProfileUpdate,
    VehicleProfileUpdateResponseModel,
    VehiclesResponseModel,
    VehicleUpdate,
    VehicleUpdateResponseModel,
)
import config
import db
import energy
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
    {
        "/api/health",
        "/api/status",
        "/api/schedule",
        "/api/statistics",
        "/api/sessions",
        "/api/tariff",
        "/api/energy-usage",
        "/api/data-quality",
    }
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
# Host-header allowlist protects an anonymous LAN service from DNS rebinding.
# Production deployments must add their real hostname and LAN IP explicitly.
TRUSTED_HOSTS = [
    host.strip()
    for host in os.getenv(
        "TRUSTED_HOSTS",
        "localhost,127.0.0.1,[::1],backend,autocharge-backend,autocharge",
    ).split(",")
    if host.strip()
]
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

# The running poll task, so /api/health can report whether it is still alive.
_poll_task: Optional[asyncio.Task] = None


def _next_poll_delay(consecutive_failures: int) -> float:
    """Seconds to wait before the next poll.

    Healthy (no failures): the normal POLL_INTERVAL. After a run of failed polls,
    back off exponentially — POLL_INTERVAL * 2**(failures-1) — capped at
    MAX_POLL_BACKOFF, so a sustained Ohme/Bluelink outage isn't retried every
    interval. ``store.update`` zeroes the counter on a good poll, so the cadence
    snaps back to POLL_INTERVAL on the first success.
    """
    if consecutive_failures <= 0:
        return float(config.POLL_INTERVAL)
    # Cap the exponent so a long outage doesn't build a needlessly huge int; the
    # result is clamped to MAX_POLL_BACKOFF anyway.
    factor = 2 ** min(consecutive_failures - 1, 20)
    return float(min(config.POLL_INTERVAL * factor, config.MAX_POLL_BACKOFF))


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
    planned_energy_raw = sum(s.energy for s in slots) if connected else 0.0
    planned_energy_kwh = round(planned_energy_raw, 2)
    # Prefer an Agile-accurate cost: price each slot against the half-hourly rate
    # it falls in (so an overnight charge through cheap slots isn't valued at a
    # flat average). Falls back to the recent average £/kWh when Agile rates are
    # unavailable or don't fully cover the schedule.
    projected_cost = None
    projected_cost_method = None
    projected_cost_currency = None
    if connected and planned_energy_kwh > 0:
        agile_cost = octopus.cost_for_slots(slots, store.agile_rates)
        if agile_cost is not None:
            projected_cost = agile_cost
            projected_cost_method = "agile"
            projected_cost_currency = "GBP"  # Octopus Agile is GBP-only
        else:
            price = store.avg_price_per_kwh
            if price:
                projected_cost = float(
                    (Decimal(str(price)) * Decimal(str(planned_energy_raw))).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                )
                projected_cost_method = "average"
                projected_cost_currency = store.price_currency

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
        # Vehicle health, like the other Bluelink extras, is the reading captured
        # at the last plug-in — only meaningful while still connected.
        aux_battery_percent=store.last_aux_battery_percent if connected else None,
        tyre_pressure_warning=store.last_tyre_pressure_warning if connected else None,
        washer_fluid_warning=store.last_washer_fluid_warning if connected else None,
        key_battery_warning=store.last_key_battery_warning if connected else None,
        open_items=list(store.last_open_items) if connected else [],
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
        projected_cost_currency=projected_cost_currency,
        projected_cost_method=projected_cost_method,
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


async def _recreate_ohme_client(current: Any) -> Any:
    """Authenticate and atomically swap a stale client, cleaning both paths."""
    replacement = None
    try:
        replacement = await ohme_client.make_client()
        await ohme_client.update_device_info(replacement)
        async with store.client_lock:
            store.client = replacement
        await ohme_client.close_client(current)
        return replacement
    except BaseException:
        if replacement is not None:
            await ohme_client.close_client(replacement)
        raise


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
        vehicle = await bluelink.get_vehicle_state_async(store.selected_vehicle_id)
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

    This function intentionally owns only the edge-triggered alert. Durable
    completion and reconciliation are level-triggered separately, because an
    on-demand refresh or control request may update the shared snapshot before
    the background poll observes the transition.
    """
    if prev_status not in _ACTIVE_STATUSES or snap.charger_status != "finished":
        return
    if snap.session_energy_wh <= 0:
        return
    kwh = snap.session_energy_wh / 1000
    preferences = store.notification_preferences
    if preferences.charge_complete and kwh >= preferences.minimum_charge_kwh:
        name = snap.vehicle_name or "EV"
        await ntfy.send(
            f"{name} added {kwh:.1f} kWh this session.",
            title="Charging finished",
            tags="white_check_mark",
        )


async def _finalize_finished_session(snap: StatusSnapshot) -> None:
    """Persist an active session whenever its current state is ``finished``.

    Unlike the notification helper, this is deliberately level-triggered. The
    database update is idempotent and returns a session id only to the caller
    that first completes the row, keeping the lifecycle event and initial
    reconciliation single-shot even when ``finished`` spans many polls.
    """
    if snap.charger_status != "finished" or not store.active_session_key:
        return
    session_id = await db.complete_session(
        store.active_session_key,
        actual_energy_wh=snap.session_energy_wh,
        end_soc_percent=snap.battery_percent,
    )
    if session_id is None:
        return
    store.active_session_id = session_id
    await db.record_session_event(
        session_id,
        "charging_finished",
        {"energyWh": round(snap.session_energy_wh), "soc": snap.battery_percent},
    )
    await _reconcile_finished_session(snap)


# Health warnings from the SDK plus an optional user-defined 12V percentage
# threshold. Edge-triggered, so a warning present at plug-in notifies once and a
# steady one across polls doesn't.
_HEALTH_WARNINGS = (
    ("tyre_pressure_warning", "Tyre pressure low"),
    ("washer_fluid_warning", "Washer fluid low"),
    ("key_battery_warning", "Key fob battery low"),
)


async def _maybe_notify_vehicle_health(prev: StatusSnapshot, snap: StatusSnapshot) -> None:
    """Notify when a vehicle-health warning newly appears (False/None → True).

    Comparing the previous snapshot to the new one makes this edge-triggered:
    health only changes on a fresh Bluelink read, so a warning that persists
    across polls won't re-notify, and an unplug (which clears the fields) can't
    masquerade as a new warning.
    """
    preferences = store.notification_preferences
    if not preferences.vehicle_health:
        return
    raised = [
        label
        for attr, label in _HEALTH_WARNINGS
        if getattr(snap, attr) is True and getattr(prev, attr) is not True
    ]
    # Anything newly reported open that wasn't open before.
    raised.extend(f"{item} open" for item in snap.open_items if item not in prev.open_items)
    threshold = preferences.aux_battery_below_percent
    if (
        threshold is not None
        and snap.aux_battery_percent is not None
        and snap.aux_battery_percent <= threshold
        and (prev.aux_battery_percent is None or prev.aux_battery_percent > threshold)
    ):
        raised.append(f"12V battery at {snap.aux_battery_percent}%")
    if not raised:
        return
    name = snap.vehicle_name or "EV"
    await ntfy.send(
        "\n".join(raised),
        title=f"{name} — vehicle health",
        tags="warning",
    )


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
    if snap.connected and store.active_session_id is None and store.active_session_key:
        store.active_session_id = await db.get_session_id_by_key(store.active_session_key)
    await db.record_telemetry(
        snap, session_id=store.active_session_id if snap.connected else None
    )


async def _reconcile_session(
    session_id: Optional[int], counter_energy_wh: float, *, trigger: str
) -> None:
    """Price one durable session when telemetry and tariff coverage agree."""
    if session_id is None:
        return
    rows = await db.get_session_attribution_rows(session_id)
    if not rows:
        await db.record_session_event(
            session_id,
            "reconciliation_skipped",
            {"reason": "no_telemetry", "trigger": trigger},
        )
        return
    attribution = energy.attribute_car_kwh(
        rows, max_gap_seconds=max(config.POLL_INTERVAL * 3, 15 * 60)
    )
    start = rows[0][0]
    end = rows[-1][0] + datetime.timedelta(minutes=30)
    rates = await db.get_tariff_rates(start, end)
    if not rates:
        rates = store.agile_rates
    priced = octopus.price_energy_buckets(attribution.car_by_slot, rates)
    await db.record_session_reconciliation(
        session_id, priced, counter_energy_wh=counter_energy_wh
    )
    await db.record_session_event(
        session_id,
        "session_reconciled",
        {
            "counterEnergyWh": round(counter_energy_wh),
            "reconstructedEnergyWh": priced.energy_wh,
            "tariffCoverage": priced.coverage,
            "costMinor": priced.cost_minor,
            "attributionIssues": attribution.issue_count,
            "trigger": trigger,
        },
    )


async def _reconcile_finished_session(snap: StatusSnapshot) -> None:
    """Initial reconciliation when a durable row first reaches ``finished``."""
    await _reconcile_session(
        store.active_session_id, snap.session_energy_wh, trigger="finished"
    )


async def _reconcile_unplugged_session(
    session_key: Optional[str], session_id: Optional[int], energy_wh: Optional[float]
) -> None:
    """Retry reconciliation at the final physical session boundary."""
    resolved_id = session_id
    if resolved_id is None:
        resolved_id = await db.get_session_id_by_key(session_key)
    if resolved_id is None:
        return
    if energy_wh is None:
        await db.record_session_event(
            resolved_id,
            "reconciliation_skipped",
            {"reason": "no_energy_counter", "trigger": "unplugged"},
        )
        return
    await _reconcile_session(resolved_id, energy_wh, trigger="unplugged")


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
        await ohme_client.update_device_info(client)
    except Exception:
        logger.warning("Could not fetch device info on startup", exc_info=True)

    # The plug-in transition state machine is shared with main.run_loop.
    detector = main.PlugInDetector(on_unplug=_reconcile_unplugged_session)
    try:
        initial_status = await ohme_client.get_charger_status(client)
        detector.prime(initial_status)
    except Exception:
        logger.warning("Could not determine initial charge state", exc_info=True)

    last_daily_sync = 0.0  # monotonic time of the last daily-stats persist (0 = never)
    last_tariff_sync = 0.0
    ohme_session_failures = 0
    try:
        while True:
            try:
                try:
                    async with store.client_lock:
                        status = await ohme_client.get_charger_status(client)
                except Exception:
                    ohme_session_failures += 1
                    raise
                else:
                    # Only authentication/session refresh failures justify
                    # replacing the client. Optional integration failures do not.
                    ohme_session_failures = 0
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

                prev_snapshot = store.status
                prev_status = prev_snapshot.charger_status
                preferences = store.notification_preferences
                recovered = store.poll_failure_notified
                async with store.client_lock:
                    store.update(build_snapshot(client, connected=now_connected))
                if recovered and preferences.problems:
                    await ntfy.send(
                        "Back in touch with Ohme — live data restored.",
                        title="Autocharge reconnected",
                        tags="white_check_mark",
                    )
                store.poll_failure_notified = False
                # Append a telemetry point for Grafana (best-effort, no-op when
                # persistence is disabled). Outside the lock: it doesn't touch the
                # Ohme client. Identical idle rows are de-duplicated.
                await _maybe_record_telemetry(store.status)
                await _finalize_finished_session(store.status)
                await _maybe_notify_finished(prev_status, store.status)
                await _maybe_notify_vehicle_health(prev_snapshot, store.status)

                # Tariff ingestion is a background responsibility: projected and
                # actual cost accuracy must not depend on opening the dashboard.
                now_mono = time.monotonic()
                if (
                    octopus.is_enabled()
                    and now_mono - last_tariff_sync >= _TARIFF_CACHE_TTL
                ):
                    await _refresh_tariff_rates()
                    last_tariff_sync = now_mono

                # Refresh Ohme's daily totals into Postgres on a slow cadence so
                # the history is populated even when nobody opens the dashboard.
                if db.is_available():
                    if now_mono - last_daily_sync >= config.DAILY_STATS_INTERVAL:
                        await _persist_daily_stats(client)
                        # Pull recent Octopus household consumption and break out
                        # the car share (no-op when consumption isn't configured).
                        await _persist_grid_consumption()
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
                # A stale token/session object may never recover on its own.
                # Recreate only after a bounded failure run, preserving the
                # detector and durable session key outside the client.
                if ohme_session_failures >= config.OHME_RECONNECT_FAILURES:
                    try:
                        client = await _recreate_ohme_client(client)
                        ohme_session_failures = 0
                        logger.info("Recreated Ohme client after repeated session failures")
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        logger.warning("Could not recreate Ohme client yet", exc_info=True)
                # Alert exactly once when the failure streak crosses the
                # threshold; ntfy.send swallows its own errors, so this can
                # never make the poll failure worse.
                preferences = store.notification_preferences
                if (
                    preferences.problems
                    and store.consecutive_poll_failures == preferences.failure_polls
                ):
                    await ntfy.send(
                        f"{preferences.failure_polls} polls in a row have failed. "
                        "Plug-in detection and dashboard data are stale until it recovers.",
                        title="Can't reach Ohme",
                        priority="high",
                        tags="warning",
                    )
                    store.poll_failure_notified = True

            # Back off when upstreams are failing; normal cadence when healthy.
            await asyncio.sleep(_next_poll_delay(store.consecutive_poll_failures))
    finally:
        store.client = None
        await ohme_client.close_client(client)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Added here (not at import time) so it survives uvicorn configuring its own
    # loggers, which happens after the app module is imported.
    access_logger = logging.getLogger("uvicorn.access")
    if _quiet_access_filter not in access_logger.filters:
        access_logger.addFilter(_quiet_access_filter)

    await db.init()
    db_stop = asyncio.Event()
    db_reconnect_task = asyncio.create_task(db.reconnect_loop(db_stop))

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
        db_stop.set()
        await db_reconnect_task
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


async def require_csrf_header(
    x_requested_with: Optional[str] = Header(default=None),
) -> None:
    """Require the SPA's custom header on every state-changing request.

    A browser cannot attach this header cross-origin without a CORS preflight,
    which the same-origin policy rejects. Applying the rule uniformly also
    keeps JSON mutations protected if their content type or payload changes.
    The SPA sends the header on every request (see frontend ``api/client.ts``).
    """
    if x_requested_with != "autocharge-ui":
        raise HTTPException(
            status_code=403,
            detail="X-Requested-With must be autocharge-ui (CSRF protection)",
        )


app = FastAPI(
    title="Ohme Autocharge API",
    version="1.0.0",
    summary="Read-only status, schedule and statistics for the EV charging scheduler.",
    lifespan=lifespan,
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=TRUSTED_HOSTS)
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

def _money_amount(node: Any) -> tuple[Decimal, Optional[str]]:
    """Return Ohme's exact minor-unit amount and currency code."""
    if not isinstance(node, dict):
        return Decimal("0"), None
    try:
        amount = Decimal(str(node.get("amount") or 0))
    except (TypeError, ValueError, ArithmeticError):
        amount = Decimal("0")
    if not amount.is_finite():
        amount = Decimal("0")
    currency = node.get("currencyCode")
    return amount, currency


def _minor_factor(currency: Optional[str]) -> int:
    return {"JPY": 1, "KWD": 1000}.get(str(currency or "GBP").upper(), 100)


def _money(node: Any) -> tuple[float, Optional[str]]:
    """Return (amount_in_major_units, currencyCode) from an Ohme Money dict."""
    amount, currency = _money_amount(node)
    factor = _minor_factor(currency)
    return float(amount / factor), currency


def _whole_units(value: Any) -> int:
    """Normalise an upstream whole-unit counter without a float round trip."""
    try:
        amount = Decimal(str(value or 0))
    except (TypeError, ValueError, ArithmeticError):
        return 0
    if not amount.is_finite() or amount < 0:
        return 0
    return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _statistics_window(days: int, now: Optional[datetime.datetime] = None) -> dict[str, Any]:
    """The last ``days`` complete local calendar days and prior comparison window."""
    tz = _STATS_TZ or datetime.timezone.utc
    local_now = now.astimezone(tz) if now is not None else datetime.datetime.now(tz)
    end_day = local_now.date()  # today's midnight: today itself is incomplete
    start_day = end_day - datetime.timedelta(days=days)
    previous_start_day = start_day - datetime.timedelta(days=days)
    start = datetime.datetime.combine(start_day, datetime.time.min, tzinfo=tz)
    end = datetime.datetime.combine(end_day, datetime.time.min, tzinfo=tz)
    previous_start = datetime.datetime.combine(
        previous_start_day, datetime.time.min, tzinfo=tz
    )
    return {
        "days": days,
        "timezone": config.TIMEZONE,
        "start": start,
        "end": end,
        "previousStart": previous_start,
        "startMs": int(start.timestamp() * 1000),
        "endMs": int(end.timestamp() * 1000),
        "previousStartMs": int(previous_start.timestamp() * 1000),
    }


def _complete_daily_series(
    daily: list[dict[str, Any]], window: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return only upstream-reported rows inside the complete-day window."""
    by_date = {row["date"]: row for row in daily if row.get("date")}
    day = window["start"].date()
    end_day = window["end"].date()
    result = []
    while day < end_day:
        key = day.isoformat()
        row = by_date.get(key)
        if row is not None:
            result.append({**row, "isComplete": True})
        day += datetime.timedelta(days=1)
    return result


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
        stat_cost = stat.get("costStats") or {}
        day_saved_node = stat_cost.get("moneySavedVsStandardTariff")
        day_cost_node = stat_cost.get("moneyCostTotal")
        day_saved_amount, day_saved_currency = _money_amount(day_saved_node)
        day_cost_amount, day_cost_currency = _money_amount(day_cost_node)
        day_currency = day_saved_currency or day_cost_currency or currency
        factor = _minor_factor(day_currency)
        energy_wh = _whole_units(stat.get("energyChargedTotalWh"))
        start_ms = stat.get("startTime")
        date = None
        if start_ms is not None:
            date = (
                datetime.datetime.fromtimestamp(start_ms / 1000, tz=_STATS_TZ)
                .date()
                .isoformat()
            )
        daily.append(
            {
                "date": date,
                "energyKwh": round(energy_wh / 1000, 2),
                "savings": round(float(day_saved_amount / factor), 2),
                "cost": round(float(day_cost_amount / factor), 2),
                # Internal exact fields are consumed by ``record_daily_stats``.
                # The response model deliberately omits them from the public API.
                "energyWh": energy_wh,
                "savingsMinor": int(
                    day_saved_amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
                ),
                "costMinor": int(
                    day_cost_amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
                ),
                "currency": day_currency,
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


def _monthly_window(month: Optional[str]) -> tuple[str, datetime.datetime, datetime.datetime]:
    """Resolve an explicit/default month to a DST-safe local half-open window."""
    tz = _STATS_TZ or datetime.timezone.utc
    today = datetime.datetime.now(tz).date()
    if month is None:
        current_start = today.replace(day=1)
        previous_last = current_start - datetime.timedelta(days=1)
        start_day = previous_last.replace(day=1)
    else:
        try:
            start_day = datetime.date.fromisoformat(f"{month}-01")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="month must be YYYY-MM") from exc
    if start_day.month == 12:
        end_day = datetime.date(start_day.year + 1, 1, 1)
    else:
        end_day = datetime.date(start_day.year, start_day.month + 1, 1)
    start = datetime.datetime.combine(start_day, datetime.time.min, tzinfo=tz)
    end = datetime.datetime.combine(end_day, datetime.time.min, tzinfo=tz)
    return start_day.strftime("%Y-%m"), start, end


def _build_monthly_report(
    month: str,
    start: datetime.datetime,
    end: datetime.datetime,
    evidence: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Aggregate exact persisted units while retaining the underlying rows."""
    daily = evidence["daily"]
    sessions = evidence["sessions"]
    complete_daily = [row for row in daily if row["isComplete"]]
    unique_complete_dates = {row["date"] for row in complete_daily}
    now_date = datetime.datetime.now(start.tzinfo).date()
    expected_end = min(end.date(), now_date)
    expected_days = max(0, (expected_end - start.date()).days)
    complete_days = len(unique_complete_dates)
    missing_days = max(0, expected_days - complete_days)
    daily_currencies = {row["currency"] for row in complete_daily if row["currency"]}
    if not complete_daily:
        account_quality = "unavailable"
    elif len(daily_currencies) > 1:
        account_quality = "mixed_currency"
    elif end.date() <= now_date and missing_days == 0:
        account_quality = "complete"
    else:
        account_quality = "partial"
    currency = next(iter(daily_currencies)) if len(daily_currencies) == 1 else None

    configured_completed = [
        row for row in sessions
        if row["action"] == "configured" and row["completedAt"] is not None
    ]
    with_energy = [row for row in configured_completed if row["actualEnergyWh"] is not None]
    with_cost = [row for row in configured_completed if row["actualCostMinor"] is not None]
    cost_currencies = {row["currency"] for row in with_cost if row["currency"]}
    cost_currency = next(iter(cost_currencies)) if len(cost_currencies) == 1 else None
    quality_counts: dict[str, int] = {}
    for row in sessions:
        quality_counts[row["quality"]] = quality_counts.get(row["quality"], 0) + 1
    actual_cost_expected = octopus.is_enabled()

    return {
        "month": month,
        "timezone": config.TIMEZONE,
        "from": start,
        "toExclusive": end,
        "generatedAt": datetime.datetime.now(datetime.timezone.utc),
        "account": {
            "energyWh": sum(row["energyWh"] for row in complete_daily),
            "savingsMinor": (
                sum(row["savingsMinor"] for row in complete_daily) if currency else None
            ),
            "costMinor": sum(row["costMinor"] for row in complete_daily) if currency else None,
            "currency": currency,
            "completeDays": complete_days,
            "expectedDays": expected_days,
            "missingDays": missing_days,
            "quality": account_quality,
        },
        "homeSessions": {
            "total": len(sessions),
            "configuredCompleted": len(configured_completed),
            "measuredEnergyCount": len(with_energy),
            "measuredEnergyWh": sum(row["actualEnergyWh"] for row in with_energy),
            "actualCostCount": len(with_cost),
            "actualCostMinor": (
                sum(row["actualCostMinor"] for row in with_cost)
                if cost_currency is not None else None
            ),
            "costCurrency": cost_currency,
            "actualCostExpected": actual_cost_expected,
            "missingActualEnergy": len(configured_completed) - len(with_energy),
            "missingActualCost": (
                len(configured_completed) - len(with_cost) if actual_cost_expected else 0
            ),
            "qualityCounts": quality_counts,
        },
        "daily": daily,
        "sessions": sessions,
    }


def _monthly_report_csv(report: dict[str, Any]) -> str:
    """Flatten report summary and evidence into one spreadsheet-friendly file."""
    fields = [
        "recordType", "month", "date", "sessionId", "pluggedInAt", "completedAt",
        "vehicleName", "action", "quality", "energyWh", "costMinor", "savingsMinor",
        "currency", "source", "isComplete", "completeDays", "expectedDays", "missingDays",
        "sessionCount", "measuredEnergyCount", "actualCostCount", "missingActualEnergy",
        "missingActualCost", "accountEnergyWh", "accountCostMinor", "accountSavingsMinor",
        "measuredSessionEnergyWh", "actualSessionCostMinor", "actualSessionCostCurrency",
    ]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    account = report["account"]
    home = report["homeSessions"]
    writer.writerow({
        "recordType": "summary", "month": report["month"], "quality": account["quality"],
        "accountEnergyWh": account["energyWh"],
        "accountCostMinor": account["costMinor"],
        "accountSavingsMinor": account["savingsMinor"], "currency": account["currency"],
        "completeDays": account["completeDays"], "expectedDays": account["expectedDays"],
        "missingDays": account["missingDays"], "sessionCount": home["total"],
        "measuredEnergyCount": home["measuredEnergyCount"],
        "actualCostCount": home["actualCostCount"],
        "missingActualEnergy": home["missingActualEnergy"],
        "missingActualCost": home["missingActualCost"],
        "measuredSessionEnergyWh": home["measuredEnergyWh"],
        "actualSessionCostMinor": home["actualCostMinor"],
        "actualSessionCostCurrency": home["costCurrency"],
    })
    for row in report["daily"]:
        writer.writerow({
            "recordType": "daily", "month": report["month"], "date": row["date"],
            "quality": "complete" if row["isComplete"] else "incomplete",
            "energyWh": row["energyWh"], "costMinor": row["costMinor"],
            "savingsMinor": row["savingsMinor"], "currency": row["currency"],
            "source": row["source"], "isComplete": row["isComplete"],
        })
    for row in report["sessions"]:
        writer.writerow({
            "recordType": "session", "month": report["month"], "sessionId": row["id"],
            "pluggedInAt": row["pluggedInAt"], "completedAt": row["completedAt"],
            "vehicleName": row["vehicleName"], "action": row["action"],
            "quality": row["quality"], "energyWh": row["actualEnergyWh"],
            "costMinor": row["actualCostMinor"], "currency": row["currency"],
        })
    return output.getvalue()


def _persistence_status(saved: bool) -> PersistenceStatus:
    return "saved" if saved else "memory_only"


async def _reapply_target_if_connected(
    *, allow_zero_topup: bool = False
) -> ApplyStatus:
    """Push the current effective target/ready-by to Ohme if the car is plugged in.

    Reads the effective target and ready-by so any settings change — base,
    weekday, trip, or departure time — re-plans the active
    session. Returns an explicit result so the UI can distinguish an expected
    disconnected charger from a failed live apply.
    """
    client = store.client
    if client is None or not store.status.connected:
        return "not_connected"
    # The SOC recorded at plug-in goes stale as the session charges, and the
    # top-up sent to Ohme is computed from it — so re-read the real SOC first.
    # Target changes are rare (someone clicking save), so the extra Bluelink
    # round-trip is fine; fall back to the plug-in reading if it fails. The full
    # vehicle read also refreshes the displayed range/odometer.
    vehicle_id = store.selected_vehicle_id or store.last_vehicle_id
    try:
        vehicle = await bluelink.get_vehicle_state_async(store.selected_vehicle_id)
        store.record_vehicle_state(vehicle)
        soc = vehicle.soc
        vehicle_id = vehicle.vehicle_id
    except Exception:  # noqa: BLE001
        logger.warning(
            "Could not refresh SOC from Bluelink — using the plug-in reading",
            exc_info=True,
        )
        soc = store.last_soc
    target = store.effective_target_for(vehicle_id)
    ready_by = store.effective_ready_by_for(vehicle_id)
    if soc is None or (soc >= target and not allow_zero_topup):
        await db.record_session_event(
            store.active_session_id,
            "target_reapply_skipped",
            {"soc": soc, "target": target},
        )
        return "failed" if soc is None else "already_at_target"
    try:
        async with store.client_lock:
            await ohme_client.set_target(
                client,
                current_soc=soc,
                target_percent=target,
                target_time=store.ready_by_tuple_for(vehicle_id),
            )
            slots = list(client.slots)
            next_slot_start = client.next_slot_start
            next_slot_end = client.next_slot_end
        await db.record_session_event(
            store.active_session_id,
            "target_reapplied",
            {
                "soc": soc,
                "target": target,
                "readyBy": ready_by,
                "tripMode": store.trip_mode_enabled,
            },
        )
        await db.record_schedule(
            session_id=store.active_session_id,
            slots=[slot.to_dict() for slot in slots],
            next_slot_start=next_slot_start,
            next_slot_end=next_slot_end,
            reason="target_reapplied",
        )
        return "applied"
    except Exception:  # noqa: BLE001 - never let an Ohme hiccup fail the settings write
        logger.warning("Could not re-apply charge target to Ohme", exc_info=True)
        return "failed"


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


@app.get("/api/ready")
async def ready() -> JSONResponse:
    """Operational readiness, separate from restart-oriented liveness."""
    poll_alive = DISABLE_POLLING or (_poll_task is not None and not _poll_task.done())
    operational = (
        poll_alive
        and store.ready
        and (DISABLE_POLLING or store.client is not None)
        and store.last_poll_error is None
    )
    return JSONResponse(
        {
            "status": "ready" if operational else "not_ready",
            "pollAlive": poll_alive,
            "ohmeConnected": store.client is not None,
            "lastError": store.last_poll_error,
            "persistence": {
                "configured": db.is_enabled(),
                "available": db.is_available(),
            },
        },
        status_code=200 if operational else 503,
    )


@app.get("/api/data-quality", response_model=DataQualityResponseModel)
async def get_data_quality() -> DataQualityResponseModel:
    """Read-only completeness counters for operations and alerting."""
    generated_at = datetime.datetime.now(datetime.timezone.utc)
    cache_available = _summary_cache["value"] is not None
    cache_age = max(0, round(time.time() - _summary_cache["at"])) if cache_available else None
    summary = await db.get_data_quality_summary()
    if summary is None:
        return DataQualityResponseModel(
            status="unavailable",
            generatedAt=generated_at,
            persistenceAvailable=db.is_available(),
            actualCostExpected=octopus.is_enabled(),
            sessions=None,
            telemetry=None,
            consumption=None,
            daily=None,
            statisticsCache={"available": cache_available, "ageSeconds": cache_age},
        )
    needs_attention = (
        summary["sessions"]["missingActualEnergy"] > 0
        or (octopus.is_enabled() and summary["sessions"]["missingActualCost"] > 0)
        or summary["telemetry"]["unlinkedLast24h"] > 0
        or summary["consumption"]["uncertainLast30d"] > 0
    )
    return DataQualityResponseModel(
        status="attention" if needs_attention else "ok",
        generatedAt=generated_at,
        persistenceAvailable=True,
        actualCostExpected=octopus.is_enabled(),
        sessions=summary["sessions"],
        telemetry=summary["telemetry"],
        consumption=summary["consumption"],
        daily=summary["daily"],
        statisticsCache={"available": cache_available, "ageSeconds": cache_age},
    )


@app.get("/api/reports/monthly", response_model=MonthlyReportResponseModel)
async def get_monthly_report(
    month: Optional[str] = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    format: Literal["json", "csv"] = Query(default="json"),
) -> MonthlyReportResponseModel | Response:
    """Auditable calendar-month account totals and measured home sessions."""
    report_month, start, end = _monthly_window(month)
    evidence = await db.get_monthly_report_rows(start, end)
    if evidence is None:
        raise HTTPException(status_code=404, detail="History persistence is disabled")
    report = _build_monthly_report(report_month, start, end, evidence)
    if format == "csv":
        filename = f"autocharge-monthly-{report_month}.csv"
        return Response(
            content=_monthly_report_csv(report),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    return MonthlyReportResponseModel.model_validate(report)


def _reflect_effective_target() -> None:
    """Update the cached snapshot's target so a GET /api/status right after a
    settings change sees the new effective target immediately, not next poll."""
    if store.ready:
        store.status.target_percent = store.effective_target


@app.put(
    "/api/settings/target",
    dependencies=[Depends(require_csrf_header)],
    response_model=TargetUpdateResponseModel,
)
async def set_charge_target(update: TargetUpdate) -> JSONResponse:
    target = update.targetPercent
    store.set_charge_target(target)
    persisted = settings.save_target(target)
    applied = await _reapply_target_if_connected()
    _reflect_effective_target()
    logger.info(
        "Charge target set to %s%% (persisted=%s, applied=%s)", target, persisted, applied
    )
    return JSONResponse(
        {
            "targetPercent": target,
            "persistenceStatus": _persistence_status(persisted),
            "applyStatus": applied,
        }
    )


@app.put(
    "/api/settings/ready-by",
    dependencies=[Depends(require_csrf_header)],
    response_model=ReadyByUpdateResponseModel,
)
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
    return JSONResponse(
        {
            "readyBy": ready_by,
            "persistenceStatus": _persistence_status(persisted),
            "applyStatus": applied,
        }
    )


@app.put(
    "/api/settings/day-targets",
    dependencies=[Depends(require_csrf_header)],
    response_model=DayTargetsUpdateResponseModel,
)
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
            "persistenceStatus": _persistence_status(persisted),
            "applyStatus": applied,
        }
    )


@app.put(
    "/api/settings/trip-mode",
    dependencies=[Depends(require_csrf_header)],
    response_model=TripModeUpdateResponseModel,
)
async def set_trip_mode(update: TripModeUpdate) -> JSONResponse:
    """Set a durable override that is automatically consumed on unplug."""
    if update.enabled:
        store.set_trip_mode(update.targetPercent, update.readyBy)
        persisted = settings.save_trip_mode(update.targetPercent, update.readyBy)
    else:
        store.clear_trip_mode()
        persisted = settings.clear_trip_mode()
    # Cancelling while connected must send a zero top-up when the normal target
    # is already reached; otherwise Ohme could retain the old trip schedule.
    applied = await _reapply_target_if_connected(allow_zero_topup=not update.enabled)
    _reflect_effective_target()
    logger.info(
        "Trip mode %s (target=%s%% ready_by=%s persisted=%s applied=%s)",
        "enabled" if update.enabled else "cancelled",
        update.targetPercent,
        update.readyBy,
        persisted,
        applied,
    )
    return JSONResponse(
        {
            "enabled": store.trip_mode_enabled,
            "targetPercent": store.trip_target,
            "readyBy": store.trip_ready_by,
            "persistenceStatus": _persistence_status(persisted),
            "applyStatus": applied,
        }
    )


@app.put(
    "/api/settings/notifications",
    dependencies=[Depends(require_csrf_header)],
    response_model=NotificationPreferencesUpdateResponseModel,
)
async def set_notification_preferences(
    update: NotificationPreferencesUpdate,
) -> JSONResponse:
    """Persist ntfy categories and thresholds used by the poll loop."""
    preferences = update.to_settings()
    store.set_notification_preferences(preferences)
    persisted = settings.save_notification_preferences(preferences)
    return JSONResponse(
        {
            **preferences.to_json(),
            "configured": bool(config.NTFY_TOPIC),
            "persistenceStatus": _persistence_status(persisted),
        }
    )


@app.get("/api/vehicles", response_model=VehiclesResponseModel)
async def get_vehicles() -> JSONResponse:
    """List the Hyundai vehicles on the account, with the selected one flagged.

    Used by the dashboard's vehicle picker (shown only when there's more than
    one). A live Bluelink call, so fetched on demand rather than polled.
    """
    try:
        vehicles = await bluelink.list_vehicles_async()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not list vehicles from Bluelink", exc_info=True)
        raise HTTPException(status_code=502, detail="Could not list vehicles from Bluelink") from exc
    public_vehicles = [
        {key: vehicle.get(key) for key in ("id", "name", "model")}
        for vehicle in vehicles
    ]
    return JSONResponse({"vehicles": public_vehicles, "selected": store.selected_vehicle_id})


@app.put(
    "/api/settings/vehicle",
    dependencies=[Depends(require_csrf_header)],
    response_model=VehicleUpdateResponseModel,
)
async def set_vehicle(update: VehicleUpdate) -> JSONResponse:
    """Select which Hyundai vehicle to read (null = first). Persisted; re-reads
    the new vehicle's SOC and re-applies to an active session."""
    vehicle_id = update.vehicleId or None
    try:
        vehicles = await bluelink.list_vehicles_async()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not validate Hyundai vehicle selection", exc_info=True)
        raise HTTPException(
            status_code=502, detail="Could not validate vehicle with Bluelink"
        ) from exc
    if vehicle_id is not None and vehicle_id not in {str(v["id"]) for v in vehicles}:
        raise HTTPException(
            status_code=422,
            detail="Vehicle is not present on this Hyundai account",
        )
    store.set_vehicle_id(vehicle_id)
    persisted = settings.save_vehicle_id(vehicle_id)
    applied = await _reapply_target_if_connected()
    logger.info("Vehicle selection set to %s (persisted=%s, applied=%s)", vehicle_id, persisted, applied)
    return JSONResponse(
        {
            "vehicleId": vehicle_id,
            "persistenceStatus": _persistence_status(persisted),
            "applyStatus": applied,
        }
    )


@app.put(
    "/api/settings/vehicle-profile",
    dependencies=[Depends(require_csrf_header)],
    response_model=VehicleProfileUpdateResponseModel,
)
async def set_vehicle_profile(update: VehicleProfileUpdate) -> JSONResponse:
    """Create/update or remove charging defaults for one vehicle."""
    profiles = dict(store.vehicle_profiles)
    if update.enabled:
        profiles[update.vehicleId] = settings.VehicleProfile(
            update.targetPercent, update.readyBy
        )
    else:
        profiles.pop(update.vehicleId, None)
    store.set_vehicle_profiles(profiles)
    persisted = settings.save_vehicle_profiles(profiles)
    active_vehicle_id = store.selected_vehicle_id or store.last_vehicle_id
    applied = (
        await _reapply_target_if_connected(allow_zero_topup=True)
        if active_vehicle_id == update.vehicleId else "not_connected"
    )
    _reflect_effective_target()
    profile = profiles.get(update.vehicleId)
    return JSONResponse(
        {
            "vehicleId": update.vehicleId,
            "enabled": profile is not None,
            "targetPercent": profile.target_percent if profile else None,
            "readyBy": profile.ready_by if profile else None,
            "persistenceStatus": _persistence_status(persisted),
            "applyStatus": applied,
        }
    )


@app.get("/api/status", response_model=StatusResponseModel)
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
            # Read-only vehicle health. Each field is null when the car didn't
            # report it; openItems is the (possibly empty) list of things open.
            "health": {
                "auxBatteryPercent": store.status.aux_battery_percent,
                "tyrePressureWarning": store.status.tyre_pressure_warning,
                "washerFluidWarning": store.status.washer_fluid_warning,
                "keyBatteryWarning": store.status.key_battery_warning,
                "openItems": store.status.open_items,
            },
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
            # "agile" (per-slot Agile pricing) or "average" (flat recent £/kWh).
            "projectedCostMethod": store.status.projected_cost_method,
        },
        "config": {
            "chargeTarget": store.charge_target,
            "pollIntervalSeconds": config.POLL_INTERVAL,
            "timezone": config.TIMEZONE,
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
            "tripMode": {
                "enabled": store.trip_mode_enabled,
                "targetPercent": store.trip_target,
                "readyBy": store.trip_ready_by,
            },
            "notifications": {
                **store.notification_preferences.to_json(),
                "configured": bool(config.NTFY_TOPIC),
            },
            "vehicleProfiles": {
                vehicle_id: profile.to_json()
                for vehicle_id, profile in store.vehicle_profiles.items()
            },
        },
        "updatedAt": store.status.updated_at,
        "ready": store.ready,
        "automation": {
            "state": store.automation_state,
            "errorCode": store.automation_error_code,
            "lastAttemptAt": store.automation_last_attempt_at,
        },
        # Why the most recent poll failed, or null when it succeeded. The data
        # above is the last good snapshot, so the UI can flag it as stale.
        "lastError": store.last_poll_error,
    }
    return JSONResponse(payload)


@app.get("/api/schedule", response_model=ScheduleResponseModel)
async def get_schedule() -> JSONResponse:
    return JSONResponse(
        {
            "slots": store.status.slots,
            "nextSlotStart": store.status.next_slot_start,
            "nextSlotEnd": store.status.next_slot_end,
            "connected": store.status.connected,
            "updatedAt": store.status.updated_at,
            "timezone": config.TIMEZONE,
        }
    )


_TARIFF_CACHE_TTL = 1800  # 30 min; Agile rates change at most once a day
_tariff_cache: dict[str, Any] = {"value": None, "at": 0.0}


async def _refresh_tariff_rates() -> Optional[dict[str, Any]]:
    """Fetch, cache and persist tariff windows for forecasts and actual costs."""
    rates = await octopus.fetch_rates()
    if rates is None:
        return None
    store.agile_rates = rates
    await db.upsert_tariff_rates(rates)
    upcoming = rates[:24]
    payload = {
        "enabled": True,
        "currency": "GBP",
        "rates": upcoming,
        "cheapest": sorted(upcoming, key=lambda rate: rate["pricePerKwh"])[:3],
    }
    _tariff_cache.update(value=payload, at=time.time())
    return payload


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
    payload = await _refresh_tariff_rates()
    if payload is None:
        if _tariff_cache["value"] is not None:
            return JSONResponse(_tariff_cache["value"])
        return JSONResponse({"enabled": True, "currency": "GBP", "rates": [], "cheapest": []})
    return JSONResponse(payload)


@app.get("/api/energy-usage")
async def get_energy_usage(date: Optional[str] = Query(default=None)) -> JSONResponse:
    """Half-hourly whole-house import vs car charging for a single day.

    ``date`` is a ``YYYY-MM-DD`` string in the configured timezone; it defaults to
    **yesterday** because Octopus consumption data lags ~a day (today is usually
    incomplete). ``enabled`` is false when the consumption feature is unconfigured
    or persistence is off — the dashboard hides the card, mirroring
    ``/api/sessions`` and ``/api/tariff``.
    """
    if not octopus.consumption_is_enabled() or not db.is_available():
        return JSONResponse(
            {
                "enabled": False,
                "slots": [],
                "totals": None,
                "date": None,
                "latestDate": None,
                "timezone": str(_STATS_TZ or datetime.timezone.utc),
            }
        )

    tz = _STATS_TZ or datetime.timezone.utc
    latest_day = (datetime.datetime.now(tz) - datetime.timedelta(days=1)).date()
    if date:
        try:
            day = datetime.date.fromisoformat(date)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD") from exc
    else:
        day = latest_day

    # Local-midnight bounds for the requested day, so a day's 48 slots line up
    # with the user's calendar rather than the container's UTC day.
    start = datetime.datetime.combine(day, datetime.time.min, tzinfo=tz)
    end = start + datetime.timedelta(days=1)
    rows = await db.get_grid_consumption(start, end)
    if rows is None:
        return JSONResponse(
            {
                "enabled": False,
                "slots": [],
                "totals": None,
                "date": None,
                "latestDate": latest_day.isoformat(),
                "timezone": str(tz),
            }
        )

    totals = {
        "importKwh": round(sum(r["importKwh"] or 0 for r in rows), 2),
        "carKwh": round(sum(r["carKwh"] or 0 for r in rows), 2),
        "houseKwh": round(sum(r["houseKwh"] or 0 for r in rows), 2),
        "unattributedKwh": round(sum(r.get("unattributedKwh") or 0 for r in rows), 2),
    }
    return JSONResponse(
        {
            "enabled": True,
            "date": day.isoformat(),
            "latestDate": latest_day.isoformat(),
            "timezone": str(tz),
            "currency": "GBP",
            "slots": rows,
            "totals": totals,
        }
    )


@app.get("/api/sessions", response_model=SessionsResponseModel)
async def get_sessions(limit: int = Query(default=10, ge=1, le=50)) -> JSONResponse:
    """Recent plug-in sessions from the Postgres history.

    ``enabled`` is false when persistence is off (or unreadable) — the
    dashboard hides the history card entirely rather than showing an empty one.
    """
    sessions = await db.get_recent_sessions(limit)
    if sessions is None:
        return JSONResponse({"enabled": False, "sessions": []})
    return JSONResponse({"enabled": True, "sessions": sessions})


# Column order for the export — kept in one place so CSV header and JSON keys
# stay in lockstep with the dict shape db.get_all_sessions returns.
_EXPORT_FIELDS = (
    "id",
    "pluggedInAt",
    "vehicleName",
    "socPercent",
    "targetPercent",
    "topupPercent",
    "action",
    "odometerMiles",
    "sohPercent",
    "actualEnergyKwh",
    "actualCost",
    "costCurrency",
    "costMethod",
    "tariffCoverage",
    "quality",
    "completedAt",
)


@app.get("/api/sessions/export")
async def export_sessions(format: str = Query(default="csv", pattern="^(csv|json)$")) -> Response:
    """Download the *full* charge-session history as a CSV or JSON file.

    Unlike ``/api/sessions`` (which serves the few most recent for the card),
    this returns every row, oldest first, as an attachment for spreadsheets or
    archival. 404s when persistence is disabled — there is nothing to export.
    """
    sessions = await db.get_all_sessions()
    if sessions is None:
        raise HTTPException(status_code=404, detail="History persistence is disabled")

    stamp = datetime.datetime.now(_STATS_TZ).strftime("%Y%m%d")
    filename = f"autocharge-sessions-{stamp}.{format}"
    disposition = {"Content-Disposition": f'attachment; filename="{filename}"'}

    if format == "json":
        body = json.dumps(sessions, indent=2)
        return Response(content=body, media_type="application/json", headers=disposition)

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=_EXPORT_FIELDS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(sessions)
    return Response(
        content=buffer.getvalue(), media_type="text/csv; charset=utf-8", headers=disposition
    )


@app.get("/api/sessions/{session_id}/telemetry")
async def get_session_telemetry(session_id: int) -> JSONResponse:
    """Per-poll charge curve (SOC + power over time) for one session.

    ``enabled`` is false when persistence is off (the sessions card itself is
    hidden then, so this is defensive). A 404 means the session id is unknown.
    """
    if not db.is_available():
        return JSONResponse({"enabled": False, "points": []})
    points = await db.get_session_telemetry(session_id)
    if points is None:
        raise HTTPException(status_code=404, detail="Unknown session")
    return JSONResponse({"enabled": True, "points": points})


@app.get("/api/sessions/{session_id}/audit", response_model=SessionAuditResponseModel)
async def get_session_audit(session_id: int) -> SessionAuditResponseModel:
    """Identity, lifecycle, schedule revisions and measured tariff intervals."""
    if not db.is_available():
        raise HTTPException(status_code=404, detail="History persistence is disabled")
    audit = await db.get_session_audit(session_id)
    if audit is None:
        raise HTTPException(status_code=404, detail="Unknown session")
    return SessionAuditResponseModel.model_validate(audit)


@app.get("/api/soh-history")
async def get_soh_history(limit: int = Query(default=90, ge=1, le=365)) -> JSONResponse:
    """Battery state-of-health readings over time (one point per change).

    ``enabled`` is false when persistence is off (or unreadable) — the dashboard
    hides the trend card, falling back to the single current value shown on the
    status ring.
    """
    history = await db.get_soh_history(limit)
    if history is None:
        return JSONResponse({"enabled": False, "history": []})
    return JSONResponse({"enabled": True, "history": history})


async def _persist_daily_stats(client: Any, days: int = 90) -> None:
    """Fetch Ohme's charge summary and upsert its per-day totals into Postgres.

    Best-effort and only does work when persistence is enabled. Used by the poll
    loop so Grafana's daily history stays current without the dashboard open.
    """
    if not db.is_available():
        return
    window = _statistics_window(days)
    try:
        async with store.client_lock:
            summary = await ohme_client.get_charge_summary(
                client,
                start_ts=window["startMs"], end_ts=window["endMs"]
            )
    except Exception:
        logger.warning("Could not fetch charge summary for daily-stats persist", exc_info=True)
        return
    parsed = parse_summary({k: v for k, v in summary.items() if k != "granularity"}, days)
    parsed["daily"] = _complete_daily_series(parsed["daily"], window)
    _cache_avg_price(parsed)
    await db.record_daily_stats(
        parsed["daily"],
        parsed["currency"],
        window_start=window["start"].date(),
        window_end=window["end"].date(),
    )


async def _persist_grid_consumption(days: int = 3) -> None:
    """Fetch recent Octopus household consumption and upsert the car/house split.

    Resumes from a durable cursor (or the configured initial backfill), while
    always overlapping at least the last ``days`` for corrected readings. It
    reconstructs the car's per-slot share from telemetry and upserts the split
    into ``grid_consumption``. Best-effort and a no-op unless consumption and
    persistence are enabled. The cursor advances only after rows commit.
    """
    if not octopus.consumption_is_enabled() or not db.is_available():
        return
    now = datetime.datetime.now(datetime.timezone.utc)
    cursor = await db.get_ingestion_cursor("octopus_consumption")
    if cursor is None:
        period_from = now - datetime.timedelta(days=config.CONSUMPTION_BACKFILL_DAYS)
    else:
        period_from = min(
            cursor - datetime.timedelta(days=1), now - datetime.timedelta(days=days)
        )
    consumption = await octopus.fetch_consumption(period_from, now)
    if not consumption:
        return
    # Widen the telemetry read a little before the window so the first slot's
    # cumulative-energy delta has a preceding reading to diff against.
    tele_from = period_from - datetime.timedelta(seconds=max(config.POLL_INTERVAL * 2, 600))
    telemetry = await db.get_telemetry_between(tele_from, now)
    attribution = energy.attribute_car_kwh(
        telemetry or [], max_gap_seconds=max(config.POLL_INTERVAL * 3, 15 * 60)
    )
    rows = energy.merge_usage(consumption, attribution)
    if not await db.upsert_grid_consumption(rows):
        return
    ends = [
        datetime.datetime.fromisoformat(row["to"].replace("Z", "+00:00"))
        for row in consumption
        if row.get("to")
    ]
    if ends:
        await db.set_ingestion_cursor(
            "octopus_consumption", max(ends), {"rows": len(rows), "overlapDays": days}
        )


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
    """Weekly summary from a parsed charge summary — one fact per line so it
    reads as a tidy list in the notification rather than a run-on sentence."""
    totals = parsed["totals"]
    currency = parsed["currency"]
    symbol = "£" if currency == "GBP" else ""

    def money(value: float) -> str:
        return f"{symbol}{value:.2f}" if symbol else f"{value:.2f} {currency or ''}".strip()

    return "\n".join(
        [
            "Last 7 days:",
            f"• {totals['energyKwh']:.1f} kWh charged",
            f"• {money(totals['costTotal'])} cost",
            f"• {money(totals['savingsVsStandard'])} saved vs standard",
            f"• {totals['carbonSavedKgVsGasCar']:.0f} kg CO₂ saved",
        ]
    )


async def _maybe_send_weekly_digest(client: Any) -> None:
    """Send a weekly ntfy summary of the last 7 days, once on its scheduled slot.

    No-op unless ntfy is configured, the digest day is valid (0–6), and it's the
    configured weekday + hour in the local timezone. ``store.last_digest_date``
    guards against re-sending across the polls within that hour.
    """
    if (
        not config.NTFY_TOPIC
        or not store.notification_preferences.weekly_digest
        or not (0 <= config.WEEKLY_DIGEST_DAY <= 6)
    ):
        return
    now_local = _now_local()
    if now_local.weekday() != config.WEEKLY_DIGEST_DAY or now_local.hour != config.WEEKLY_DIGEST_HOUR:
        return
    today = now_local.date()
    if store.last_digest_date == today:
        return

    window = _statistics_window(7, now_local)
    try:
        async with store.client_lock:
            summary = await ohme_client.get_charge_summary(
                client,
                start_ts=window["startMs"], end_ts=window["endMs"]
            )
    except Exception:
        logger.warning("Weekly digest: could not fetch charge summary", exc_info=True)
        return
    parsed = parse_summary({k: v for k, v in summary.items() if k != "granularity"}, 7)
    # Mark sent before awaiting ntfy so a slow/failed send can't double-fire.
    store.last_digest_date = today
    await ntfy.send(_format_digest(parsed), title="Weekly charging summary", tags="bar_chart")
    logger.info("Sent weekly charging digest")


async def _previous_period_totals(
    client: Any, window: dict[str, Any]
) -> Optional[dict[str, Any]]:
    """Totals for the equal-length window immediately before the current one.

    Used for the month-over-month comparison. Best-effort: None on any failure,
    so the comparison simply hides rather than failing the statistics request.
    """
    try:
        async with store.client_lock:
            summary = await ohme_client.get_charge_summary(
                client,
                start_ts=window["previousStartMs"], end_ts=window["startMs"]
            )
    except Exception:  # noqa: BLE001
        logger.warning("Could not fetch previous-period summary for comparison", exc_info=True)
        return None
    totals = parse_summary(
        {k: v for k, v in summary.items() if k != "granularity"}, window["days"]
    )["totals"]
    return {
        "energyKwh": totals["energyKwh"],
        "costTotal": totals["costTotal"],
        "savingsVsStandard": totals["savingsVsStandard"],
    }


async def _driving_metrics(window: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Fully-contained, single-vehicle charge-to-drive intervals for this window."""
    if not db.is_available():
        return None
    vehicle_id = store.selected_vehicle_id or await db.get_single_vehicle_id()
    if not vehicle_id:
        return None
    return await db.get_vehicle_driving_metrics(
        window["start"].astimezone(datetime.timezone.utc),
        window["end"].astimezone(datetime.timezone.utc),
        vehicle_id,
    )


def _efficiency(metrics: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Distance after home charging divided by matched final charger energy."""
    if not metrics or metrics["energyWh"] <= 0 or metrics["milesDriven"] <= 0:
        return None
    energy_kwh = metrics["energyWh"] / 1000
    return {
        "milesDriven": metrics["milesDriven"],
        "milesPerKwh": round(metrics["milesDriven"] / energy_kwh, 2),
        "energyKwh": round(energy_kwh, 3),
        "intervalCount": metrics["intervalCount"],
        "vehicleId": metrics["vehicleId"],
        "from": metrics["from"].isoformat() if metrics.get("from") else None,
        "to": metrics["to"].isoformat() if metrics.get("to") else None,
        "scope": "matched_home_charging",
    }


def _running_cost(metrics: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Actual reconciled home-charging cost per matched odometer mile."""
    if not metrics or metrics.get("costMinor") is None or metrics["costMilesDriven"] <= 0:
        return None
    currency = metrics.get("costCurrency") or "GBP"
    factor = {"JPY": 1, "KWD": 1000}.get(currency, 100)
    cost_total = metrics["costMinor"] / factor
    return {
        "costPerMile": round(cost_total / metrics["costMilesDriven"], 3),
        "milesDriven": metrics["costMilesDriven"],
        "costTotal": round(cost_total, 2),
        "currency": currency,
        "intervalCount": metrics["costIntervalCount"],
        "scope": "matched_actual_home_charging",
    }


def _statistics_metadata(
    parsed: dict[str, Any],
    window: dict[str, Any],
    metrics: Optional[dict[str, Any]],
    fetched_at: datetime.datetime,
) -> dict[str, Any]:
    """Attach auditable source, method, freshness and coverage to each metric family."""
    complete_through = window["end"].isoformat()
    efficiency = parsed.get("efficiency")
    running_cost = parsed.get("runningCost")
    comparison = parsed.get("comparison")
    reported_dates = {row["date"] for row in parsed["daily"] if row.get("date")}
    reported_days = len(reported_dates)
    missing_days = max(0, window["days"] - reported_days)
    contiguous_day = window["start"].date()
    while (
        contiguous_day < window["end"].date()
        and contiguous_day.isoformat() in reported_dates
    ):
        contiguous_day += datetime.timedelta(days=1)
    daily_complete_through = datetime.datetime.combine(
        contiguous_day,
        datetime.time.min,
        tzinfo=window["start"].tzinfo,
    ).isoformat()
    summary_coverage = {
        "requestedDays": window["days"],
        "from": window["start"].isoformat(),
        "toExclusive": complete_through,
        "scope": "ohme_account",
    }
    daily_coverage = {
        **summary_coverage,
        "completeDays": reported_days,
        "missingDays": missing_days,
    }

    return {
        "summary": {
            "source": "ohme_charge_summary",
            "calculationType": "upstream_reported_totals",
            "observedAt": fetched_at.isoformat(),
            "completeThrough": complete_through,
            "quality": "complete",
            "coverage": summary_coverage,
        },
        "daily": {
            "source": "ohme_charge_summary",
            "calculationType": "upstream_reported_complete_local_days",
            "observedAt": fetched_at.isoformat(),
            "completeThrough": daily_complete_through,
            "quality": (
                "complete"
                if missing_days == 0
                else "partial"
                if reported_days > 0
                else "unavailable"
            ),
            "coverage": daily_coverage,
        },
        "efficiency": {
            "source": "charge_sessions.actual_energy_wh+bluelink_odometer",
            "calculationType": "same_vehicle_charge_to_next_plugin",
            "observedAt": metrics["to"].isoformat() if metrics and metrics.get("to") else None,
            "completeThrough": complete_through,
            "quality": "measured" if efficiency else "unavailable",
            "coverage": {
                "vehicleId": metrics.get("vehicleId") if metrics else None,
                "matchedIntervals": efficiency["intervalCount"] if efficiency else 0,
                "matchedEnergyKwh": efficiency["energyKwh"] if efficiency else 0,
                "matchedMiles": efficiency["milesDriven"] if efficiency else 0,
                "boundaryPolicy": "fully_contained",
            },
        },
        "runningCost": {
            "source": "charge_sessions.reconciled_actual_cost+bluelink_odometer",
            "calculationType": "same_vehicle_actual_cost_to_next_plugin",
            "observedAt": metrics["to"].isoformat() if metrics and metrics.get("to") else None,
            "completeThrough": complete_through,
            "quality": "actual" if running_cost else "unavailable",
            "coverage": {
                "vehicleId": metrics.get("vehicleId") if metrics else None,
                "matchedIntervals": running_cost["intervalCount"] if running_cost else 0,
                "matchedMiles": running_cost["milesDriven"] if running_cost else 0,
                "costMethod": "tariff_interval_reconciliation",
            },
        },
        "comparison": {
            "source": "ohme_charge_summary",
            "calculationType": "previous_equal_calendar_window",
            "observedAt": fetched_at.isoformat() if comparison else None,
            "completeThrough": window["start"].isoformat(),
            "quality": "complete" if comparison else "unavailable",
            "coverage": {
                "requestedDays": window["days"],
                "from": window["previousStart"].isoformat(),
                "toExclusive": window["start"].isoformat(),
            },
        },
    }


def _stale_statistics(cache_age_seconds: float, reason: str) -> StatisticsResponseModel:
    """Serve the last validated snapshot with explicit staleness during an outage."""
    stale = copy.deepcopy(_summary_cache["value"])
    stale["stale"] = True
    for provenance in stale["metadata"].values():
        if provenance["quality"] != "unavailable":
            provenance["quality"] = "stale"
        provenance["coverage"]["cacheAgeSeconds"] = round(cache_age_seconds)
        provenance["coverage"]["staleReason"] = reason
    return StatisticsResponseModel.model_validate(stale)


@app.get("/api/statistics", response_model=StatisticsResponseModel)
async def get_statistics(
    days: int = Query(default=7, ge=1, le=90),
) -> StatisticsResponseModel:
    client = store.client
    if client is None:
        raise HTTPException(status_code=503, detail="Backend not connected to Ohme yet")

    window = _statistics_window(days)
    cache_key = f"days={days};end={window['end'].date().isoformat()}"
    now = time.time()
    if (
        _summary_cache["key"] == cache_key
        and _summary_cache["value"] is not None
        and now - _summary_cache["at"] < SUMMARY_CACHE_TTL
    ):
        return StatisticsResponseModel.model_validate(_summary_cache["value"])

    try:
        async with store.client_lock:
            summary = await ohme_client.get_charge_summary(
                client,
                start_ts=window["startMs"], end_ts=window["endMs"]
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to fetch charge summary", exc_info=True)
        if _summary_cache["key"] == cache_key and _summary_cache["value"] is not None:
            return _stale_statistics(now - _summary_cache["at"], type(exc).__name__)
        raise HTTPException(status_code=502, detail="Could not fetch statistics from Ohme") from exc

    # async_get_charge_summary returns granularity as an enum; drop it before serialising.
    parsed = parse_summary({k: v for k, v in summary.items() if k != "granularity"}, days)
    parsed["stale"] = False
    parsed["daily"] = _complete_daily_series(parsed["daily"], window)
    parsed["window"] = {
        "from": window["start"].isoformat(),
        "toExclusive": window["end"].isoformat(),
        "completeThrough": window["end"].isoformat(),
        "timezone": window["timezone"],
    }
    _cache_avg_price(parsed)
    metrics = await _driving_metrics(window)
    parsed["efficiency"] = _efficiency(metrics)
    parsed["runningCost"] = _running_cost(metrics)
    parsed["scope"] = {
        "summary": "ohme_account",
        "vehicleId": metrics.get("vehicleId") if metrics else store.selected_vehicle_id,
    }
    # Period-over-period comparison: the previous equal-length window (best-effort).
    previous = await _previous_period_totals(client, window)
    parsed["comparison"] = {"previous": previous} if previous is not None else None
    fetched_at = datetime.datetime.now(datetime.timezone.utc)
    parsed["metadata"] = _statistics_metadata(parsed, window, metrics, fetched_at)
    _summary_cache.update(key=cache_key, value=parsed, at=now)
    # Opportunistically persist the day totals we just fetched (no-op when disabled).
    await db.record_daily_stats(
        parsed["daily"],
        parsed["currency"],
        window_start=window["start"].date(),
        window_end=window["end"].date(),
    )
    return StatisticsResponseModel.model_validate(parsed)


# --- charge controls -------------------------------------------------------------


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
    await db.record_session_event(
        store.active_session_id,
        "charge_control",
        {"action": name, "status": store.status.charger_status, "maxCharge": store.status.max_charge},
    )
    return JSONResponse(
        {
            "ok": True,
            "status": store.status.charger_status,
            "maxCharge": store.status.max_charge,
        }
    )


@app.post(
    "/api/charge/pause",
    dependencies=[Depends(require_csrf_header)],
    response_model=ChargeActionResponseModel,
)
async def pause_charge() -> JSONResponse:
    """Pause the active charge session."""
    return await _charge_action("pause charging", ohme_client.pause_charge)


@app.post(
    "/api/charge/resume",
    dependencies=[Depends(require_csrf_header)],
    response_model=ChargeActionResponseModel,
)
async def resume_charge() -> JSONResponse:
    """Resume a paused charge session."""
    return await _charge_action("resume charging", ohme_client.resume_charge)


@app.put(
    "/api/charge/max-charge",
    dependencies=[Depends(require_csrf_header)],
    response_model=ChargeActionResponseModel,
)
async def set_max_charge(update: MaxChargeUpdate) -> JSONResponse:
    """Toggle Ohme's max-charge (boost) mode.

    Enabling abandons the smart schedule and charges flat-out at full rate;
    disabling returns to smart charging.
    """
    action = "enable max charge" if update.enabled else "disable max charge"
    return await _charge_action(action, lambda c: ohme_client.set_max_charge(c, update.enabled))


@app.post(
    "/api/refresh",
    dependencies=[Depends(require_csrf_header)],
    response_model=RefreshResponseModel,
)
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
