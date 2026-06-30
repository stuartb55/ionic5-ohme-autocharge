import type { SessionTelemetryPoint } from '../api/types';

export interface CurveDims {
  width: number;
  height: number;
  padX: number;
  padY: number;
}

export interface ChargeCurve {
  /** SVG polyline points for the SOC series (empty string when none). */
  socLine: string;
  /** SVG polyline points for the power series (empty string when none). */
  powerLine: string;
  socStart: number | null;
  socEnd: number | null;
  peakPowerKw: number;
  startAt: string | null;
  endAt: string | null;
}

/**
 * Build SVG coordinates for a session's charge curve: SOC on a fixed 0–100%
 * scale (so the climb is comparable across sessions) and power scaled to its own
 * peak, both laid out on a shared time axis. Pure — no DOM — so it's unit-tested
 * directly. Returns null when there aren't at least two timestamped points to
 * draw a line between.
 */
export function buildChargeCurve(
  points: SessionTelemetryPoint[],
  dims: CurveDims,
): ChargeCurve | null {
  const timed = points.filter((p) => p.at != null);
  if (timed.length < 2) return null;

  const times = timed.map((p) => new Date(p.at as string).getTime());
  const t0 = times[0]!;
  const t1 = times[times.length - 1]!;
  const tSpan = t1 - t0 || 1; // guard /0 if every point shares a timestamp
  const chartW = dims.width - dims.padX * 2;
  const chartH = dims.height - dims.padY * 2;
  const x = (t: number) => dims.padX + ((t - t0) / tSpan) * chartW;

  const socCoords = timed
    .map((p, i) => ({ soc: p.socPercent, t: times[i]! }))
    .filter((c): c is { soc: number; t: number } => c.soc != null)
    .map((c) => `${x(c.t).toFixed(1)},${(dims.padY + (1 - c.soc / 100) * chartH).toFixed(1)}`);

  const powerKw = timed.map((p) => (p.powerWatts != null ? p.powerWatts / 1000 : null));
  const peakPowerKw = Math.max(0, ...powerKw.filter((v): v is number => v != null));
  const powerScale = peakPowerKw || 1; // flat at 0 → a baseline rather than /0
  const powerCoords = timed
    .map((_, i) => ({ kw: powerKw[i], t: times[i]! }))
    .filter((c): c is { kw: number; t: number } => c.kw != null)
    .map((c) => `${x(c.t).toFixed(1)},${(dims.padY + (1 - c.kw / powerScale) * chartH).toFixed(1)}`);

  const socValues = timed
    .map((p) => p.socPercent)
    .filter((v): v is number => v != null);

  return {
    socLine: socCoords.join(' '),
    powerLine: powerCoords.join(' '),
    socStart: socValues[0] ?? null,
    socEnd: socValues[socValues.length - 1] ?? null,
    peakPowerKw,
    startAt: timed[0]!.at,
    endAt: timed[timed.length - 1]!.at,
  };
}
