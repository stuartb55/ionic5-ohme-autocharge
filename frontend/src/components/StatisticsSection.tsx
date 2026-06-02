import { useState } from 'react';
import type { StatisticsResponse } from '../api/types';
import { formatKwh, formatMoney } from '../utils/format';
import { EnergyBarChart } from './EnergyBarChart';

interface Props {
  stats: StatisticsResponse;
  days: number;
  onDaysChange: (days: number) => void;
}

const RANGES = [7, 30, 90];

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

export function StatisticsSection({ stats, days, onDaysChange }: Props) {
  const [metric, setMetric] = useState<'energyKwh' | 'savings'>('energyKwh');
  const { totals, currency } = stats;

  return (
    <section className="card" aria-labelledby="stats-heading">
      <header>
        <div>
          <p className="eyebrow">Performance</p>
          <h2 id="stats-heading">Statistics &amp; savings</h2>
        </div>
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
      </header>

      <div className="stat-cards">
        <StatCard label="Energy charged" value={formatKwh(totals.energyKwh)} />
        <StatCard
          label="Saved vs standard tariff"
          value={formatMoney(totals.savingsVsStandard, currency)}
          highlight
        />
        <StatCard label="Avg. price / kWh" value={formatMoney(totals.averageKwhPrice, currency)} />
        <StatCard label="CO₂ saved vs petrol" value={`${totals.carbonSavedKgVsGasCar} kg`} />
      </div>

      <header style={{ marginBottom: 'var(--space-4)' }}>
        <h2 style={{ fontSize: '0.92rem' }}>
          {metric === 'energyKwh' ? 'Daily energy' : 'Daily savings'}
        </h2>
        <div className="chart-toolbar" role="group" aria-label="Chart metric">
          <button type="button" aria-pressed={metric === 'energyKwh'} onClick={() => setMetric('energyKwh')}>
            Energy
          </button>
          <button type="button" aria-pressed={metric === 'savings'} onClick={() => setMetric('savings')}>
            Savings
          </button>
        </div>
      </header>

      <EnergyBarChart daily={stats.daily} metric={metric} currency={currency} />
    </section>
  );
}
