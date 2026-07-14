"""
Monitors the Ohme charger for a plug-in event, then fetches the vehicle's
current battery SOC from Hyundai Bluelink and sets the Ohme charge target.

Run continuously:  python main.py
Run once (CI/test): python main.py --once
"""

import argparse
import asyncio
import datetime
import logging
import math
import sys
import uuid
from collections.abc import Awaitable, Callable

import bluelink
import ohme_client
import ntfy
import config
import db
import settings
from state import store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_persisted_settings() -> None:
    """Apply any persisted dashboard settings (charge target, ready-by) at startup."""
    persisted = settings.load_target()
    if persisted is not None:
        store.set_charge_target(persisted)
        logger.info("Loaded persisted charge target: %s%%", persisted)
    ready_by = settings.load_ready_by()
    if ready_by is not None:
        store.set_ready_by(ready_by)
        logger.info("Loaded persisted ready-by time: %s", ready_by)
    day_targets = settings.load_day_targets()
    if day_targets:
        store.set_day_targets(day_targets)
        logger.info("Loaded persisted per-weekday targets: %s", day_targets)
    trip_mode = settings.load_trip_mode()
    if trip_mode is not None:
        store.set_trip_mode(*trip_mode)
        logger.info("Loaded pending trip mode: target=%s%% ready_by=%s", *trip_mode)
    store.set_notification_preferences(settings.load_notification_preferences())
    store.set_vehicle_profiles(settings.load_vehicle_profiles())
    vehicle_id = settings.load_vehicle_id()
    if vehicle_id is not None:
        store.set_vehicle_id(vehicle_id)
        logger.info("Loaded persisted vehicle selection: %s", vehicle_id)
    store.pending_sessions = settings.load_pending_sessions()


def _outbox_timestamp(value) -> str | None:
    """Make a timestamp JSON-safe for the durable session outbox."""
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    return value if isinstance(value, str) and value else None


def _string_or_none(value) -> str | None:
    """Keep third-party client metadata JSON/DB safe at the persistence boundary."""
    return value if isinstance(value, str) and value else None


def _restore_outbox_timestamp(value) -> datetime.datetime | None:
    """Restore a timestamp from a validated, internally-produced outbox row."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _slot_payloads(slots) -> list[dict]:
    """Return only JSON-safe schedule rows from the Ohme client."""
    payloads = []
    for slot in slots:
        try:
            payload = slot.to_dict()
        except Exception:  # noqa: BLE001 - optional audit evidence only
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def _save_outbox_payload(payload: dict) -> None:
    """Keep one outbox item in memory and on the durable settings volume."""
    session_key = payload["sessionKey"]
    store.pending_sessions[session_key] = payload
    if not settings.save_pending_session(payload):
        # The in-memory copy still recovers a transient DB outage.  The warning
        # makes the narrower restart guarantee explicit if the settings volume
        # itself is unavailable.
        logger.warning("Session outbox could not be persisted; retaining it in memory")


def _stage_pending_session(
    *,
    session_key: str,
    vehicle_name: str | None,
    soc_percent: int | None,
    target_percent: int | None,
    topup_percent: int | None,
    action: str,
    odometer_miles: int | None,
    soh_percent: int | None,
    vehicle_id: str | None,
    vin: str | None,
    charger_id: str | None,
    source_observed_at: datetime.datetime | None,
    plugged_in_at: datetime.datetime,
    initial_event_type: str,
    initial_event_details: dict,
    initial_schedule: dict | None = None,
) -> None:
    """Persist the evidence needed to create one idempotent session row.

    This happens before the plug-in is marked handled.  PostgreSQL can therefore
    be absent for the whole plug-in event (or across a process restart) without
    losing the row needed to link telemetry and final energy later.
    """
    if not db.is_enabled():
        return
    payload = {
        "sessionKey": session_key,
        "vehicleName": vehicle_name,
        "socPercent": soc_percent,
        "targetPercent": target_percent,
        "topupPercent": topup_percent,
        "action": action,
        "odometerMiles": odometer_miles,
        "sohPercent": soh_percent,
        "vehicleId": vehicle_id,
        "vin": vin,
        "chargerId": charger_id,
        "sourceObservedAt": _outbox_timestamp(source_observed_at),
        "pluggedInAt": _outbox_timestamp(plugged_in_at),
        "initialEvent": {
            "type": initial_event_type,
            "details": initial_event_details,
        },
        "initialSchedule": initial_schedule,
    }
    _save_outbox_payload(payload)


def _stage_pending_session_close(
    session_key: str, *, final_energy_wh: float | None, end_soc_percent: int | None
) -> None:
    """Durably stage the final physical boundary before in-memory state clears."""
    if not db.is_enabled():
        return
    pending = settings.load_pending_sessions()
    pending.update(store.pending_sessions)
    payload = pending.get(session_key)
    if payload is None:
        # The creation outbox was already acknowledged, so the row is known to
        # exist. This close-only command is sufficient to retry a later outage.
        payload = {"sessionKey": session_key, "rowPersisted": True}
    else:
        payload = dict(payload)
    payload.update(
        {
            "unplugged": True,
            "finalEnergyWh": final_energy_wh,
            "endSocPercent": end_soc_percent,
            "completionReason": "unplugged",
        }
    )
    _save_outbox_payload(payload)


async def _record_pending_session_row(session_key: str, payload: dict) -> int | None:
    """Write the creation part of one outbox item via its idempotency key."""
    return await db.record_session(
        vehicle_name=payload.get("vehicleName"),
        soc_percent=payload.get("socPercent"),
        target_percent=payload.get("targetPercent"),
        topup_percent=payload.get("topupPercent"),
        action=payload.get("action") or "configured",
        odometer_miles=payload.get("odometerMiles"),
        soh_percent=payload.get("sohPercent"),
        session_key=session_key,
        vehicle_id=payload.get("vehicleId"),
        vin=payload.get("vin"),
        charger_id=payload.get("chargerId"),
        source_observed_at=_restore_outbox_timestamp(
            payload.get("sourceObservedAt")
        ),
        plugged_in_at=_restore_outbox_timestamp(payload.get("pluggedInAt")),
    )


async def ensure_pending_sessions(*, active_session_key: str | None = None) -> int | None:
    """Drain durable session rows into Postgres, retrying safely on every poll.

    ``db.record_session`` uses ``session_key`` as an idempotency key, so a crash
    after the INSERT commits but before this function acknowledges the outbox is
    harmless.  Multiple rows are retained because one database outage can span
    more than one physical plug-in session.
    """
    if not db.is_enabled():
        return None
    pending = settings.load_pending_sessions()
    pending.update(store.pending_sessions)
    store.pending_sessions = pending
    active_id: int | None = None
    for session_key, payload in list(pending.items()):
        session_id = None
        if payload.get("rowPersisted") is True:
            if session_key == active_session_key and store.active_session_id is not None:
                session_id = store.active_session_id
            else:
                session_id = await db.get_session_id_by_key(session_key)
            # The acknowledgement can outlive a restored/replaced database. A
            # full creation payload can safely repair that case; a close-only
            # command deliberately waits because it lacks trustworthy row data.
            if session_id is None and isinstance(payload.get("action"), str):
                payload["rowPersisted"] = False
                _save_outbox_payload(payload)
                session_id = await _record_pending_session_row(session_key, payload)
        else:
            session_id = await _record_pending_session_row(session_key, payload)
        if session_id is None:
            continue
        if payload.get("rowPersisted") is not True:
            payload["rowPersisted"] = True
            _save_outbox_payload(payload)
        if session_key == active_session_key:
            store.active_session_id = session_id
            store.active_session_key = session_key
            active_id = session_id
        initial_event = payload.get("initialEvent")
        if isinstance(initial_event, dict):
            event_type = initial_event.get("type")
            if not isinstance(event_type, str) or not await db.record_initial_session_event(
                session_id,
                event_type,
                initial_event.get("details")
                if isinstance(initial_event.get("details"), dict)
                else {},
            ):
                continue
        initial_schedule = payload.get("initialSchedule")
        if isinstance(initial_schedule, dict):
            slots = initial_schedule.get("slots")
            if not await db.record_initial_schedule(
                session_id=session_id,
                slots=slots if isinstance(slots, list) else [],
                next_slot_start=_restore_outbox_timestamp(
                    initial_schedule.get("nextSlotStart")
                ),
                next_slot_end=_restore_outbox_timestamp(
                    initial_schedule.get("nextSlotEnd")
                ),
            ):
                continue
        if payload.get("unplugged") is True and not await db.close_session(
            session_key,
            actual_energy_wh=payload.get("finalEnergyWh"),
            end_soc_percent=payload.get("endSocPercent"),
            completion_reason=payload.get("completionReason") or "unplugged",
        ):
            continue
        # A failed acknowledgement leaves the item in memory and on disk.  The
        # next idempotent retry will return the same row id and try again.
        if settings.clear_pending_session(session_key):
            store.pending_sessions.pop(session_key, None)
    return active_id


async def handle_plugin_event(
    client,
    *,
    session_key: str | None = None,
    plugged_in_at: datetime.datetime | None = None,
) -> bool:
    """Called once per session when the car transitions from unplugged → plugged in.
    Returns True only when Ohme has been successfully updated (or no update was needed)."""
    session_key = session_key or uuid.uuid4().hex
    plugged_in_at = plugged_in_at or datetime.datetime.now(datetime.timezone.utc)
    logger.info("Plug-in detected (session=%s) — fetching vehicle state from Bluelink...", session_key)
    store.record_automation_attempt("pending")
    try:
        # hyundai_kia_connect_api is synchronous; run it in a thread (bounded by
        # UPSTREAM_TIMEOUT) so a hung Bluelink call can't stall the loop.
        vehicle = await bluelink.get_vehicle_state_async(store.selected_vehicle_id)
    except Exception:
        store.record_automation_attempt("error", "bluelink_read_failed")
        logger.exception("Failed to fetch SOC from Hyundai Bluelink — will retry next poll")
        await _notify_plugin_failure(
            "Couldn't read the battery SOC from Bluelink — this charge may not be "
            "configured yet. Retrying automatically."
        )
        return False

    # Remember the real SOC (plus range/odometer) so the dashboard shows it
    # instead of Ohme's unreliable internal battery estimate.
    store.record_vehicle_state(vehicle)
    soc = vehicle.soc

    # effective_target applies today's per-weekday override (if any), else the base.
    target = store.effective_target_for(vehicle.vehicle_id)
    ready_by = store.effective_ready_by_for(vehicle.vehicle_id)

    if soc >= target:
        logger.info(
            "SOC %s%% already at or above target %s%% — no action needed",
            soc,
            target,
        )
        _stage_pending_session(
            vehicle_name=_string_or_none(client.current_vehicle),
            soc_percent=soc,
            target_percent=target,
            topup_percent=0,
            action="skipped_at_target",
            odometer_miles=vehicle.odometer_miles,
            soh_percent=vehicle.soh_percent,
            session_key=session_key,
            vehicle_id=vehicle.vehicle_id,
            vin=vehicle.vin,
            charger_id=(
                client.serial
                if isinstance(getattr(client, "serial", None), str)
                else None
            ),
            source_observed_at=vehicle.observed_at,
            plugged_in_at=plugged_in_at,
            initial_event_type="skipped_at_target",
            initial_event_details={
                "soc": soc,
                "target": target,
                "tripMode": store.trip_mode_enabled,
            },
        )
        await ensure_pending_sessions(active_session_key=session_key)
        store.plugin_failure_notified = False
        store.record_automation_attempt("configured")
        return True

    logger.info(
        "SOC %s%% is below target %s%% — configuring Ohme...",
        soc,
        target,
    )
    try:
        # Serialise the Ohme write behind client_lock so it can't interleave with
        # the dashboard's own set_target (_reapply_target_if_connected holds the
        # same lock) or a concurrent charge-summary read on the shared client. The
        # slow Bluelink SOC fetch above stays outside the lock so it never stalls
        # the API; only the quick Ohme mutation is serialised.
        async with store.client_lock:
            await ohme_client.set_target(
                client,
                current_soc=soc,
                target_percent=target,
                target_time=store.ready_by_tuple_for(vehicle.vehicle_id),
            )
            # Capture everything we report on (notification text + DB snapshot)
            # while still holding the lock, so a concurrent charge-summary read
            # on the shared client can't rebuild client.slots between the
            # set_target write and these reads.
            vehicle_name = _string_or_none(client.current_vehicle) or "EV"
            slots = list(client.slots)
            next_slot_start = client.next_slot_start
            next_slot_end = client.next_slot_end
        _stage_pending_session(
            vehicle_name=vehicle_name,
            soc_percent=soc,
            target_percent=target,
            topup_percent=target - soc,
            action="configured",
            odometer_miles=vehicle.odometer_miles,
            soh_percent=vehicle.soh_percent,
            session_key=session_key,
            vehicle_id=vehicle.vehicle_id,
            vin=vehicle.vin,
            charger_id=(
                client.serial
                if isinstance(getattr(client, "serial", None), str)
                else None
            ),
            source_observed_at=vehicle.observed_at,
            plugged_in_at=plugged_in_at,
            initial_event_type="target_configured",
            initial_event_details={
                "soc": soc,
                "target": target,
                "tripMode": store.trip_mode_enabled,
            },
            initial_schedule={
                "slots": _slot_payloads(slots),
                "nextSlotStart": _outbox_timestamp(next_slot_start),
                "nextSlotEnd": _outbox_timestamp(next_slot_end),
            },
        )
        await ensure_pending_sessions(active_session_key=session_key)
        # Multi-line body so each fact is on its own line — far easier to scan on
        # a phone than one run-on sentence. The vehicle name goes in the title.
        lines = [f"Charging {soc}% → {target}%"]
        if ready_by:
            lines.append(f"Ready by {ready_by}")
        if store.trip_mode_enabled:
            lines.append("One-time trip charge")
        schedule = ", ".join(str(s) for s in slots)
        if schedule:
            lines.append(f"Schedule: {schedule}")
        if store.notification_preferences.plug_in:
            await ntfy.send(
                "\n".join(lines), title=f"{vehicle_name} plugged in", tags="electric_plug"
            )
        store.plugin_failure_notified = False
        store.record_automation_attempt("configured")
        return True
    except Exception:
        store.record_automation_attempt("error", "ohme_target_failed")
        logger.exception("Failed to set Ohme charge target — will retry next poll")
        await _notify_plugin_failure(
            "Couldn't set the Ohme charge target — this charge may not be "
            "configured yet. Retrying automatically."
        )
        return False


async def _notify_plugin_failure(message: str) -> None:
    """Alert once per plug-in session that handling it is failing.

    The poll loop retries every interval, so without the once-per-session
    guard a persistent failure would notify every few minutes.
    """
    if store.plugin_failure_notified:
        return
    store.plugin_failure_notified = True
    if store.notification_preferences.problems:
        await ntfy.send(message, title="Autocharge problem", priority="high", tags="warning")


UnplugHook = Callable[
    [str | None, int | None, float | None], Awaitable[None]
]


class PlugInDetector:
    """Tracks plug/unplug transitions and fires :func:`handle_plugin_event` once
    per plug-in session.

    Shared by :func:`run_loop` and :func:`api.poll_loop` so the transition state
    machine lives in one place. The caller fetches the charger status each tick
    (``api`` does it under ``client_lock``; ``main`` doesn't) and hands it to
    :meth:`update`, which owns the once-per-session and unplug logic.
    """

    def __init__(self, *, on_unplug: UnplugHook | None = None) -> None:
        self.was_connected = False
        self.session_handled = False
        self.session_key: str | None = None
        self.plugged_in_at: datetime.datetime | None = None
        self.on_unplug = on_unplug

    def prime(self, status) -> None:
        """Seed the initial connection state from a startup snapshot.

        A single snapshot can't distinguish a restart *during* a session we
        already handled from a car that was plugged in while we were down, so we
        consult the persisted ``sessionActive`` marker:

        * connected + ``sessionActive`` True → the session was already configured
          before the restart. Treat it as handled so we don't re-send a
          notification or repeat the Ohme write; any queued database row is
          replayed independently from its durable outbox.
        * connected + not ``sessionActive`` → the car was plugged in while the
          container was down; the session was never configured. Leave it
          unhandled so the next poll configures, records and notifies once.
        """
        self.was_connected = ohme_client.is_connected(status)
        if not self.was_connected:
            return
        self.session_key = settings.load_session_key() or uuid.uuid4().hex
        self.plugged_in_at = datetime.datetime.now(datetime.timezone.utc)
        settings.save_session_marker(self.session_key, handled=settings.load_session_active())
        store.active_session_key = self.session_key
        if settings.load_session_active():
            self.session_handled = True
            store.record_automation_attempt("configured")
            logger.info("Car already connected on startup — session already handled before restart")
        else:
            self.session_handled = False
            store.record_automation_attempt("pending")
            logger.info("Car connected on startup with no handled session — will configure on next poll")

    async def update(self, client, status) -> bool:
        """Advance the state machine for one poll. Calls
        :func:`handle_plugin_event` once when a plug-in is first seen (retrying
        each tick until it succeeds) and clears the recorded SOC on unplug.

        Returns whether the car is currently connected.
        """
        now_connected = ohme_client.is_connected(status)

        if now_connected and not self.was_connected:
            # Transition: disconnected → connected (car just plugged in)
            self.session_handled = False
            store.last_session_energy_wh = None
            self.session_key = uuid.uuid4().hex
            self.plugged_in_at = datetime.datetime.now(datetime.timezone.utc)
            # Persist the key before any upstream/DB work. If the process dies
            # after inserting a row, the retry uses the same unique key.
            settings.save_session_marker(self.session_key, handled=False)
            store.active_session_key = self.session_key
            store.record_automation_attempt("pending")

        if now_connected:
            # Capture the cumulative counter before a later DISCONNECTED refresh
            # resets ``client.energy`` to zero inside the Ohme library.
            store.record_session_energy(getattr(client, "energy", None))

        if now_connected and not self.session_handled:
            if self.session_key is None:
                self.session_key = settings.load_session_key() or uuid.uuid4().hex
                self.plugged_in_at = datetime.datetime.now(datetime.timezone.utc)
                settings.save_session_marker(self.session_key, handled=False)
            self.session_handled = await handle_plugin_event(
                client, session_key=self.session_key, plugged_in_at=self.plugged_in_at
            )
            # Persist once the target is configured and its row outbox is staged,
            # so a restart doesn't repeat the Ohme write or re-notify.
            if self.session_handled:
                settings.save_session_marker(self.session_key, handled=True)

        # Retry durable row creation independently of target configuration. In
        # particular, a successful Ohme write while Postgres is down must not be
        # repeated just to recover its history row.
        if now_connected:
            await ensure_pending_sessions(active_session_key=self.session_key)

        if not now_connected and self.was_connected:
            logger.info("Car unplugged (status=%s). Waiting for next session.", status)
            session_key = self.session_key or settings.load_session_key()
            session_id = store.active_session_id
            raw_energy = getattr(client, "energy", None)
            fallback_energy = (
                float(raw_energy)
                if (
                    isinstance(raw_energy, (int, float))
                    and not isinstance(raw_energy, bool)
                    and math.isfinite(float(raw_energy))
                    and float(raw_energy) >= 0
                )
                else None
            )
            final_energy = (
                store.last_session_energy_wh
                if store.last_session_energy_wh is not None
                else fallback_energy
            )
            if session_key is not None:
                # Persist the close command before clear_soc() discards the only
                # final counter/SOC copy. The outbox acknowledges it only after
                # close_session confirms that the durable row was updated.
                _stage_pending_session_close(
                    session_key,
                    final_energy_wh=final_energy,
                    end_soc_percent=store.last_soc,
                )
                recovered_id = await ensure_pending_sessions(
                    active_session_key=session_key
                )
                session_id = recovered_id or store.active_session_id or session_id
            # The API injects its tariff/telemetry reconciliation here. Run it
            # after the durable close but before clear_soc() discards the active
            # id, key and final counter. A reporting failure must never prevent
            # the detector from clearing the physical session boundary.
            if self.on_unplug is not None:
                try:
                    await self.on_unplug(session_key, session_id, final_energy)
                except Exception:  # noqa: BLE001 - best-effort reporting hook
                    logger.warning("Unplug reconciliation failed", exc_info=True)
            if store.trip_mode_enabled:
                await db.record_session_event(
                    store.active_session_id,
                    "trip_mode_consumed",
                    {"target": store.trip_target, "readyBy": store.trip_ready_by},
                )
                settings.clear_trip_mode()
                store.clear_trip_mode()
            self.session_handled = False
            # Clear the persisted marker so the next plug-in is handled afresh.
            settings.clear_session_marker()
            # The plug-in SOC is meaningless once the car drives away.
            store.clear_soc()
            self.session_key = None
            self.plugged_in_at = None
        elif not now_connected:
            # Drain close commands left by a database outage that continued past
            # the physical unplug boundary.
            await ensure_pending_sessions()

        self.was_connected = now_connected
        return now_connected


async def run_loop() -> None:
    load_persisted_settings()
    logger.info(
        "Starting poll loop (interval=%ss, target=%s%%)",
        config.POLL_INTERVAL,
        store.charge_target,
    )
    if config.NTFY_TOPIC:
        logger.info("Ntfy notifications enabled (url=%s, topic=%s)", config.NTFY_URL, config.NTFY_TOPIC)
    else:
        logger.info("Ntfy notifications disabled — set NTFY_TOPIC to enable")

    await db.init()

    client = await ohme_client.make_client()

    # Populate the vehicle name once up front (api.poll_loop does the same).
    # Without it, current_vehicle is None until the first set_target call, so
    # the skipped-at-target session record would have no vehicle name.
    try:
        await ohme_client.update_device_info(client)
    except Exception:
        logger.warning("Could not fetch device info on startup", exc_info=True)

    # Snapshot real initial state so a container restart mid-charge doesn't
    # re-record or re-notify an already-handled session (prime() consults the
    # persisted sessionActive marker to decide).
    detector = PlugInDetector()
    try:
        initial_status = await ohme_client.get_charger_status(client)
        detector.prime(initial_status)
    except Exception:
        logger.warning("Could not determine initial charge state — will treat as disconnected")

    try:
        session_failures = 0
        while True:
            try:
                status = await ohme_client.get_charger_status(client)
                await detector.update(client, status)
                session_failures = 0
            except Exception:
                logger.exception("Error during poll — will retry next interval")
                session_failures += 1
                if session_failures >= config.OHME_RECONNECT_FAILURES:
                    replacement = None
                    try:
                        replacement = await ohme_client.make_client()
                        await ohme_client.update_device_info(replacement)
                        previous, client = client, replacement
                        replacement = None
                        await ohme_client.close_client(previous)
                        session_failures = 0
                        logger.info("Recreated Ohme client after repeated session failures")
                    except asyncio.CancelledError:
                        if replacement is not None:
                            await ohme_client.close_client(replacement)
                        raise
                    except Exception:
                        if replacement is not None:
                            await ohme_client.close_client(replacement)
                        logger.warning("Could not recreate Ohme client yet", exc_info=True)

            await asyncio.sleep(config.POLL_INTERVAL)
    finally:
        await ohme_client.close_client(client)
        await db.close()


async def run_once() -> int:
    """Single execution: fetch SOC and set Ohme target regardless of plug state.

    Returns the process exit code — non-zero when the SOC fetch or the Ohme
    configuration failed, so CI/smoke callers actually see the failure.
    """
    logger.info("Running in one-shot mode")
    load_persisted_settings()
    await db.init()
    client = await ohme_client.make_client()
    try:
        try:
            await ohme_client.update_device_info(client)
        except Exception:
            logger.warning("Could not fetch device info", exc_info=True)
        ok = await handle_plugin_event(client)
        return 0 if ok else 1
    finally:
        await ohme_client.close_client(client)
        await db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--once",
        action="store_true",
        help="Fetch SOC and set target once then exit (skips plug-in detection)",
    )
    args = parser.parse_args()

    if args.once:
        sys.exit(asyncio.run(run_once()))
    else:
        asyncio.run(run_loop())
