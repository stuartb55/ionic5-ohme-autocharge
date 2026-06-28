import type { ChargeSlot } from '../api/types';
import { buildTimeline } from '../utils/schedule';

const W = 720;
const H = 64;
const TRACK_Y = 16;
const TRACK_H = 28;

export function ScheduleTimeline({ slots }: { slots: ChargeSlot[] }) {
  const timeline = buildTimeline(slots);
  if (!timeline) return null;

  return (
    <div className="timeline">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Charging schedule timeline">
        {/* idle track */}
        <rect x={0} y={TRACK_Y} width={W} height={TRACK_H} rx={8} fill="var(--charge-track)" />
        {/* active charging segments */}
        {timeline.segments.map((seg) => (
          <rect
            key={seg.slot.start}
            x={seg.startFrac * W}
            y={TRACK_Y}
            width={Math.max(2, seg.widthFrac * W)}
            height={TRACK_H}
            rx={8}
            fill="var(--brand)"
          >
            <title>
              {new Date(seg.slot.start).toLocaleTimeString()} – {new Date(seg.slot.end).toLocaleTimeString()} ·{' '}
              {seg.slot.energy} kWh
            </title>
          </rect>
        ))}
        {/* hour ticks */}
        {timeline.hourTicks.map((tick, i) => (
          <text
            key={i}
            className="axis"
            x={Math.min(W - 2, Math.max(2, tick.frac * W))}
            y={H - 4}
            textAnchor={i === 0 ? 'start' : tick.frac > 0.95 ? 'end' : 'middle'}
          >
            {tick.label}
          </text>
        ))}
      </svg>
      <div className="timeline-legend">
        <span><span className="swatch active" /> Charging active</span>
        <span><span className="swatch idle" /> Paused / off-peak</span>
      </div>
    </div>
  );
}
