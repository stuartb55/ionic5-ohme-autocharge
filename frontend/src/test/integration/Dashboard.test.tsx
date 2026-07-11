import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';
import { Dashboard } from '../../components/Dashboard';
import { server } from '../mocks/server';
import { statisticsFixture, statusFixture } from '../fixtures';

describe('Dashboard integration', () => {
  it('renders all three sections wired to the API', async () => {
    render(<Dashboard />);

    // Section 1: status
    expect(await screen.findByText('Hyundai IONIQ 5')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /state of charge 62%/i })).toBeInTheDocument();
    expect(screen.getByText('Charging')).toBeInTheDocument();
    expect(screen.getByText('7.4 kW')).toBeInTheDocument();

    // Section 2: schedule
    expect(await screen.findByRole('img', { name: /schedule timeline/i })).toBeInTheDocument();
    expect(screen.getByText(/Charging active/i)).toBeInTheDocument();

    // Section 3: statistics
    expect(await screen.findByText('Saved vs standard tariff')).toBeInTheDocument();
    expect(screen.getByText('42.0 kWh')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /daily energy bar chart/i })).toBeInTheDocument();
  });

  it('refetches statistics when the time range changes', async () => {
    const requested: string[] = [];
    server.use(
      http.get('*/api/statistics', ({ request }) => {
        const days = new URL(request.url).searchParams.get('days') ?? '7';
        requested.push(days);
        return HttpResponse.json({ ...statisticsFixture, rangeDays: Number(days) });
      }),
    );

    render(<Dashboard />);
    await screen.findByText('Saved vs standard tariff');

    const ranges = screen.getByRole('group', { name: /time range/i });
    await userEvent.click(within(ranges).getByRole('button', { name: '30d' }));

    await waitFor(() => expect(requested).toContain('30'));
  });

  it('shows time since the backend last polled Ohme, not since the browser fetched', async () => {
    // statusFixture.updatedAt is 2026-06-02T00:05:00+01:00; pretend "now" is 3
    // minutes later. The label must reflect that backend poll time (3m ago), not
    // the browser fetch which just happened (~0s ago).
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date('2026-06-02T00:08:00+01:00'));
    try {
      render(<Dashboard />);
      await screen.findByText('Hyundai IONIQ 5');
      expect(screen.getByText(/Updated 3m ago/i)).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('saves a new charge target via the API', async () => {
    let putBody: { targetPercent: number } | null = null;
    server.use(
      http.put('*/api/settings/target', async ({ request }) => {
        putBody = (await request.json()) as { targetPercent: number };
        return HttpResponse.json({ ...putBody, persisted: true, applied: false });
      }),
    );

    render(<Dashboard />);
    // Status section renders the editor with the fixture target (80%).
    await screen.findByRole('button', { name: /charge target 80%/i });

    await userEvent.click(screen.getByRole('button', { name: /increase target/i }));
    await userEvent.click(screen.getByRole('button', { name: /save 85%/i }));

    await waitFor(() => expect(putBody).toEqual({ targetPercent: 85 }));
  });

  it('forces a backend refresh then refetches when the button is clicked', async () => {
    let statusHits = 0;
    let refreshHits = 0;
    server.use(
      http.get('*/api/status', () => {
        statusHits += 1;
        return HttpResponse.json(statusFixture);
      }),
      http.post('*/api/refresh', () => {
        refreshHits += 1;
        return HttpResponse.json({ ok: true, updatedAt: statusFixture.updatedAt, ready: true });
      }),
    );

    render(<Dashboard />);
    await screen.findByText('Hyundai IONIQ 5');
    const initialStatusHits = statusHits;

    await userEvent.click(screen.getByRole('button', { name: /refresh now/i }));

    await waitFor(() => expect(refreshHits).toBe(1));
    await waitFor(() => expect(statusHits).toBeGreaterThan(initialStatusHits));
  });

  it('switches the daily chart to the Cost metric', async () => {
    render(<Dashboard />);
    await screen.findByRole('img', { name: /daily energy bar chart/i });

    await userEvent.click(screen.getByRole('button', { name: 'Cost' }));

    expect(screen.getByRole('img', { name: /daily cost bar chart/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Daily cost' })).toBeInTheDocument();
  });

  it('shows an error banner when the backend is unreachable', async () => {
    server.use(http.get('*/api/status', () => HttpResponse.error()));
    render(<Dashboard />);
    expect(await screen.findByRole('alert')).toHaveTextContent(/can't reach the charging service/i);
  });

  it('shows a per-section error with retry when the schedule fails to load', async () => {
    server.use(http.get('*/api/schedule', () => HttpResponse.error()));
    render(<Dashboard />);

    // Status still loads fine; only the schedule card shows an error.
    expect(await screen.findByText('Hyundai IONIQ 5')).toBeInTheDocument();
    expect(await screen.findByText(/couldn’t load the charge schedule/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });

  it('flags stale data when the backend cannot reach Ohme', async () => {
    server.use(
      http.get('*/api/status', () =>
        HttpResponse.json({ ...statusFixture, lastError: 'poll_failed' }),
      ),
    );
    render(<Dashboard />);

    // The last good snapshot is still rendered…
    expect(await screen.findByText('Hyundai IONIQ 5')).toBeInTheDocument();
    // …with a banner explaining that live updates are failing.
    expect(screen.getByRole('alert')).toHaveTextContent(/can't reach ohme/i);
  });
});
