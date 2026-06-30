import type {
  ChargeActionResponse,
  DayTargetsUpdateResponse,
  EnergyUsageResponse,
  ReadyByUpdateResponse,
  ScheduleResponse,
  SessionsResponse,
  SohHistoryResponse,
  StatisticsResponse,
  StatusResponse,
  TargetUpdateResponse,
  TariffResponse,
  VehicleUpdateResponse,
  VehiclesResponse,
} from './types';

// Same-origin relative base: in production nginx proxies /api to the backend;
// in dev Vite's proxy does the same. Override with VITE_API_BASE if needed.
const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '';

// Sent on every request. The backend's CSRF guard requires it on the
// body-less POST endpoints (pause/resume/refresh): a browser can't attach a
// custom header to a cross-origin "simple request" without a CORS preflight,
// so this stops another site from forging those actions against the LAN IP.
const REQUESTED_WITH = { 'X-Requested-With': 'autocharge-ui' } as const;

export class ApiError extends Error {
  status: number;
  /** Backend-provided detail (FastAPI's `{ detail }`), when present. */
  detail?: string;
  constructor(message: string, status: number, detail?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

// Best-effort read of a FastAPI error body so callers can surface the backend's
// own message (e.g. "target out of bounds") rather than a blanket failure.
async function errorFor(res: Response, path: string): Promise<ApiError> {
  let detail: string | undefined;
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body?.detail === 'string') detail = body.detail;
  } catch {
    /* non-JSON or empty body — fall back to the generic message */
  }
  return new ApiError(detail ?? `Request to ${path} failed`, res.status, detail);
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    signal,
    headers: { Accept: 'application/json', ...REQUESTED_WITH },
  });
  if (!res.ok) {
    throw await errorFor(res, path);
  }
  return (await res.json()) as T;
}

async function putJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'PUT',
    signal,
    headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...REQUESTED_WITH },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw await errorFor(res, path);
  }
  return (await res.json()) as T;
}

async function postJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    signal,
    headers: { Accept: 'application/json', ...REQUESTED_WITH },
  });
  if (!res.ok) {
    throw await errorFor(res, path);
  }
  return (await res.json()) as T;
}


export interface RefreshResponse {
  ok: boolean;
  updatedAt: string | null;
  ready: boolean;
}

export interface VersionResponse {
  /** Build git SHA, or "dev" in local runs. */
  version: string;
}

export const api = {
  getStatus: (signal?: AbortSignal) => getJson<StatusResponse>('/api/status', signal),
  getSchedule: (signal?: AbortSignal) => getJson<ScheduleResponse>('/api/schedule', signal),
  getStatistics: (days = 7, signal?: AbortSignal) =>
    getJson<StatisticsResponse>(`/api/statistics?days=${days}`, signal),
  getSessions: (limit = 8, signal?: AbortSignal) =>
    getJson<SessionsResponse>(`/api/sessions?limit=${limit}`, signal),
  getSohHistory: (limit = 90, signal?: AbortSignal) =>
    getJson<SohHistoryResponse>(`/api/soh-history?limit=${limit}`, signal),
  getTariff: (signal?: AbortSignal) => getJson<TariffResponse>('/api/tariff', signal),
  // Household-vs-car energy for a day (YYYY-MM-DD); omit for yesterday (default).
  getEnergyUsage: (date?: string, signal?: AbortSignal) =>
    getJson<EnergyUsageResponse>(
      date ? `/api/energy-usage?date=${date}` : '/api/energy-usage',
      signal,
    ),
  getVersion: (signal?: AbortSignal) => getJson<VersionResponse>('/api/version', signal),
  getVehicles: (signal?: AbortSignal) => getJson<VehiclesResponse>('/api/vehicles', signal),
  // Select which Hyundai vehicle to read (null = first).
  setVehicle: (vehicleId: string | null, signal?: AbortSignal) =>
    putJson<VehicleUpdateResponse>('/api/settings/vehicle', { vehicleId }, signal),
  setTarget: (targetPercent: number, signal?: AbortSignal) =>
    putJson<TargetUpdateResponse>('/api/settings/target', { targetPercent }, signal),
  // Set ("HH:MM") or clear (null) the ready-by departure time.
  setReadyBy: (readyBy: string | null, signal?: AbortSignal) =>
    putJson<ReadyByUpdateResponse>('/api/settings/ready-by', { readyBy }, signal),
  // Replace the per-weekday target overrides (weekday 0-6 -> percent).
  setDayTargets: (dayTargets: Record<number, number>, signal?: AbortSignal) =>
    putJson<DayTargetsUpdateResponse>('/api/settings/day-targets', { dayTargets }, signal),
  // Ask the backend to pull a fresh live reading from Ohme, then the caller
  // refetches the read endpoints to display it.
  refresh: (signal?: AbortSignal) => postJson<RefreshResponse>('/api/refresh', signal),
  // Charge controls — pause/resume the session, or toggle max-charge (boost).
  pauseCharge: (signal?: AbortSignal) =>
    postJson<ChargeActionResponse>('/api/charge/pause', signal),
  resumeCharge: (signal?: AbortSignal) =>
    postJson<ChargeActionResponse>('/api/charge/resume', signal),
  setMaxCharge: (enabled: boolean, signal?: AbortSignal) =>
    putJson<ChargeActionResponse>('/api/charge/max-charge', { enabled }, signal),
};
