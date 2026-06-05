import type { DailyStat, StatisticsResponse } from '../api/types';
import { formatKwh, formatMoney } from './format';

/** The metrics the daily bar chart can plot. */
export type ChartMetric = 'energyKwh' | 'savings' | 'cost';

/**
 * Assumed real-world efficiency of the Hyundai IONIQ 5, in miles per kWh.
 * The official figure is optimistic; ~3.5 mi/kWh is a realistic mixed-driving
 * average and keeps the "range added" estimate honest rather than flattering.
 */
export const MILES_PER_KWH = 3.5;

export interface Insights {
  /** Days in the range on which any energy was charged. */
  chargingDays: number;
  /** Total days covered by the range. */
  totalDays: number;
  /** Mean kWh per day that actually had a charge (0 when none). */
  avgPerChargingDay: number;
  /** The single biggest charging day, or null if nothing was charged. */
  bestDay: DailyStat | null;
  /** Estimated driving range added across the whole range, in miles. */
  estimatedMiles: number;
}

/** Derive higher-level insights from the raw daily/total figures. */
export function deriveInsights(stats: StatisticsResponse): Insights {
  const daily = stats.daily;
  const active = daily.filter((d) => d.energyKwh > 0);
  const totalEnergy = stats.totals.energyKwh;

  const bestDay = daily.reduce<DailyStat | null>(
    (best, d) => (best === null || d.energyKwh > best.energyKwh ? d : best),
    null,
  );

  return {
    chargingDays: active.length,
    totalDays: daily.length,
    avgPerChargingDay: active.length ? totalEnergy / active.length : 0,
    bestDay: bestDay && bestDay.energyKwh > 0 ? bestDay : null,
    estimatedMiles: totalEnergy * MILES_PER_KWH,
  };
}

/** Format a chart value for the given metric, with units/currency. */
export function formatMetric(
  value: number,
  metric: ChartMetric,
  currency: string | null,
): string {
  return metric === 'energyKwh' ? formatKwh(value) : formatMoney(value, currency);
}

/** Build a CSV (header + one row per day) from the daily history. */
export function dailyToCsv(daily: DailyStat[]): string {
  const header = ['date', 'energyKwh', 'savings', 'cost'];
  const rows = daily.map((d) => [d.date ?? '', d.energyKwh, d.savings, d.cost].join(','));
  return [header.join(','), ...rows].join('\n');
}

/**
 * Trigger a browser download of the daily history as a CSV file. No-op in
 * environments without the relevant DOM/URL APIs (e.g. SSR).
 */
export function downloadDailyCsv(stats: StatisticsResponse): void {
  if (typeof document === 'undefined' || typeof URL.createObjectURL !== 'function') return;
  const blob = new Blob([dailyToCsv(stats.daily)], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `autocharge-stats-${stats.rangeDays}d.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
