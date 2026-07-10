import { describe, expect, it } from 'vitest';
import type { StatisticsResponse } from '../api/types';
import { statisticsFixture } from '../test/fixtures';
import {
  MILES_PER_KWH,
  dailyToCsv,
  deriveInsights,
  formatMetric,
  percentChange,
} from './statistics';

const empty: StatisticsResponse = {
  rangeDays: 7,
  stale: false,
  currency: 'GBP',
  window: statisticsFixture.window,
  scope: statisticsFixture.scope,
  totals: {
    energyKwh: 0,
    savingsVsStandard: 0,
    costTotal: 0,
    averageKwhPrice: 0,
    carbonSavedKgVsGasCar: 0,
  },
  daily: [
    { date: '2026-05-27', energyKwh: 0, savings: 0, cost: 0, isComplete: true },
    { date: '2026-05-28', energyKwh: 0, savings: 0, cost: 0, isComplete: true },
  ],
  efficiency: null,
  runningCost: null,
  comparison: null,
  metadata: statisticsFixture.metadata,
};

describe('deriveInsights', () => {
  it('counts charging days and picks the best day', () => {
    const insights = deriveInsights(statisticsFixture);
    // fixture has 5 of 7 days with energy > 0
    expect(insights.chargingDays).toBe(5);
    expect(insights.totalDays).toBe(7);
    expect(insights.bestDay?.date).toBe('2026-05-30'); // 12.1 kWh
    expect(insights.avgPerChargingDay).toBeCloseTo(42 / 5, 5);
    expect(insights.estimatedMiles).toBeCloseTo(42 * MILES_PER_KWH, 5);
  });

  it('handles a range with no charging gracefully', () => {
    const insights = deriveInsights(empty);
    expect(insights.chargingDays).toBe(0);
    expect(insights.avgPerChargingDay).toBe(0);
    expect(insights.bestDay).toBeNull();
    expect(insights.estimatedMiles).toBe(0);
  });

  it('falls back to the assumed efficiency when none is measured', () => {
    const insights = deriveInsights(statisticsFixture); // efficiency: null
    expect(insights.efficiencyIsReal).toBe(false);
    expect(insights.milesPerKwh).toBe(MILES_PER_KWH);
    expect(insights.milesDriven).toBeNull();
    expect(insights.costPerMile).toBeNull(); // runningCost: null in the fixture
  });

  it('surfaces running cost (and miles) when present without efficiency', () => {
    const withCost: StatisticsResponse = {
      ...statisticsFixture,
      runningCost: { costPerMile: 0.083, milesDriven: 210, costTotal: 17.4, currency: 'GBP', intervalCount: 4, scope: 'matched_actual_home_charging' },
    };
    const insights = deriveInsights(withCost);
    expect(insights.costPerMile).toBe(0.083);
    // milesDriven falls back to runningCost's when efficiency is null.
    expect(insights.milesDriven).toBe(210);
  });

  it('does not apply a scoped measured efficiency to the account-wide total', () => {
    const withEff: StatisticsResponse = {
      ...statisticsFixture,
      efficiency: { milesDriven: 168, milesPerKwh: 4, energyKwh: 42, intervalCount: 3, vehicleId: 'car-1', from: null, to: null, scope: 'matched_home_charging' },
    };
    const insights = deriveInsights(withEff);
    expect(insights.efficiencyIsReal).toBe(true);
    expect(insights.milesPerKwh).toBe(4);
    expect(insights.milesDriven).toBe(168);
    expect(insights.estimatedMiles).toBe(168);
  });
});

describe('percentChange', () => {
  it('computes the change relative to the previous value', () => {
    expect(percentChange(110, 100)).toBeCloseTo(10, 5);
    expect(percentChange(80, 100)).toBeCloseTo(-20, 5);
  });
  it('returns null when there is no prior value', () => {
    expect(percentChange(50, 0)).toBeNull();
  });
});

describe('formatMetric', () => {
  it('formats energy in kWh and money in currency', () => {
    expect(formatMetric(6.2, 'energyKwh', 'GBP')).toBe('6.2 kWh');
    expect(formatMetric(1.1, 'savings', 'GBP')).toContain('1.10');
    expect(formatMetric(0.8, 'cost', null)).toBe('0.80');
  });
});

describe('dailyToCsv', () => {
  it('emits a header row and one row per day', () => {
    const csv = dailyToCsv(statisticsFixture.daily);
    const lines = csv.split('\n');
    expect(lines[0]).toBe('date,energyKwh,savings,cost');
    expect(lines).toHaveLength(statisticsFixture.daily.length + 1);
    expect(lines[1]).toBe('2026-05-27,6.2,1.1,0.8');
  });

  it('renders a null date as an empty cell', () => {
    const csv = dailyToCsv([
      { date: null, energyKwh: 1, savings: 0, cost: 0, isComplete: true },
    ]);
    expect(csv.split('\n')[1]).toBe(',1,0,0');
  });
});
