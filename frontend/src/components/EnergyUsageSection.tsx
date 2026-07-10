import type { EnergyUsageResponse } from '../api/types';
import { useNow } from '../hooks/useNow';
import { formatKwh } from '../utils/format';

const W = 720;
const H = 200;
const PAD_BOTTOM = 24;
const PAD_TOP = 8;

/** Shift a YYYY-MM-DD date string by ``n`` days (UTC maths avoids DST drift). */
function shiftDate(iso: string, n: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

/** "Mon 1 Jun" label for a YYYY-MM-DD date. */
function formatDay(iso: string): string {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    timeZone: 'UTC',
  });
}

/** "00:30" label for a slot start ISO. */
function slotLabel(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

/**
 * Whole-house grid import for a day, split into the car-charging share and the
 * rest of the household, as a stacked half-hourly bar chart. Renders nothing
 * when the feature is unconfigured (no Octopus account / persistence off).
 */
export function EnergyUsageSection({
  data,
  onDateChange,
}: {
  data: EnergyUsageResponse;
  onDateChange: (date: string) => void;
}) {
  // Tick each minute so "yesterday" (the latest navigable day) stays correct
  // across a midnight boundary without an impure Date.now() in render.
  const now = useNow(60_000);
  if (!data.enabled || !data.date || !data.totals) return null;

  const date = data.date;
  // Octopus consumption lags ~a day, so yesterday is the most recent full day.
  const latest = shiftDate(new Date(now).toISOString().slice(0, 10), -1);
  const canGoNext = date < latest;

  const slots = data.slots;
  const values = slots.map((s) => s.importKwh ?? 0);
  const max = Math.max(...values, 0.0001);
  const n = slots.length;
  const slotW = n > 0 ? W / n : W;
  const barW = Math.min(20, slotW * 0.7);
  const chartH = H - PAD_BOTTOM - PAD_TOP;
  // Label every ~2 hours (4 half-hour slots), keeping the axis readable.
  const labelStep = 4;

  return (
    <section className="card energy-usage-card" aria-labelledby="energy-usage-heading">
      <header>
        <div>
          <p className="eyebrow">Energy</p>
          <h2 id="energy-usage-heading">House vs car</h2>
        </div>
        <div className="day-nav">
          <button
            type="button"
            className="ghost-button"
            onClick={() => onDateChange(shiftDate(date, -1))}
            aria-label="Previous day"
          >
            ‹
          </button>
          <span className="day-label">{formatDay(date)}</span>
          <button
            type="button"
            className="ghost-button"
            onClick={() => onDateChange(shiftDate(date, 1))}
            disabled={!canGoNext}
            aria-label="Next day"
          >
            ›
          </button>
        </div>
      </header>

      <dl className="energy-totals">
        <div>
          <dt>Total import</dt>
          <dd>{formatKwh(data.totals.importKwh)}</dd>
        </div>
        <div className="energy-car">
          <dt>Car</dt>
          <dd>{formatKwh(data.totals.carKwh)}</dd>
        </div>
        <div className="energy-house">
          <dt>Rest of house</dt>
          <dd>{formatKwh(data.totals.houseKwh)}</dd>
        </div>
        {data.totals.unattributedKwh > 0 && (
          <div className="energy-unattributed">
            <dt>Unattributed</dt>
            <dd>{formatKwh(data.totals.unattributedKwh)}</dd>
          </div>
        )}
      </dl>

      {n === 0 ? (
        <p className="empty">No consumption data for this day yet.</p>
      ) : (
        <div className="barchart">
          <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="House vs car usage bar chart">
            {slots.map((s, i) => {
              const imp = s.importKwh ?? 0;
              const car = s.carKwh ?? 0;
              const house = s.houseKwh ?? 0;
              const unattributed = s.unattributedKwh ?? 0;
              const x = i * slotW + (slotW - barW) / 2;
              const carH = (car / max) * chartH;
              const houseH = (house / max) * chartH;
              const unattributedH = (unattributed / max) * chartH;
              const carY = PAD_TOP + (chartH - carH);
              const houseY = carY - houseH;
              const unattributedY = houseY - unattributedH;
              return (
                <g key={s.start ?? i}>
                  {/* Rest-of-house stacked on top of the car portion. */}
                  <rect x={x} y={houseY} width={barW} height={Math.max(0, houseH)} rx={2}
                    fill="var(--success)" fillOpacity={0.7}>
                    <title>
                      {slotLabel(s.start)} · house {formatKwh(house)} · car {formatKwh(car)} · total {formatKwh(imp)}
                    </title>
                  </rect>
                  <rect x={x} y={unattributedY} width={barW} height={Math.max(0, unattributedH)} rx={2}
                    fill="var(--muted)" fillOpacity={0.7}>
                    <title>
                      {slotLabel(s.start)} · unattributed {formatKwh(unattributed)} · quality {s.quality}
                    </title>
                  </rect>
                  <rect x={x} y={carY} width={barW} height={Math.max(0, carH)} rx={2}
                    fill="var(--brand)">
                    <title>
                      {slotLabel(s.start)} · car {formatKwh(car)} · house {formatKwh(house)} · total {formatKwh(imp)}
                    </title>
                  </rect>
                  {i % labelStep === 0 && (
                    <text className="axis" x={i * slotW + slotW / 2} y={H - 8} textAnchor="middle">
                      {slotLabel(s.start)}
                    </text>
                  )}
                </g>
              );
            })}
          </svg>
          <div className="energy-legend">
            <span className="legend-item"><span className="swatch swatch-car" /> Car</span>
            <span className="legend-item"><span className="swatch swatch-house" /> Rest of house</span>
            {data.totals.unattributedKwh > 0 && (
              <span className="legend-item"><span className="swatch swatch-unattributed" /> Unattributed</span>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
