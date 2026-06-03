import { describe, expect, it } from 'vitest';
import { buildTimeline } from './schedule';
import type { ChargeSlot } from '../api/types';

const slots: ChargeSlot[] = [
  { start: '2026-06-02T01:00:00Z', end: '2026-06-02T03:00:00Z', power: 7.4, energy: 14.8 },
  { start: '2026-06-02T04:00:00Z', end: '2026-06-02T05:00:00Z', power: 7.4, energy: 7.4 },
];

describe('buildTimeline', () => {
  it('returns null with no slots', () => {
    expect(buildTimeline([])).toBeNull();
  });

  it('spans from first slot start to last slot end', () => {
    const tl = buildTimeline(slots)!;
    expect(tl.startMs).toBe(new Date('2026-06-02T01:00:00Z').getTime());
    expect(tl.endMs).toBe(new Date('2026-06-02T05:00:00Z').getTime());
  });

  it('produces a segment per slot with fractional positions', () => {
    const tl = buildTimeline(slots)!;
    expect(tl.segments).toHaveLength(2);
    // First slot starts at the window start.
    expect(tl.segments[0].startFrac).toBeCloseTo(0, 5);
    // 2h of a 4h window = half width.
    expect(tl.segments[0].widthFrac).toBeCloseTo(0.5, 5);
    // Second slot starts 3h into the 4h window.
    expect(tl.segments[1].startFrac).toBeCloseTo(0.75, 5);
  });

  it('emits hour ticks within the window', () => {
    const tl = buildTimeline(slots)!;
    expect(tl.hourTicks.length).toBeGreaterThan(0);
    expect(tl.hourTicks[0].frac).toBeCloseTo(0, 5);
  });
});
