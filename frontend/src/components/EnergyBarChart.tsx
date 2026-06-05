import type { DailyStat } from '../api/types';
import { formatDateShort, formatMoney } from '../utils/format';

export type ChartMetric = 'energyKwh' | 'savings' | 'cost';

interface Props {
  daily: DailyStat[];
  metric: ChartMetric;
  currency: string | null;
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

export function EnergyBarChart({ daily, metric, currency }: Props) {
  if (!daily.length) {
    return <p className="empty">No charging history in this period yet.</p>;
  }

  const values = daily.map((d) => d[metric] ?? 0);
  const max = Math.max(...values, 0.0001);
  const n = daily.length;
  const slot = W / n;
  const barW = Math.min(48, slot * 0.6);
  const chartH = H - PAD_BOTTOM - PAD_TOP;
  const color = METRIC_COLOR[metric];
  const formatValue = (v: number) =>
    metric === 'energyKwh' ? `${v} kWh` : formatMoney(v, currency);

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
          return (
            <g key={i}>
              <rect x={x} y={y} width={barW} height={Math.max(0, h)} rx={4} fill={color}>
                <title>
                  {d.date ?? ''}: {formatValue(v)}
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
      </svg>
    </div>
  );
}
