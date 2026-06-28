import type { ScheduleResponse } from '../api/types';
import { useNow } from '../hooks/useNow';
import { formatKwh, formatPower, formatTime, formatUntil } from '../utils/format';
import { ScheduleTimeline } from './ScheduleTimeline';

export function ScheduleSection({ schedule }: { schedule: ScheduleResponse }) {
  const hasSlots = schedule.slots.length > 0;
  // Tick each minute so the "in 2h" countdown on the next slot stays current.
  const now = useNow(60_000);

  return (
    <section className="card" aria-labelledby="schedule-heading">
      <header>
        <div>
          <p className="eyebrow">Charge plan</p>
          <h2 id="schedule-heading">Schedule</h2>
        </div>
        {schedule.nextSlotStart && (
          <span className="badge plugged_in">
            <span className="pip" aria-hidden="true" />
            Next slot {formatTime(schedule.nextSlotStart)}
            <span className="badge-rel"> · {formatUntil(schedule.nextSlotStart, new Date(now))}</span>
          </span>
        )}
      </header>

      {hasSlots ? (
        <>
          <ScheduleTimeline slots={schedule.slots} />
          <div className="slot-list">
            {schedule.slots.map((slot) => (
              <div className="slot-row" key={slot.start}>
                <span className="time">
                  {formatTime(slot.start)} – {formatTime(slot.end)}
                </span>
                <span className="detail">
                  {formatKwh(slot.energy)} · {formatPower(slot.power * 1000)}
                </span>
              </div>
            ))}
          </div>
        </>
      ) : (
        <p className="empty">
          {schedule.connected
            ? 'No charging slots allocated yet — Ohme is calculating the schedule.'
            : 'No active schedule. Plug in the vehicle to allocate off-peak charging slots.'}
        </p>
      )}
    </section>
  );
}
