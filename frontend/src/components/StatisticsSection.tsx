import { useState } from 'react';
import type { StatisticsResponse } from '../api/types';
import { formatDateShort, formatKwh, formatMoney, formatPricePerKwh } from '../utils/format';
import { deriveInsights, downloadDailyCsv, type ChartMetric } from '../utils/statistics';
import { EnergyBarChart } from './EnergyBarChart';

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
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div className={`stat-card${highlight ? ' highlight' : ''}`}>
      <div className="label">{label}</div>
      <div className="value">{value}</div>
    </div>
  );
}

function Insight({ label, value, sub }: { label: string; value: string; sub?: string }) {
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
  const insights = deriveInsights(stats);

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
        <StatCard label="Energy charged" value={formatKwh(totals.energyKwh)} />
        <StatCard
          label="Saved vs standard tariff"
          value={formatMoney(totals.savingsVsStandard, currency)}
          highlight
        />
        <StatCard label="Avg. price / kWh" value={formatPricePerKwh(totals.averageKwhPrice, currency)} />
        <StatCard label="CO₂ saved vs petrol" value={`${totals.carbonSavedKgVsGasCar} kg`} />
      </div>

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
        <Insight
          label="Est. range added"
          value={`${Math.round(insights.estimatedMiles)} mi`}
          sub="@ 3.5 mi/kWh"
        />
        <Insight label="Total cost" value={formatMoney(totals.costTotal, currency)} />
      </div>

      <header style={{ marginBottom: 'var(--space-4)' }}>
        <h2 style={{ fontSize: '0.92rem' }}>{CHART_TITLE[metric]}</h2>
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

      <EnergyBarChart daily={stats.daily} metric={metric} currency={currency} />
    </section>
  );
}
