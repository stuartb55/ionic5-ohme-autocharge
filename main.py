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
import sys
import uuid

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
    try:
        # hyundai_kia_connect_api is synchronous; run it in a thread (bounded by
        # UPSTREAM_TIMEOUT) so a hung Bluelink call can't stall the loop.
        vehicle = await bluelink.get_vehicle_state_async(store.selected_vehicle_id)
    except Exception:
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
        if db.is_enabled():
            session_id = await db.record_session(
                vehicle_name=client.current_vehicle,
                soc_percent=soc,
                target_percent=target,
                topup_percent=0,
                action="skipped_at_target",
                odometer_miles=vehicle.odometer_miles,
                soh_percent=vehicle.soh_percent,
                session_key=session_key,
                vehicle_id=vehicle.vehicle_id,
                vin=vehicle.vin,
                charger_id=client.serial if isinstance(getattr(client, "serial", None), str) else None,
                source_observed_at=vehicle.observed_at,
                plugged_in_at=plugged_in_at,
            )
            store.active_session_id = session_id
            store.active_session_key = session_key
            await db.record_session_event(
                session_id,
                "skipped_at_target",
                {"soc": soc, "target": target, "tripMode": store.trip_mode_enabled},
            )
        store.plugin_failure_notified = False
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
            vehicle_name = client.current_vehicle or "EV"
            slots = list(client.slots)
            next_slot_start = client.next_slot_start
            next_slot_end = client.next_slot_end
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
        if db.is_enabled():
            session_id = await db.record_session(
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
                charger_id=client.serial if isinstance(getattr(client, "serial", None), str) else None,
                source_observed_at=vehicle.observed_at,
                plugged_in_at=plugged_in_at,
            )
            store.active_session_id = session_id
            store.active_session_key = session_key
            await db.record_session_event(
                session_id,
                "target_configured",
                {"soc": soc, "target": target, "tripMode": store.trip_mode_enabled},
            )
            await db.record_schedule(
                session_id=session_id,
                slots=[s.to_dict() for s in slots],
                next_slot_start=next_slot_start,
                next_slot_end=next_slot_end,
            )
        store.plugin_failure_notified = False
        return True
    except Exception:
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


class PlugInDetector:
    """Tracks plug/unplug transitions and fires :func:`handle_plugin_event` once
    per plug-in session.

    Shared by :func:`run_loop` and :func:`api.poll_loop` so the transition state
    machine lives in one place. The caller fetches the charger status each tick
    (``api`` does it under ``client_lock``; ``main`` doesn't) and hands it to
    :meth:`update`, which owns the once-per-session and unplug logic.
    """

    def __init__(self) -> None:
        self.was_connected = False
        self.session_handled = False
        self.session_key: str | None = None
        self.plugged_in_at: datetime.datetime | None = None

    def prime(self, status) -> None:
        """Seed the initial connection state from a startup snapshot.

        A single snapshot can't distinguish a restart *during* a session we
        already handled from a car that was plugged in while we were down, so we
        consult the persisted ``sessionActive`` marker:

        * connected + ``sessionActive`` True → the session was already configured
          and recorded before the restart. Treat it as handled so we don't
          re-record a duplicate ``charge_sessions`` row or re-send a notification.
          Ohme keeps its charge rule server-side, so nothing needs reconfiguring.
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
            logger.info("Car already connected on startup — session already handled before restart")
        else:
            self.session_handled = False
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
            self.session_key = uuid.uuid4().hex
            self.plugged_in_at = datetime.datetime.now(datetime.timezone.utc)
            # Persist the key before any upstream/DB work. If the process dies
            # after inserting a row, the retry uses the same unique key.
            settings.save_session_marker(self.session_key, handled=False)
            store.active_session_key = self.session_key

        if now_connected and not self.session_handled:
            if self.session_key is None:
                self.session_key = settings.load_session_key() or uuid.uuid4().hex
                self.plugged_in_at = datetime.datetime.now(datetime.timezone.utc)
                settings.save_session_marker(self.session_key, handled=False)
            self.session_handled = await handle_plugin_event(
                client, session_key=self.session_key, plugged_in_at=self.plugged_in_at
            )
            # Persist once the session is configured/recorded so a restart
            # mid-session doesn't re-record a duplicate row or re-notify.
            if self.session_handled:
                settings.save_session_marker(self.session_key, handled=True)

        if not now_connected and self.was_connected:
            logger.info("Car unplugged (status=%s). Waiting for next session.", status)
            raw_energy = getattr(client, "energy", None)
            await db.close_session(
                self.session_key or settings.load_session_key(),
                actual_energy_wh=float(raw_energy) if isinstance(raw_energy, (int, float)) else None,
                end_soc_percent=store.last_soc,
            )
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
        await client.async_update_device_info()
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
        while True:
            try:
                status = await ohme_client.get_charger_status(client)
                await detector.update(client, status)
            except Exception:
                logger.exception("Error during poll — will retry next interval")

            await asyncio.sleep(config.POLL_INTERVAL)
    finally:
        await client.close()
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
            await client.async_update_device_info()
        except Exception:
            logger.warning("Could not fetch device info", exc_info=True)
        ok = await handle_plugin_event(client)
        return 0 if ok else 1
    finally:
        await client.close()
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
