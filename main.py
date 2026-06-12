"""
Monitors the Ohme charger for a plug-in event, then fetches the vehicle's
current battery SOC from Hyundai Bluelink and sets the Ohme charge target.

Run continuously:  python main.py
Run once (CI/test): python main.py --once
"""

import argparse
import asyncio
import logging

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


def load_persisted_target() -> None:
    """Apply any persisted charge target to the store at startup."""
    persisted = settings.load_target()
    if persisted is not None:
        store.set_charge_target(persisted)
        logger.info("Loaded persisted charge target: %s%%", persisted)


async def handle_plugin_event(client) -> bool:
    """Called once per session when the car transitions from unplugged → plugged in.
    Returns True only when Ohme has been successfully updated (or no update was needed)."""
    logger.info("Plug-in detected — fetching battery SOC from Bluelink...")
    try:
        # hyundai_kia_connect_api is synchronous; run it in a thread to avoid blocking the loop
        soc = await asyncio.to_thread(bluelink.get_battery_percentage)
    except Exception:
        logger.exception("Failed to fetch SOC from Hyundai Bluelink — will retry next poll")
        return False

    # Remember the real SOC so the dashboard shows it instead of Ohme's
    # unreliable internal battery estimate.
    store.record_soc(soc)

    target = store.charge_target

    if soc >= target:
        logger.info(
            "SOC %s%% already at or above target %s%% — no action needed",
            soc,
            target,
        )
        if db.is_enabled():
            await db.record_session(
                vehicle_name=client.current_vehicle,
                soc_percent=soc,
                target_percent=target,
                topup_percent=0,
                action="skipped_at_target",
            )
        return True

    logger.info(
        "SOC %s%% is below target %s%% — configuring Ohme...",
        soc,
        target,
    )
    try:
        await ohme_client.set_target(client, current_soc=soc, target_percent=target)
        vehicle_name = client.current_vehicle or "EV"
        msg = f"{vehicle_name} plugged in at {soc}% → {target}%"
        schedule = ", ".join(str(s) for s in client.slots)
        if schedule:
            msg += f". Charge schedule: {schedule}"
        await ntfy.send(msg)
        if db.is_enabled():
            session_id = await db.record_session(
                vehicle_name=client.current_vehicle,
                soc_percent=soc,
                target_percent=target,
                topup_percent=target - soc,
                action="configured",
            )
            await db.record_schedule(
                session_id=session_id,
                slots=[s.to_dict() for s in client.slots],
                next_slot_start=client.next_slot_start,
                next_slot_end=client.next_slot_end,
            )
        return True
    except Exception:
        logger.exception("Failed to set Ohme charge target — will retry next poll")
        return False


async def run_loop() -> None:
    load_persisted_target()
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
    # reconfigure Ohme and interrupt an active session.
    was_connected = False
    session_handled = False
    try:
        initial_mode = await ohme_client.get_session_mode(client)
        was_connected = ohme_client.is_connected(initial_mode)
        if was_connected:
            logger.info("Car already connected on startup — will reconfigure Ohme on next poll")
    except Exception:
        logger.warning("Could not determine initial charge state — will treat as disconnected")
        was_connected = False
        session_handled = False

    try:
        while True:
            try:
                mode = await ohme_client.get_session_mode(client)
                now_connected = ohme_client.is_connected(mode)

                if now_connected and not was_connected:
                    # Transition: disconnected → connected (car just plugged in)
                    session_handled = False

                if now_connected and not session_handled:
                    session_handled = await handle_plugin_event(client)

                if not now_connected and was_connected:
                    logger.info("Car unplugged (mode=%s). Waiting for next session.", mode)
                    session_handled = False

                was_connected = now_connected

            except Exception:
                logger.exception("Error during poll — will retry next interval")

            await asyncio.sleep(config.POLL_INTERVAL)
    finally:
        await client.close()
        await db.close()


async def run_once() -> None:
    """Single execution: fetch SOC and set Ohme target regardless of plug state."""
    logger.info("Running in one-shot mode")
    load_persisted_target()
    await db.init()
    client = await ohme_client.make_client()
    try:
        try:
            await client.async_update_device_info()
        except Exception:
            logger.warning("Could not fetch device info", exc_info=True)
        await handle_plugin_event(client)
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
        asyncio.run(run_once())
    else:
        asyncio.run(run_loop())
