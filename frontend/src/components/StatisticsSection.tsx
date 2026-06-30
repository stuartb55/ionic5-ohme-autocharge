import type { ReactNode } from 'react';
import { useMemo, useState } from 'react';
import type { StatisticsResponse } from '../api/types';
import {
  formatDateShort,
  formatKwh,
  formatMoney,
  formatPricePerKwh,
  formatPricePerMile,
} from '../utils/format';
import { deriveInsights, downloadDailyCsv, percentChange, type ChartMetric } from '../utils/statistics';
import { EnergyBarChart } from './EnergyBarChart';

/**
 * "▲ 12% / ▼ 8%" change vs the previous period. ``goodWhen`` colours the badge:
 * for savings up is good; for cost up is bad; energy is neutral. Hidden when
 * there's no prior value to compare against.
 */
function DeltaBadge({
  current,
  previous,
  goodWhen,
}: {
  current: number;
  previous: number;
  goodWhen: 'up' | 'down' | 'neutral';
}) {
  const pct = percentChange(current, previous);
  if (pct === null) return null;
  if (Math.abs(pct) < 0.5) return <span className="delta neutral">±0%</span>;
  const up = pct > 0;
  let tone = 'neutral';
  if (goodWhen !== 'neutral') {
    const good = (up && goodWhen === 'up') || (!up && goodWhen === 'down');
    tone = good ? 'good' : 'bad';
  }
  return (
    <span className={`delta ${tone}`} title="vs previous period">
      {up ? '▲' : '▼'} {Math.abs(pct).toFixed(0)}%
    </span>
  );
}

interface Props {
  stats: StatisticsResponse;
  days: number;
  onDaysChange: (days: number) => void;
}

const RANGES = [7, 30, 90];

const CHART_METRICS: { key: ChartMetric; label: string }[] = [
  { key: 'energyKwh', label: 'Energy' },
  { key: 'savings', label: 'Savings' },
  { key: 'cost', label: 'Cost' },
];

const CHART_TITLE: Record<ChartMetric, string> = {
  energyKwh: 'Daily energy',
  savings: 'Daily savings',
  cost: 'Daily cost',
};

function StatCard({
  label,
  value,
  highlight = false,
  delta,
}: {
  label: string;
  value: string;
  highlight?: boolean;
  delta?: ReactNode;
}) {
  return (
    <div className={`stat-card${highlight ? ' highlight' : ''}`}>
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {delta && <div className="stat-delta">{delta}</div>}
    </div>
  );
}

function Insight({ label, value, sub }: { label: string; value: string; sub?: ReactNode }) {
  return (
    <div className="insight">
      <span className="insight-label">{label}</span>
      <span className="insight-value">{value}</span>
      {sub && <span className="insight-sub">{sub}</span>}
    </div>
  );
}

export function StatisticsSection({ stats, days, onDaysChange }: Props) {
  const [metric, setMetric] = useState<ChartMetric>('energyKwh');
  const { totals, currency } = stats;
  const insights = useMemo(() => deriveInsights(stats), [stats]);
  const prev = stats.comparison?.previous;

  return (
    <section className="card" aria-labelledby="stats-heading">
      <header>
        <div>
          <p className="eyebrow">Performance</p>
          <h2 id="stats-heading">Statistics &amp; savings</h2>
        </div>
        <div className="stats-actions">
          <button
            type="button"
            className="ghost-button"
            onClick={() => downloadDailyCsv(stats)}
            disabled={!stats.daily.length}
          >
            Export CSV
          </button>
          <div className="chart-toolbar" role="group" aria-label="Time range">
            {RANGES.map((r) => (
              <button
                key={r}
                type="button"
                aria-pressed={days === r}
                onClick={() => onDaysChange(r)}
              >
                {r}d
              </button>
            ))}
          </div>
        </div>
      </header>

      <div className="stat-cards">
        <StatCard
          label="Energy charged"
          value={formatKwh(totals.energyKwh)}
          delta={prev && <DeltaBadge current={totals.energyKwh} previous={prev.energyKwh} goodWhen="neutral" />}
        />
        <StatCard
          label="Saved vs standard tariff"
          value={formatMoney(totals.savingsVsStandard, currency)}
          highlight
          delta={
            prev && (
              <DeltaBadge current={totals.savingsVsStandard} previous={prev.savingsVsStandard} goodWhen="up" />
            )
          }
        />
        <StatCard label="Avg. price / kWh" value={formatPricePerKwh(totals.averageKwhPrice, currency)} />
        <StatCard label="CO₂ saved vs petrol" value={`${totals.carbonSavedKgVsGasCar} kg`} />
      </div>

      <p className="eyebrow insights-eyebrow">Breakdowns</p>
      <div className="insights" aria-label="Derived insights">
        <Insight
          label="Charging days"
          value={`${insights.chargingDays}`}
          sub={`of ${insights.totalDays} days`}
        />
        <Insight label="Avg / charging day" value={formatKwh(insights.avgPerChargingDay)} />
        <Insight
          label="Best day"
          value={insights.bestDay ? formatKwh(insights.bestDay.energyKwh) : '—'}
          sub={insights.bestDay ? formatDateShort(insights.bestDay.date) : undefined}
        />
        {insights.efficiencyIsReal && (
          <Insight
            label="Efficiency"
            value={`${insights.milesPerKwh} mi/kWh`}
            sub={`over ${insights.milesDriven} mi`}
          />
        )}
        {insights.costPerMile != null && (
          <Insight
            label="Running cost"
            value={`${formatPricePerMile(insights.costPerMile, currency)} / mi`}
            sub={insights.milesDriven != null ? `over ${insights.milesDriven} mi` : undefined}
          />
        )}
        <Insight
          label="Est. range added"
          value={`${Math.round(insights.estimatedMiles)} mi`}
          sub={`@ ${insights.milesPerKwh} mi/kWh`}
        />
        <Insight
          label="Total cost"
          value={formatMoney(totals.costTotal, currency)}
          sub={prev && <DeltaBadge current={totals.costTotal} previous={prev.costTotal} goodWhen="down" />}
        />
      </div>

      <header className="chart-header">
        <h3 className="chart-title">{CHART_TITLE[metric]}</h3>
        <div className="chart-toolbar" role="group" aria-label="Chart metric">
          {CHART_METRICS.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              aria-pressed={metric === key}
              onClick={() => setMetric(key)}
            >
              {label}
            </button>
          ))}
        </div>
      </header>

      <EnergyBarChart
        daily={stats.daily}
        metric={metric}
        currency={currency}
        title={CHART_TITLE[metric]}
      />
    </section>
  );
}
