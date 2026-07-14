"""Exercise the persistence workflow against CI's real PostgreSQL service."""

import asyncio
import datetime
import os
from pathlib import Path
import sys
import uuid
from types import SimpleNamespace

# CI executes this file directly, so add the repository root just as pytest's
# configured ``pythonpath = .`` does for the unit suite.
sys.path.insert(0, str(Path(__file__).parents[2]))

import db
from state import StatusSnapshot


async def main() -> None:
    if os.getenv("CI_MIGRATION_TEST") != "1":
        raise SystemExit("Refusing to mutate a database without CI_MIGRATION_TEST=1")

    await db.init()
    assert db.is_available()

    now = datetime.datetime.now(datetime.timezone.utc)
    key = f"ci-{uuid.uuid4().hex}"
    session_id = await db.record_session(
        vehicle_name="CI EV",
        soc_percent=40,
        target_percent=80,
        topup_percent=40,
        action="configured",
        session_key=key,
        vehicle_id="ci-car",
        plugged_in_at=now,
    )
    duplicate_id = await db.record_session(
        vehicle_name="CI EV",
        soc_percent=41,
        target_percent=80,
        topup_percent=39,
        action="configured",
        session_key=key,
        vehicle_id="ci-car",
        plugged_in_at=now,
    )
    assert session_id is not None and duplicate_id == session_id

    await db.record_session_event(session_id, "ci_started", {"source": "integration"})
    await db.record_telemetry(
        StatusSnapshot(
            vehicle_name="CI EV",
            battery_percent=50,
            charger_status="charging",
            connected=True,
            charger_online=True,
            power_watts=7000,
            target_percent=80,
            session_energy_wh=3500,
        ),
        session_id=session_id,
    )
    telemetry = await db.get_session_telemetry(session_id)
    assert telemetry and telemetry[0]["socPercent"] == 50

    await db.complete_session(key, actual_energy_wh=7000, end_soc_percent=80)
    interval_end = now + datetime.timedelta(minutes=30)
    priced = SimpleNamespace(
        energy_wh=7000,
        cost_minor=70,
        coverage=1.0,
        intervals=[
            {
                "start": now,
                "end": interval_end,
                "energyWh": 7000,
                "costMinor": 70,
                "rateMinorPerKwh": 10,
                "currency": "GBP",
                "quality": "priced",
            }
        ],
    )
    await db.record_session_reconciliation(session_id, priced, counter_energy_wh=7000)
    await db.record_daily_stats(
        [
            {
                "date": now.date().isoformat(),
                "energyKwh": 7,
                "savings": 1.2,
                "cost": 0.7,
                "isComplete": True,
            }
        ],
        "GBP",
    )

    audit = await db.get_session_audit(session_id)
    assert audit is not None
    assert audit["session"]["actualEnergyWh"] == 7000
    assert audit["session"]["actualCostMinor"] == 70
    assert audit["intervals"][0]["energyWh"] == 7000

    report = await db.get_monthly_report_rows(
        now.replace(day=1, hour=0, minute=0, second=0, microsecond=0),
        (now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
         + datetime.timedelta(days=32)).replace(day=1),
    )
    assert report is not None
    assert any(row["id"] == session_id for row in report["sessions"])

    await db.close()
    assert not db.is_available()
    stop = asyncio.Event()
    reconnect = asyncio.create_task(db.reconnect_loop(stop))
    for _ in range(100):
        if db.is_available():
            break
        await asyncio.sleep(0.05)
    assert db.is_available()
    stop.set()
    await reconnect
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
