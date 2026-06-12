import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';
import type { StatusResponse } from '../api/types';
import { server } from '../test/mocks/server';
import { statusFixture } from '../test/fixtures';
import { ChargeControls } from './ChargeControls';

function withCharger(overrides: Partial<StatusResponse['charger']>): StatusResponse {
  return { ...statusFixture, charger: { ...statusFixture.charger, ...overrides } };
}

describe('ChargeControls', () => {
  it('renders nothing when the car is disconnected', () => {
    const { container } = render(
      <ChargeControls status={withCharger({ connected: false })} onChanged={() => {}} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('pauses an active charge and notifies the parent', async () => {
    let hits = 0;
    server.use(
      http.post('*/api/charge/pause', () => {
        hits += 1;
        return HttpResponse.json({ ok: true, status: 'paused', maxCharge: false });
      }),
    );
    const onChanged = vi.fn();
    render(<ChargeControls status={statusFixture} onChanged={onChanged} />);

    await userEvent.click(screen.getByRole('button', { name: /pause charging/i }));

    await waitFor(() => expect(hits).toBe(1));
    expect(onChanged).toHaveBeenCalled();
  });

  it('offers resume instead of pause while paused', async () => {
    render(
      <ChargeControls status={withCharger({ status: 'paused' })} onChanged={() => {}} />,
    );
    expect(screen.getByRole('button', { name: /resume charging/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /pause charging/i })).not.toBeInTheDocument();
  });

  it('requires confirmation before enabling boost', async () => {
    let body: { enabled: boolean } | null = null;
    server.use(
      http.put('*/api/charge/max-charge', async ({ request }) => {
        body = (await request.json()) as { enabled: boolean };
        return HttpResponse.json({ ok: true, status: 'charging', maxCharge: true });
      }),
    );
    render(<ChargeControls status={statusFixture} onChanged={() => {}} />);

    await userEvent.click(screen.getByRole('button', { name: /boost charge/i }));
    // First click only arms the confirmation — nothing sent yet.
    expect(body).toBeNull();

    await userEvent.click(screen.getByRole('button', { name: /confirm boost/i }));
    await waitFor(() => expect(body).toEqual({ enabled: true }));
  });

  it('cancel backs out of the boost confirmation without calling the API', async () => {
    let hits = 0;
    server.use(
      http.put('*/api/charge/max-charge', () => {
        hits += 1;
        return HttpResponse.json({ ok: true, status: 'charging', maxCharge: true });
      }),
    );
    render(<ChargeControls status={statusFixture} onChanged={() => {}} />);

    await userEvent.click(screen.getByRole('button', { name: /boost charge/i }));
    await userEvent.click(screen.getByRole('button', { name: /^cancel$/i }));

    expect(screen.getByRole('button', { name: /boost charge/i })).toBeInTheDocument();
    expect(hits).toBe(0);
  });

  it('offers stop boost while max charge is active', async () => {
    let body: { enabled: boolean } | null = null;
    server.use(
      http.put('*/api/charge/max-charge', async ({ request }) => {
        body = (await request.json()) as { enabled: boolean };
        return HttpResponse.json({ ok: true, status: 'charging', maxCharge: false });
      }),
    );
    render(
      <ChargeControls status={withCharger({ maxCharge: true })} onChanged={() => {}} />,
    );

    await userEvent.click(screen.getByRole('button', { name: /stop boost/i }));
    await waitFor(() => expect(body).toEqual({ enabled: false }));
  });

  it('shows an error when the action fails', async () => {
    server.use(http.post('*/api/charge/pause', () => HttpResponse.error()));
    render(<ChargeControls status={statusFixture} onChanged={() => {}} />);

    await userEvent.click(screen.getByRole('button', { name: /pause charging/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/action failed/i);
  });
});
