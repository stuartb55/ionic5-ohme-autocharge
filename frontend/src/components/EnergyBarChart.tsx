import type { DailyStat } from '../api/types';
import { formatDateShort } from '../utils/format';
import { formatMetric, type ChartMetric } from '../utils/statistics';

interface Props {
  daily: DailyStat[];
  metric: ChartMetric;
  currency: string | null;
}

const W = 720;
const H = 200;
const PAD_BOTTOM = 24;
const PAD_TOP = 8;

const METRIC_COLOR: Record<ChartMetric, string> = {
  energyKwh: 'var(--brand)',
  savings: 'var(--success)',
  cost: 'var(--accent)',
};

export function EnergyBarChart({ daily, metric, currency }: Props) {
  if (!daily.length) {
    return <p className="empty">No charging history in this period yet.</p>;
  }

  const values = daily.map((d) => d[metric] ?? 0);
  const max = Math.max(...values, 0.0001);
  const peak = Math.max(...values);
  const n = daily.length;
  const slot = W / n;
  const barW = Math.min(48, slot * 0.6);
  const chartH = H - PAD_BOTTOM - PAD_TOP;
  const color = METRIC_COLOR[metric];

  // Average across all days in the range (including zero days), drawn as a
  // dashed reference line so peaks and troughs read against a baseline.
  const total = values.reduce((sum, v) => sum + v, 0);
  const avg = total / n;
  const avgY = PAD_TOP + (chartH - (avg / max) * chartH);
  const showAvg = avg > 0;

  // Label density: avoid overlap when many days.
  const labelStep = Math.ceil(n / 12);

  return (
    <div className="barchart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Daily ${metric} bar chart`}>
        {daily.map((d, i) => {
          const v = d[metric] ?? 0;
          const h = (v / max) * chartH;
          const x = i * slot + (slot - barW) / 2;
          const y = PAD_TOP + (chartH - h);
          // Dim every bar except the peak, so the best day stands out.
          const isPeak = v > 0 && v === peak;
          return (
            <g key={i}>
              <rect
                x={x}
                y={y}
                width={barW}
                height={Math.max(0, h)}
                rx={4}
                fill={color}
                fillOpacity={isPeak ? 1 : 0.55}
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
    </div>
  );
}
