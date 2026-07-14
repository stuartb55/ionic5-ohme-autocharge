import type { ChargeSlot } from '../api/types';
import { buildTimeline } from '../utils/schedule';

const W = 720;
const H = 64;
const TRACK_Y = 16;
const TRACK_H = 28;

export function ScheduleTimeline({
  slots,
  now = new Date(),
  timeZone,
}: {
  slots: ChargeSlot[];
  now?: Date;
  timeZone?: string;
}) {
  const timeline = buildTimeline(slots, 5, timeZone);
  if (!timeline) return null;
  const nowMs = now.getTime();
  const showNow = nowMs >= timeline.startMs && nowMs <= timeline.endMs;
  const nowX = showNow
    ? ((nowMs - timeline.startMs) / (timeline.endMs - timeline.startMs)) * W
    : 0;

  return (
    <div className="timeline">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Charging schedule timeline">
        {/* idle track */}
        <rect x={0} y={TRACK_Y} width={W} height={TRACK_H} rx={8} fill="var(--charge-track)" />
        {/* active charging segments */}
        {timeline.segments.map((seg) => {
          const start = new Date(seg.slot.start).getTime();
          const end = new Date(seg.slot.end).getTime();
          const state = end <= nowMs ? 'complete' : start <= nowMs ? 'current' : 'upcoming';
          return (
          <rect
            key={seg.slot.start}
            className={`timeline-segment ${state}`}
            x={seg.startFrac * W}
            y={TRACK_Y}
            width={Math.max(2, seg.widthFrac * W)}
            height={TRACK_H}
            rx={8}
          >
            <title>
              {new Date(seg.slot.start).toLocaleTimeString('en-GB', timeZone ? { timeZone } : {})} –{' '}
              {new Date(seg.slot.end).toLocaleTimeString('en-GB', timeZone ? { timeZone } : {})} ·{' '}
              {seg.slot.energy} kWh
            </title>
          </rect>
          );
        })}
        {showNow && (
          <g className="timeline-now" aria-hidden="true">
            <line x1={nowX} x2={nowX} y1={TRACK_Y - 7} y2={TRACK_Y + TRACK_H + 5} />
            <circle cx={nowX} cy={TRACK_Y - 7} r={3} />
          </g>
        )}
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
        <span><span className="swatch active" /> Scheduled charging</span>
        <span><span className="swatch idle" /> Paused / off-peak</span>
        {showNow && <span><span className="swatch now" /> Now</span>}
      </div>
    </div>
  );
}
