import type { ReactNode } from 'react';
import { useMemo, useState } from 'react';
import type { StatisticsResponse } from '../api/types';
import { api } from '../api/client';
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

function shiftDate(iso: string, days: number): string {
  const value = new Date(`${iso}T00:00:00Z`);
  value.setUTCDate(value.getUTCDate() + days);
  return value.toISOString().slice(0, 10);
}

/** Keep missing upstream days in their real position without treating them as zero. */
function chartWindow(stats: StatisticsResponse) {
  const byDate = new Map(stats.daily.flatMap((day) => day.date ? [[day.date, day]] : []));
  const firstDate = stats.window.from.slice(0, 10);
  return Array.from({ length: stats.rangeDays }, (_, index) => {
    const date = shiftDate(firstDate, index);
    return byDate.get(date) ?? {
      date,
      energyKwh: 0,
      savings: 0,
      cost: 0,
      isComplete: false,
    };
  });
}

export function StatisticsSection({ stats, days, onDaysChange }: Props) {
  const [metric, setMetric] = useState<ChartMetric>('energyKwh');
  const { totals, currency } = stats;
  const insights = useMemo(() => deriveInsights(stats), [stats]);
  const chartDaily = useMemo(() => chartWindow(stats), [stats]);
  const prev = stats.comparison?.previous;
  const reportedDays = Number(stats.metadata.daily.coverage.completeDays ?? stats.daily.length);
  const missingDays = Math.max(0, stats.rangeDays - reportedDays);
  const dailyIncomplete = stats.metadata.daily.quality !== 'complete';
  const defaultReportMonth = (() => {
    const [year, month] = stats.window.completeThrough.slice(0, 10).split('-').map(Number);
    const previous = new Date(Date.UTC(year!, month! - 2, 1));
    return `${previous.getUTCFullYear()}-${String(previous.getUTCMonth() + 1).padStart(2, '0')}`;
  })();
  const [reportMonth, setReportMonth] = useState(defaultReportMonth);

  return (
    <section className="card" aria-labelledby="stats-heading">
      <header>
        <div>
          <p className="eyebrow">Last {stats.rangeDays} complete days</p>
          <h2 id="stats-heading">Statistics &amp; savings</h2>
          <p className="card-description">Your Ohme account totals, compared with the previous {stats.rangeDays} days.</p>
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

      <details className="monthly-report">
        <summary>Monthly report</summary>
        <div className="monthly-report-controls">
          <label>
            <span>Calendar month</span>
            <input
              type="month"
              value={reportMonth}
              onChange={(event) => setReportMonth(event.target.value)}
              aria-label="Monthly report month"
            />
          </label>
          <a className="ghost-button" href={api.monthlyReportUrl(reportMonth, 'csv')} download>
            Download CSV
          </a>
          <a className="ghost-button" href={api.monthlyReportUrl(reportMonth, 'json')} download>
            JSON
          </a>
        </div>
        <p className="field-hint">
          Account daily totals and measured home-session evidence, with explicit coverage and quality.
        </p>
      </details>

      <div className="stats-context" aria-label="Statistics coverage">
        <span>
          {reportedDays > 0 ? `${reportedDays} of ${stats.rangeDays} daily breakdowns reported` : 'No daily breakdowns reported'}
          {' · '}{stats.window.timezone}
        </span>
        <details>
          <summary>Sources &amp; methods</summary>
          <ul>
            <li>Account totals: Ohme charge summary for complete local days.</li>
            {stats.efficiency ? (
              <li>
                Efficiency: same-vehicle distance across {stats.efficiency.intervalCount}{' '}
                complete local charge-to-next-plug-in intervals.
              </li>
            ) : (
              <li>
                Efficiency unavailable: requires complete local charge-to-next-plug-in
                intervals with charged energy and two odometer readings.
              </li>
            )}
            {stats.runningCost ? (
              <li>
                Running cost: reconciled tariff cost across {stats.runningCost.intervalCount}{' '}
                complete local charge-to-next-plug-in intervals.
              </li>
            ) : (
              <li>
                Running cost unavailable: requires a complete local charge-to-next-plug-in
                interval with fully reconciled tariff pricing.
              </li>
            )}
          </ul>
        </details>
      </div>
      {stats.stale && (
        <p className="stats-stale" role="status">
          Ohme is temporarily unavailable. Showing the last validated statistics snapshot.
        </p>
      )}
      {dailyIncomplete && missingDays > 0 && (
        <p className="stats-stale" role="status">
          Ohme did not supply {missingDays} daily {missingDays === 1 ? 'breakdown' : 'breakdowns'}.
          Missing days are marked as not reported, not counted as zero usage.
        </p>
      )}

      <div className="stat-cards">
        <StatCard
          label="Total cost"
          value={formatMoney(totals.costTotal, currency)}
          delta={prev && <DeltaBadge current={totals.costTotal} previous={prev.costTotal} goodWhen="down" />}
        />
        <StatCard
          label="Saved vs standard"
          value={formatMoney(totals.savingsVsStandard, currency)}
          highlight
          delta={
            prev && (
              <DeltaBadge current={totals.savingsVsStandard} previous={prev.savingsVsStandard} goodWhen="up" />
            )
          }
        />
        <StatCard
          label="Energy charged"
          value={formatKwh(totals.energyKwh)}
          delta={prev && <DeltaBadge current={totals.energyKwh} previous={prev.energyKwh} goodWhen="neutral" />}
        />
        <StatCard label="Average price / kWh" value={formatPricePerKwh(totals.averageKwhPrice, currency)} />
      </div>

      <details className="analytics-details">
        <summary>More performance insights</summary>
        <div className="secondary-stat-cards">
          <StatCard label="CO₂ saved vs petrol" value={`${totals.carbonSavedKgVsGasCar} kg`} />
        </div>
        <p className="eyebrow insights-eyebrow">Breakdowns</p>
        <div className="insights" aria-label="Derived insights">
          <Insight
            label="Charging days"
            value={`${insights.chargingDays}`}
            sub={dailyIncomplete
              ? `among ${insights.totalDays} reported ${insights.totalDays === 1 ? 'day' : 'days'}`
              : `of ${insights.totalDays} days`}
          />
          <Insight
            label={dailyIncomplete ? 'Avg / reported charge day' : 'Avg / charging day'}
            value={formatKwh(insights.avgPerChargingDay)}
          />
          <Insight
            label="Best day"
            value={insights.bestDay ? formatKwh(insights.bestDay.energyKwh) : '—'}
            sub={insights.bestDay ? formatDateShort(insights.bestDay.date) : undefined}
          />
          {insights.efficiencyIsReal && (
            <Insight
              label="Home-energy efficiency"
              value={`${insights.milesPerKwh} mi/kWh`}
              sub={`${insights.matchedEnergyKwh} kWh across ${insights.efficiencyIntervalCount} matched intervals`}
            />
          )}
          {insights.costPerMile != null && (
            <Insight
              label="Actual home running cost"
              value={`${formatPricePerMile(insights.costPerMile, currency)} / mi`}
              sub={`${insights.costIntervalCount} matched intervals`}
            />
          )}
          <Insight
            label={insights.efficiencyIsReal ? 'Matched distance' : 'Est. range added'}
            value={`${Math.round(insights.estimatedMiles)} mi`}
            sub={insights.efficiencyIsReal ? 'after matched home charges' : `@ ${insights.milesPerKwh} mi/kWh assumed`}
          />
        </div>
      </details>

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
        daily={chartDaily}
        metric={metric}
        currency={currency}
        title={CHART_TITLE[metric]}
      />
    </section>
  );
}
