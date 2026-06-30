import { describe, expect, it } from 'vitest';
import {
  formatFinishTime,
  formatKwh,
  formatMiles,
  formatMoney,
  formatPower,
  formatPricePerKwh,
  formatPricePerMile,
  relativeTime,
  statusLabel,
} from './format';

describe('formatFinishTime', () => {
  // Exact output is locale-dependent (12h vs 24h clock), so match loosely.
  it('shows just the time when the finish is today', () => {
    const now = new Date('2026-06-02T00:08:00');
    const out = formatFinishTime('2026-06-02T05:00:00', now);
    expect(out).toContain('05:00');
    expect(out).not.toMatch(/^Tue/);
  });

  it('prefixes the weekday when the finish is another day', () => {
    const now = new Date('2026-06-02T23:30:00');
    // 2026-06-03 is a Wednesday.
    expect(formatFinishTime('2026-06-03T06:30:00', now)).toMatch(/^Wed.*06:30/);
  });
});

describe('formatPower', () => {
  it('converts watts to kW', () => {
    expect(formatPower(7400)).toBe('7.4 kW');
    expect(formatPower(0)).toBe('0 kW');
    expect(formatPower(-5)).toBe('0 kW');
  });
});

describe('formatKwh', () => {
  it('shows one decimal under 100 and none above', () => {
    expect(formatKwh(4.5)).toBe('4.5 kWh');
    expect(formatKwh(120.4)).toBe('120 kWh');
  });
});

describe('formatMoney', () => {
  it('formats a known currency', () => {
    expect(formatMoney(8.4, 'GBP')).toContain('8.40');
  });
  it('falls back gracefully for null currency', () => {
    expect(formatMoney(8.4, null)).toBe('8.40');
  });
});

describe('formatPricePerKwh', () => {
  it('shows GBP per-kWh prices in pence', () => {
    expect(formatPricePerKwh(0.125, 'GBP')).toBe('12.5p');
    expect(formatPricePerKwh(0.3, 'GBP')).toBe('30.0p');
  });
  it('falls back to money formatting when currency is null', () => {
    expect(formatPricePerKwh(0.125, null)).toBe('0.13');
  });
});

describe('formatPricePerMile', () => {
  it('shows GBP per-mile costs in pence', () => {
    expect(formatPricePerMile(0.083, 'GBP')).toBe('8.3p');
    expect(formatPricePerMile(0.25, 'GBP')).toBe('25.0p');
  });
  it('falls back to money formatting when currency is null', () => {
    expect(formatPricePerMile(0.083, null)).toBe('0.08');
  });
});

describe('statusLabel', () => {
  it('maps enum values to friendly labels', () => {
    expect(statusLabel('charging')).toBe('Charging');
    expect(statusLabel('unplugged')).toBe('Unplugged');
    expect(statusLabel('pending_approval')).toBe('Awaiting approval');
  });
});

describe('formatMiles', () => {
  it('renders whole miles', () => {
    expect(formatMiles(180)).toBe('180 mi');
    expect(formatMiles(180.6)).toBe('181 mi');
  });
  it('renders empty for null/negative', () => {
    expect(formatMiles(null)).toBe('');
    expect(formatMiles(undefined)).toBe('');
    expect(formatMiles(-5)).toBe('');
  });
});

describe('relativeTime', () => {
  const base = new Date('2026-06-02T12:00:00Z');
  it('handles null', () => {
    expect(relativeTime(null, base)).toBe('never');
  });
  it('formats seconds and minutes', () => {
    expect(relativeTime(new Date('2026-06-02T11:59:50Z'), base)).toBe('10s ago');
    expect(relativeTime(new Date('2026-06-02T11:57:00Z'), base)).toBe('3m ago');
  });
});
