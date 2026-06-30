import { render, screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { server } from '../test/mocks/server';
import { SessionChargeCurve } from './SessionChargeCurve';

const points = [
  { at: '2026-06-01T20:00:00Z', socPercent: 40, powerWatts: 7000, sessionEnergyKwh: 0 },
  { at: '2026-06-01T20:30:00Z', socPercent: 55, powerWatts: 7400, sessionEnergyKwh: 3.5 },
  { at: '2026-06-01T21:00:00Z', socPercent: 70, powerWatts: 2000, sessionEnergyKwh: 7 },
];

describe('SessionChargeCurve', () => {
  it('renders the curve with the peak power once loaded', async () => {
    server.use(
      http.get('*/api/sessions/7/telemetry', () =>
        HttpResponse.json({ enabled: true, points }),
      ),
    );
    const { container } = render(<SessionChargeCurve sessionId={7} />);

    await waitFor(() => expect(screen.getByText(/peak 7.4 kW/i)).toBeInTheDocument());
    expect(container.querySelectorAll('polyline')).toHaveLength(2); // SOC + power
  });

  it('shows a message when there is not enough data', async () => {
    server.use(
      http.get('*/api/sessions/9/telemetry', () =>
        HttpResponse.json({ enabled: true, points: points.slice(0, 1) }),
      ),
    );
    render(<SessionChargeCurve sessionId={9} />);
    await waitFor(() =>
      expect(screen.getByText(/not enough data to chart/i)).toBeInTheDocument(),
    );
  });

  it('shows an error when the fetch fails', async () => {
    server.use(
      http.get('*/api/sessions/5/telemetry', () => new HttpResponse(null, { status: 500 })),
    );
    render(<SessionChargeCurve sessionId={5} />);
    await waitFor(() =>
      expect(screen.getByText(/couldn’t load this session’s charge curve/i)).toBeInTheDocument(),
    );
  });
});
