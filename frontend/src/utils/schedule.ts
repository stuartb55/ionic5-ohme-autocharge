import type { ChargeSlot } from '../api/types';

export interface TimelineSegment {
  startFrac: number; // 0..1 across the window
  widthFrac: number;
  slot: ChargeSlot;
}

export interface Timeline {
  startMs: number;
  endMs: number;
  segments: TimelineSegment[];
  hourTicks: { frac: number; label: string }[];
}

function floorToHour(ms: number): number {
  const d = new Date(ms);
  d.setMinutes(0, 0, 0);
  return d.getTime();
}
function ceilToHour(ms: number): number {
  const floored = floorToHour(ms);
  return floored === ms ? ms : floored + 3600_000;
}

/**
 * Project charge slots onto a single horizontal window spanning from the start
 * of the first slot to the end of the last (padded to whole hours). The gaps
 * between active segments are the paused / off-peak periods.
 */
export function buildTimeline(slots: ChargeSlot[], maxTicks = 7): Timeline | null {
  if (!slots.length) return null;

  const starts = slots.map((s) => new Date(s.start).getTime());
  const ends = slots.map((s) => new Date(s.end).getTime());
  let startMs = floorToHour(Math.min(...starts));
  let endMs = ceilToHour(Math.max(...ends));
  if (endMs <= startMs) endMs = startMs + 3600_000;

  const span = endMs - startMs;
  const segments: TimelineSegment[] = slots.map((slot) => {
    const s = new Date(slot.start).getTime();
    const e = new Date(slot.end).getTime();
    return {
      startFrac: (s - startMs) / span,
      widthFrac: Math.max(0, (e - s) / span),
      slot,
    };
  });

  const totalHours = span / 3600_000;
  const step = Math.max(1, Math.ceil(totalHours / maxTicks));
  const hourTicks: { frac: number; label: string }[] = [];
  for (let t = startMs; t <= endMs; t += step * 3600_000) {
    hourTicks.push({
      frac: (t - startMs) / span,
      label: new Date(t).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }),
    });
  }

  return { startMs, endMs, segments, hourTicks };
}
