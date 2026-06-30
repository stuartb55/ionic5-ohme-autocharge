import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { SessionTelemetryResponse } from '../api/types';
import { buildChargeCurve } from '../utils/chargeCurve';
import { formatTime } from '../utils/format';

const W = 320;
const H = 120;
const PAD_X = 8;
const PAD_Y = 12;

/**
 * The charge curve for one session — battery SOC climbing and the charge draw
 * over time — fetched on demand from the per-poll telemetry history. Rendered
 * inline when a session row is expanded.
 */
export function SessionChargeCurve({ sessionId }: { sessionId: number }) {
  const [data, setData] = useState<SessionTelemetryResponse | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    // A fresh instance mounts per expanded row (keyed by session), so initial
    // state is already clean — the effect only fetches and resolves it.
    const controller = new AbortController();
    api
      .getSessionTelemetry(sessionId, controller.signal)
      .then((res) => {
        if (!controller.signal.aborted) setData(res);
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => controller.abort();
  }, [sessionId]);

  if (failed) {
    return <p className="session-curve empty">Couldn’t load this session’s charge curve.</p>;
  }
  if (!data) {
    return <div className="session-curve skeleton" style={{ height: H }} />;
  }

  const curve = buildChargeCurve(data.points, { width: W, height: H, padX: PAD_X, padY: PAD_Y });
  if (!curve) {
    return <p className="session-curve empty">Not enough data to chart this session.</p>;
  }

  const peak = `${curve.peakPowerKw.toFixed(1)} kW`;

  return (
    <div className="session-curve">
      <div className="curve-legend">
        <span className="legend soc">Battery %</span>
        <span className="legend power">Power · peak {peak}</span>
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={`Charge curve: battery ${curve.socStart ?? '—'}% to ${curve.socEnd ?? '—'}%, peak draw ${peak}`}
      >
        {curve.powerLine && (
          <polyline
            points={curve.powerLine}
            fill="none"
            stroke="var(--accent)"
            strokeWidth={1.5}
            strokeDasharray="4 3"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        )}
        {curve.socLine && (
          <polyline
            points={curve.socLine}
            fill="none"
            stroke="var(--brand)"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        )}
      </svg>
      <div className="curve-axis" aria-hidden="true">
        <span>{curve.startAt ? formatTime(curve.startAt) : ''}</span>
        <span>{curve.endAt ? formatTime(curve.endAt) : ''}</span>
      </div>
    </div>
  );
}
