import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { sessionsFixture } from '../test/fixtures';
import { server } from '../test/mocks/server';
import { SessionsSection } from './SessionsSection';

describe('SessionsSection', () => {
  it('renders nothing when history persistence is disabled', () => {
    const { container } = render(
      <SessionsSection data={{ enabled: false, sessions: [] }} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('shows an empty state when enabled but no sessions yet', () => {
    render(<SessionsSection data={{ enabled: true, sessions: [] }} />);
    expect(screen.getByText(/no plug-in sessions recorded yet/i)).toBeInTheDocument();
  });

  it('lists sessions with SOC, target and action', () => {
    render(<SessionsSection data={sessionsFixture} />);

    expect(screen.getByRole('heading', { name: /recent sessions/i })).toBeInTheDocument();
    expect(screen.getByText('54% → 80%')).toBeInTheDocument();
    expect(screen.getByText('Target set')).toBeInTheDocument();
    expect(screen.getByText('85% → 80%')).toBeInTheDocument();
    expect(screen.getByText('Already at target')).toBeInTheDocument();
  });

  it('offers full-history CSV and JSON export links when there are sessions', () => {
    render(<SessionsSection data={sessionsFixture} />);

    const csv = screen.getByRole('link', { name: /export csv/i });
    const json = screen.getByRole('link', { name: /json/i });
    expect(csv).toHaveAttribute('href', expect.stringContaining('/api/sessions/export?format=csv'));
    expect(csv).toHaveAttribute('download');
    expect(json).toHaveAttribute('href', expect.stringContaining('format=json'));
  });

  it('hides the export links when there are no sessions to export', () => {
    render(<SessionsSection data={{ enabled: true, sessions: [] }} />);
    expect(screen.queryByRole('link', { name: /export/i })).not.toBeInTheDocument();
  });

  it('expands a row to show its charge curve on click', async () => {
    server.use(
      http.get('*/api/sessions/3/telemetry', () =>
        HttpResponse.json({
          enabled: true,
          points: [
            { at: '2026-06-01T20:00:00Z', socPercent: 54, powerWatts: 7000, sessionEnergyKwh: 0 },
            { at: '2026-06-01T20:30:00Z', socPercent: 70, powerWatts: 7400, sessionEnergyKwh: 4 },
          ],
        }),
      ),
    );
    render(<SessionsSection data={sessionsFixture} />);

    const row = screen.getAllByRole('button', { expanded: false })[0]!;
    await userEvent.click(row);

    await waitFor(() => expect(screen.getByText(/battery %/i)).toBeInTheDocument());
    expect(screen.getByRole('button', { expanded: true })).toBeInTheDocument();
  });
});
