import { http, HttpResponse } from 'msw';
import { scheduleFixture, statisticsFixture, statusFixture } from '../fixtures';

// Wildcard origin (`*/…`) so the handlers match the relative fetches regardless
// of the jsdom base URL used by the test environment.
export const handlers = [
  http.get('*/api/status', () => HttpResponse.json(statusFixture)),
  http.get('*/api/schedule', () => HttpResponse.json(scheduleFixture)),
  http.get('*/api/statistics', ({ request }) => {
    const days = Number(new URL(request.url).searchParams.get('days') ?? 7);
    return HttpResponse.json({ ...statisticsFixture, rangeDays: days });
  }),
  http.put('*/api/settings/target', async ({ request }) => {
    const body = (await request.json()) as { targetPercent: number };
    return HttpResponse.json({ targetPercent: body.targetPercent, persisted: true, applied: false });
  }),
  http.post('*/api/refresh', () =>
    HttpResponse.json({ ok: true, updatedAt: statusFixture.updatedAt, ready: true }),
  ),
  http.post('*/api/charge/pause', () =>
    HttpResponse.json({ ok: true, status: 'paused', maxCharge: false }),
  ),
  http.post('*/api/charge/resume', () =>
    HttpResponse.json({ ok: true, status: 'charging', maxCharge: false }),
  ),
  http.put('*/api/charge/max-charge', async ({ request }) => {
    const body = (await request.json()) as { enabled: boolean };
    return HttpResponse.json({ ok: true, status: 'charging', maxCharge: body.enabled });
  }),
];
