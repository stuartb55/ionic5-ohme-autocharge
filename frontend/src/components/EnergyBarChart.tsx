import type { DailyStat } from '../api/types';
import { formatDateShort } from '../utils/format';
import { formatMetric, type ChartMetric } from '../utils/statistics';

interface Props {
  daily: DailyStat[];
  metric: ChartMetric;
  currency: string | null;
  /** Human-readable chart title, used for the accessible name. */
  title: string;
}

const METRIC_COLOR: Record<ChartMetric, string> = {
  energyKwh: 'var(--brand)',
  savings: 'var(--success)',
  cost: 'var(--warning)',
};

const W = 720;
const H = 200;
const PAD_BOTTOM = 24;
const PAD_TOP = 8;

export function EnergyBarChart({ daily, metric, currency, title }: Props) {
  if (!daily.length) {
    return <p className="empty">No charging history in this period yet.</p>;
  }

  const reported = daily.filter((day) => day.isComplete);
  const values = reported.map((d) => d[metric] ?? 0);
  const max = Math.max(...values, 0.0001);
  const peak = Math.max(...values);
  const n = daily.length;
  const slot = W / n;
  const barW = Math.min(48, slot * 0.6);
  const chartH = H - PAD_BOTTOM - PAD_TOP;
  const color = METRIC_COLOR[metric];

  // Average across reported days in the range (including reported zero days),
  // drawn as a dashed reference line. Missing buckets are never treated as zero.
  const total = values.reduce((sum, v) => sum + v, 0);
  const avg = reported.length ? total / reported.length : 0;
  const avgY = PAD_TOP + (chartH - (avg / max) * chartH);
  const showAvg = avg > 0;

  // Label density: avoid overlap when many days.
  const labelStep = Math.ceil(n / 12);

  return (
    <div className="barchart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${title} bar chart`}>
        {daily.map((d, i) => {
          const v = d[metric] ?? 0;
          const h = (v / max) * chartH;
          const x = i * slot + (slot - barW) / 2;
          const y = PAD_TOP + (chartH - h);
          // A cost peak is not a "best" day, so cost bars use equal emphasis.
          // Energy and savings retain a peak cue because the maximum is useful.
          const isPeak = metric !== 'cost' && v > 0 && v === peak;
          if (!d.isComplete) {
            return (
              <g key={d.date ?? i}>
                <rect
                  x={x}
                  y={PAD_TOP}
                  width={barW}
                  height={chartH}
                  rx={4}
                  fill="var(--surface-3)"
                  stroke="var(--border-strong)"
                  strokeDasharray="4 4"
                >
                  <title>{d.date ?? ''}: Not reported</title>
                </rect>
                {i % labelStep === 0 && (
                  <text className="axis" x={i * slot + slot / 2} y={H - 8} textAnchor="middle">
                    {formatDateShort(d.date)}
                  </text>
                )}
              </g>
            );
          }
          return (
            <g key={d.date ?? i}>
              <rect
                x={x}
                y={y}
                width={barW}
                height={Math.max(0, h)}
                rx={4}
                fill={color}
                fillOpacity={metric === 'cost' ? 0.78 : isPeak ? 1 : 0.55}
              >
                <title>
                  {d.date ?? ''}: {formatMetric(v, metric, currency)}
                </title>
              </rect>
              {i % labelStep === 0 && (
                <text className="axis" x={i * slot + slot / 2} y={H - 8} textAnchor="middle">
                  {formatDateShort(d.date)}
                </text>
              )}
            </g>
          );
        })}

        {showAvg && (
          <g className="avg-line">
            <line x1={0} x2={W} y1={avgY} y2={avgY} strokeDasharray="4 4" />
            <text className="avg-label" x={W - 4} y={Math.max(PAD_TOP + 9, avgY - 4)} textAnchor="end">
              avg {formatMetric(avg, metric, currency)}
            </text>
          </g>
        )}
      </svg>
      <details className="chart-data">
        <summary>View chart data</summary>
        <div className="chart-data-wrap">
          <table>
            <caption>{title}</caption>
            <thead>
              <tr><th scope="col">Date</th><th scope="col">Value</th></tr>
            </thead>
            <tbody>
              {daily.map((day, index) => (
                <tr key={day.date ?? index}>
                  <td>{formatDateShort(day.date)}</td>
                  <td>{day.isComplete ? formatMetric(day[metric] ?? 0, metric, currency) : 'Not reported'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
