import type {
  ChargeActionResponse,
  ReadyByUpdateResponse,
  ScheduleResponse,
  SessionsResponse,
  StatisticsResponse,
  StatusResponse,
  TargetUpdateResponse,
} from './types';

// Same-origin relative base: in production nginx proxies /api to the backend;
// in dev Vite's proxy does the same. Override with VITE_API_BASE if needed.
const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '';

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    signal,
    headers: { Accept: 'application/json' },
  });
  if (!res.ok) {
    throw new ApiError(`Request to ${path} failed`, res.status);
  }
  return (await res.json()) as T;
}

async function putJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'PUT',
    signal,
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new ApiError(`Request to ${path} failed`, res.status);
  }
  return (await res.json()) as T;
}

async function postJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    signal,
    headers: { Accept: 'application/json' },
  });
  if (!res.ok) {
    throw new ApiError(`Request to ${path} failed`, res.status);
  }
  return (await res.json()) as T;
}

export interface RefreshResponse {
  ok: boolean;
  updatedAt: string | null;
  ready: boolean;
}

export const api = {
  getStatus: (signal?: AbortSignal) => getJson<StatusResponse>('/api/status', signal),
  getSchedule: (signal?: AbortSignal) => getJson<ScheduleResponse>('/api/schedule', signal),
  getStatistics: (days = 7, signal?: AbortSignal) =>
    getJson<StatisticsResponse>(`/api/statistics?days=${days}`, signal),
  getSessions: (limit = 8, signal?: AbortSignal) =>
    getJson<SessionsResponse>(`/api/sessions?limit=${limit}`, signal),
  setTarget: (targetPercent: number, signal?: AbortSignal) =>
    putJson<TargetUpdateResponse>('/api/settings/target', { targetPercent }, signal),
  // Set ("HH:MM") or clear (null) the ready-by departure time.
  setReadyBy: (readyBy: string | null, signal?: AbortSignal) =>
    putJson<ReadyByUpdateResponse>('/api/settings/ready-by', { readyBy }, signal),
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
