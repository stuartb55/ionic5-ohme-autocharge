import { describe, expect, it } from 'vitest';
import { formatKwh, formatMoney, formatPower, relativeTime, statusLabel } from './format';

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

describe('statusLabel', () => {
  it('maps enum values to friendly labels', () => {
    expect(statusLabel('charging')).toBe('Charging');
    expect(statusLabel('unplugged')).toBe('Unplugged');
    expect(statusLabel('pending_approval')).toBe('Awaiting approval');
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
