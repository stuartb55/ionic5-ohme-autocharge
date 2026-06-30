import { describe, expect, it } from 'vitest';
import type { SessionTelemetryPoint } from '../api/types';
import { buildChargeCurve } from './chargeCurve';

const dims = { width: 320, height: 120, padX: 8, padY: 12 };

function pt(at: string, soc: number | null, watts: number | null): SessionTelemetryPoint {
  return { at, socPercent: soc, powerWatts: watts, sessionEnergyKwh: null };
}

describe('buildChargeCurve', () => {
  it('returns null with fewer than two timestamped points', () => {
    expect(buildChargeCurve([], dims)).toBeNull();
    expect(buildChargeCurve([pt('2026-06-01T20:00:00Z', 50, 7000)], dims)).toBeNull();
    // A second point with no timestamp doesn't count.
    expect(
      buildChargeCurve(
        [pt('2026-06-01T20:00:00Z', 50, 7000), { at: null, socPercent: 60, powerWatts: 7000, sessionEnergyKwh: null }],
        dims,
      ),
    ).toBeNull();
  });

  it('summarises SOC span and peak power', () => {
    const curve = buildChargeCurve(
      [
        pt('2026-06-01T20:00:00Z', 40, 7000),
        pt('2026-06-01T20:30:00Z', 55, 7400),
        pt('2026-06-01T21:00:00Z', 70, 3000),
      ],
      dims,
    )!;
    expect(curve.socStart).toBe(40);
    expect(curve.socEnd).toBe(70);
    expect(curve.peakPowerKw).toBeCloseTo(7.4);
    expect(curve.socLine.split(' ')).toHaveLength(3);
    expect(curve.powerLine.split(' ')).toHaveLength(3);
  });

  it('places SOC on a fixed 0-100 scale (higher SOC sits higher)', () => {
    const curve = buildChargeCurve(
      [pt('2026-06-01T20:00:00Z', 20, 7000), pt('2026-06-01T21:00:00Z', 80, 7000)],
      dims,
    )!;
    const [, firstY] = curve.socLine.split(' ')[0]!.split(',').map(Number);
    const [, lastY] = curve.socLine.split(' ')[1]!.split(',').map(Number);
    // SVG y grows downward, so the higher SOC (80%) must have the smaller y.
    expect(lastY).toBeLessThan(firstY!);
  });

  it('skips missing series points but keeps the line for the other', () => {
    const curve = buildChargeCurve(
      [
        pt('2026-06-01T20:00:00Z', 40, null),
        pt('2026-06-01T20:30:00Z', null, 7000),
        pt('2026-06-01T21:00:00Z', 60, 7000),
      ],
      dims,
    )!;
    expect(curve.socLine.split(' ')).toHaveLength(2); // two SOC readings
    expect(curve.powerLine.split(' ')).toHaveLength(2); // two power readings
  });
});
