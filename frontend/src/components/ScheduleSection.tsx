import type { ScheduleResponse } from '../api/types';
import { useNow } from '../hooks/useNow';
import { formatDateShort, formatKwh, formatPower, formatTime, formatUntil } from '../utils/format';
import { ScheduleTimeline } from './ScheduleTimeline';

export function ScheduleSection({ schedule }: { schedule: ScheduleResponse }) {
  // Ohme does not promise slot ordering. Sort a copy so "starts" and "ready"
  // are accurate even if an upstream response arrives out of order.
  const slots = [...schedule.slots].sort(
    (left, right) => new Date(left.start).getTime() - new Date(right.start).getTime(),
  );
  const hasSlots = slots.length > 0;
  // Tick each minute so the "in 2h" countdown on the next slot stays current.
  const now = useNow(60_000);
  const totalEnergy = slots.reduce((total, slot) => total + slot.energy, 0);
  const firstStart = slots[0]?.start ?? null;
  const finalEnd = slots.reduce<string | null>((latest, slot) => {
    if (!latest || new Date(slot.end).getTime() > new Date(latest).getTime()) return slot.end;
    return latest;
  }, null);
  const homeDay = (value: string) => new Date(value).toLocaleDateString('en-CA', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    ...(schedule.timezone ? { timeZone: schedule.timezone } : {}),
  });
  const crossesDay = firstStart && finalEnd ? homeDay(firstStart) !== homeDay(finalEnd) : false;

  return (
    <section className="card schedule-card" aria-labelledby="schedule-heading">
      <header>
        <div>
          <p className="eyebrow">Smart schedule</p>
          <h2 id="schedule-heading">Tonight&apos;s plan</h2>
        </div>
        {schedule.nextSlotStart && (
          <span className="badge plugged_in">
            <span className="pip" aria-hidden="true" />
            Next charge {formatTime(schedule.nextSlotStart, schedule.timezone)}
            <span className="badge-rel"> · {formatUntil(schedule.nextSlotStart, new Date(now))}</span>
          </span>
        )}
      </header>

      {hasSlots ? (
        <>
          <div className="schedule-summary" aria-label="Charge plan summary">
            <div>
              <span>First charge</span>
              <strong>{firstStart ? formatTime(firstStart, schedule.timezone) : '—'}</strong>
            </div>
            <div>
              <span>Ready by</span>
              <strong>{finalEnd ? formatTime(finalEnd, schedule.timezone) : '—'}</strong>
              {crossesDay && finalEnd && <small>{formatDateShort(finalEnd, schedule.timezone)}</small>}
            </div>
            <div>
              <span>Energy</span>
              <strong>{formatKwh(totalEnergy)}</strong>
            </div>
          </div>
          <ScheduleTimeline slots={slots} now={new Date(now)} timeZone={schedule.timezone} />
          <details className="slot-details">
            <summary>{slots.length} charging {slots.length === 1 ? 'window' : 'windows'}</summary>
            <div className="slot-list">
              {slots.map((slot) => (
                <div className="slot-row" key={slot.start}>
                  <span className="time">
                    {formatTime(slot.start, schedule.timezone)} – {formatTime(slot.end, schedule.timezone)}
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
