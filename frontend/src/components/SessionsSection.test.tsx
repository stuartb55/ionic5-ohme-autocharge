import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';
import { sessionsFixture } from '../test/fixtures';
import { server } from '../test/mocks/server';
import { SessionsSection } from './SessionsSection';

describe('SessionsSection', () => {
  it('renders nothing when history persistence is disabled', () => {
    const { container } = render(
      <SessionsSection data={{ enabled: false, review: null, sessions: [] }} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('shows an empty state when enabled but no sessions yet', () => {
    render(<SessionsSection data={{ enabled: true, review: null, sessions: [] }} />);
    expect(screen.getByText(/no plug-in sessions recorded yet/i)).toBeInTheDocument();
  });

  it('lists sessions with backend session details and action', () => {
    render(<SessionsSection data={sessionsFixture} />);

    expect(screen.getByRole('heading', { name: /recent sessions/i })).toBeInTheDocument();
    expect(screen.getByText(/54%\s*→\s*80%/)).toBeInTheDocument();
    expect(screen.getByText(/\+26%/)).toBeInTheDocument();
    expect(screen.getByText(/12,450 mi/)).toBeInTheDocument();
    expect(screen.getByText(/18\.5 kWh actual/)).toBeInTheDocument();
    expect(screen.getByText(/£1\.23 actual/)).toBeInTheDocument();
    expect(screen.getAllByText(/SoH 98%/)).toHaveLength(2);
    expect(screen.getAllByText(/Hyundai IONIQ 5/).length).toBeGreaterThan(0);
    expect(screen.getByText('Target set')).toBeInTheDocument();
    expect(screen.getByText(/85%\s*→\s*80%/)).toBeInTheDocument();
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
    render(<SessionsSection data={{ enabled: true, review: null, sessions: [] }} />);
    expect(screen.queryByRole('link', { name: /export/i })).not.toBeInTheDocument();
  });

  it('shows only server-filtered affected sessions with concrete issue labels', async () => {
    const onClearReview = vi.fn();
    const affected = {
      ...sessionsFixture.sessions[0]!,
      id: 8,
      actualCost: null,
      costCurrency: null,
      costMethod: null,
      tariffCoverage: null,
      quality: 'tariff_incomplete',
      reviewIssues: ['missing_cost' as const],
    };

    render(
      <SessionsSection
        data={{ enabled: true, review: 'missing_cost', sessions: [affected] }}
        reviewFilter="missing_cost"
        reviewTotal={1}
        onClearReview={onClearReview}
      />,
    );

    expect(screen.getByRole('heading', { name: /sessions needing attention/i })).toBeInTheDocument();
    expect(screen.getByText('Cost unavailable')).toBeInTheDocument();
    expect(screen.getByText(/1 session needs attention/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /show recent/i }));
    expect(onClearReview).toHaveBeenCalledOnce();
  });

  it('does not show stale unfiltered rows while an affected-session request loads', () => {
    render(
      <SessionsSection
        data={sessionsFixture}
        reviewFilter="missing_energy"
        reviewTotal={2}
      />,
    );

    expect(screen.getByText('Loading affected sessions…')).toBeInTheDocument();
    expect(screen.queryByText(/54%\s*→\s*80%/)).not.toBeInTheDocument();
  });

  it('expands a row to show its audit and charge curve on click', async () => {
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
    expect(screen.getByText(/measured energy/i)).toBeInTheDocument();
    expect(screen.getByText(/charge timeline/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { expanded: true })).toBeInTheDocument();
  });
});
