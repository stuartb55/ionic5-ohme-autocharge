import type { ScheduleResponse } from '../api/types';
import { useNow } from '../hooks/useNow';
import { formatDateShort, formatKwh, formatPower, formatTime, formatUntil } from '../utils/format';
import { ScheduleTimeline } from './ScheduleTimeline';

export function ScheduleSection({ schedule }: { schedule: ScheduleResponse }) {
  const hasSlots = schedule.slots.length > 0;
  // Tick each minute so the "in 2h" countdown on the next slot stays current.
  const now = useNow(60_000);
  const totalEnergy = schedule.slots.reduce((total, slot) => total + slot.energy, 0);
  const firstStart = schedule.slots[0]?.start ?? null;
  const finalEnd = schedule.slots[schedule.slots.length - 1]?.end ?? null;
  const crossesDay = firstStart && finalEnd
    ? new Date(firstStart).toDateString() !== new Date(finalEnd).toDateString()
    : false;

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
          <div className="schedule-summary" aria-label="Charge plan summary">
            <div>
              <span>Starts</span>
              <strong>{firstStart ? formatTime(firstStart) : '—'}</strong>
            </div>
            <div>
              <span>Ready</span>
              <strong>{finalEnd ? formatTime(finalEnd) : '—'}</strong>
              {crossesDay && finalEnd && <small>{formatDateShort(finalEnd)}</small>}
            </div>
            <div>
              <span>Planned</span>
              <strong>{formatKwh(totalEnergy)}</strong>
            </div>
          </div>
          <ScheduleTimeline slots={schedule.slots} now={new Date(now)} />
          <details className="slot-details">
            <summary>{schedule.slots.length} charging {schedule.slots.length === 1 ? 'window' : 'windows'}</summary>
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
          </details>
        </>
      ) : (
        <p className="empty">
          {schedule.connected
            ? 'Connected and waiting for Ohme to allocate the cheapest charging windows.'
            : 'Plug in the vehicle and Ohme will build an off-peak charge plan.'}
        </p>
      )}
    </section>
  );
}
