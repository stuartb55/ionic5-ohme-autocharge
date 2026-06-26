import { http, HttpResponse } from 'msw';
import { scheduleFixture, sessionsFixture, statisticsFixture, statusFixture } from '../fixtures';

// Wildcard origin (`*/…`) so the handlers match the relative fetches regardless
// of the jsdom base URL used by the test environment.
export const handlers = [
  http.get('*/api/status', () => HttpResponse.json(statusFixture)),
  http.get('*/api/version', () => HttpResponse.json({ version: 'testsha1234567' })),
  // Single vehicle by default, so the dashboard picker stays hidden in tests.
  http.get('*/api/vehicles', () =>
    HttpResponse.json({
      vehicles: [{ id: 'car-1', name: 'IONIQ 5', vin: 'VIN1', model: 'IONIQ 5' }],
      selected: null,
    }),
  ),
  http.put('*/api/settings/vehicle', async ({ request }) => {
    const body = (await request.json()) as { vehicleId: string | null };
    return HttpResponse.json({ vehicleId: body.vehicleId, persisted: true, applied: false });
  }),
  http.get('*/api/schedule', () => HttpResponse.json(scheduleFixture)),
  http.get('*/api/sessions', () => HttpResponse.json(sessionsFixture)),
  // Tariff feature off by default, so the card stays hidden in tests.
  http.get('*/api/tariff', () => HttpResponse.json({ enabled: false, rates: [], cheapest: [] })),
  http.get('*/api/statistics', ({ request }) => {
    const days = Number(new URL(request.url).searchParams.get('days') ?? 7);
    return HttpResponse.json({ ...statisticsFixture, rangeDays: days });
  }),
  http.put('*/api/settings/target', async ({ request }) => {
    const body = (await request.json()) as { targetPercent: number };
    return HttpResponse.json({ targetPercent: body.targetPercent, persisted: true, applied: false });
  }),
  http.put('*/api/settings/ready-by', async ({ request }) => {
    const body = (await request.json()) as { readyBy: string | null };
    return HttpResponse.json({ readyBy: body.readyBy, persisted: true, applied: false });
  }),
  http.put('*/api/settings/day-targets', async ({ request }) => {
    const body = (await request.json()) as { dayTargets: Record<string, number> };
    return HttpResponse.json({ dayTargets: body.dayTargets, persisted: true, applied: false });
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
