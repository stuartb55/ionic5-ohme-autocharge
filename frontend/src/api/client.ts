import type { ScheduleResponse, StatisticsResponse, StatusResponse } from './types';

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

export const api = {
  getStatus: (signal?: AbortSignal) => getJson<StatusResponse>('/api/status', signal),
  getSchedule: (signal?: AbortSignal) => getJson<ScheduleResponse>('/api/schedule', signal),
  getStatistics: (days = 7, signal?: AbortSignal) =>
    getJson<StatisticsResponse>(`/api/statistics?days=${days}`, signal),
};
