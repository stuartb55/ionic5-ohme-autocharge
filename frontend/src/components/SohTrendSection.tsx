import type { SohHistoryResponse } from '../api/types';
import { formatDateShort } from '../utils/format';

const W = 320;
const H = 64;
const PAD_X = 6;
const PAD_Y = 8;

/**
 * Battery state-of-health trend from the Postgres history. SoH is captured once
 * per plug-in; this surfaces the degradation curve on the dashboard so you don't
 * need Grafana to see it. Renders nothing when persistence is disabled or there
 * are no readings yet — the single current value still shows on the status ring.
 */
export function SohTrendSection({ data }: { data: SohHistoryResponse }) {
  if (!data.enabled || data.history.length === 0) return null;

  // Non-null: the empty-history case returned above, so both ends exist.
  const points = data.history;
  const first = points[0]!;
  const last = points[points.length - 1]!;
  const current = last.sohPercent;
  const delta = current - first.sohPercent;

  // A line needs at least two distinct readings; until then just show the value.
  const hasTrend = points.length >= 2;

  const values = points.map((p) => p.sohPercent);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1; // guard /0 (only reachable when hasTrend is false)
  const chartW = W - PAD_X * 2;
  const chartH = H - PAD_Y * 2;

  const coords = points.map((p, i) => {
    const x = PAD_X + (points.length === 1 ? chartW / 2 : (i / (points.length - 1)) * chartW);
    const y = PAD_Y + (1 - (p.sohPercent - min) / span) * chartH;
    return { x, y, p };
  });
  const polyline = coords.map((c) => `${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(' ');

  const deltaArrow = delta < 0 ? '▼' : delta > 0 ? '▲' : '±';
  const deltaLabel = `${deltaArrow} ${Math.abs(delta)}% since ${formatDateShort(first.date)}`;

  return (
    <section className="card soh-trend" aria-labelledby="soh-heading">
      <header>
        <div>
          <p className="eyebrow">Battery</p>
          <h2 id="soh-heading">Battery health</h2>
        </div>
      </header>

      <div className="soh-summary">
        <span className="soh-current">{current}%</span>
        {hasTrend && (
          <span className="soh-delta" title="Change across recorded readings">
            {deltaLabel}
          </span>
        )}
      </div>

      {hasTrend ? (
        <div className="soh-spark">
          <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Battery health trend, now ${current}%`}>
            <polyline
              points={polyline}
              fill="none"
              stroke="var(--brand)"
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            {coords.map((c, i) => (
              <circle key={c.p.date ?? i} cx={c.x} cy={c.y} r={i === coords.length - 1 ? 3.5 : 2} fill="var(--brand)">
                <title>
                  {formatDateShort(c.p.date)}: {c.p.sohPercent}%
                </title>
              </circle>
            ))}
          </svg>
          <div className="soh-axis" aria-hidden="true">
            <span>{formatDateShort(first.date)}</span>
            <span>{formatDateShort(last.date)}</span>
          </div>
        </div>
      ) : (
        <p className="empty">No change recorded yet — the trend appears after a few charges.</p>
      )}
    </section>
  );
}
