import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { Dashboard } from '../../components/Dashboard';
import { server } from '../mocks/server';
import { statisticsFixture } from '../fixtures';

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
    expect(screen.getByRole('img', { name: /daily energyKwh bar chart/i })).toBeInTheDocument();
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

  it('shows an error banner when the backend is unreachable', async () => {
    server.use(http.get('*/api/status', () => HttpResponse.error()));
    render(<Dashboard />);
    expect(await screen.findByRole('alert')).toHaveTextContent(/can't reach the charging service/i);
  });
});
