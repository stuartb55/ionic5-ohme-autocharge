import { render, screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { sessionAuditFixture } from '../test/fixtures';
import { server } from '../test/mocks/server';
import { SessionAudit } from './SessionAudit';

describe('SessionAudit', () => {
  it('shows measured values, provenance and intervals without exposing identifiers', async () => {
    render(<SessionAudit sessionId={3} />);

    expect(await screen.findByText('18.50 kWh')).toBeInTheDocument();
    expect(screen.getByText('£1.23')).toBeInTheDocument();
    expect(screen.getByText('100%')).toBeInTheDocument();
    expect(screen.getByText('Vehicle plugged in')).toBeInTheDocument();
    expect(screen.getByText(/revision 1/i)).toBeInTheDocument();
    expect(screen.getByText('6.75p/kWh')).toBeInTheDocument();
    expect(screen.queryByText('session-3')).not.toBeInTheDocument();
    expect(screen.queryByText('VIN1')).not.toBeInTheDocument();
  });

  it('uses explicit empty states when evidence is absent', async () => {
    server.use(
      http.get('*/api/sessions/8/audit', () =>
        HttpResponse.json({ ...sessionAuditFixture, events: [], schedules: [], intervals: [] }),
      ),
    );
    render(<SessionAudit sessionId={8} />);

    expect(await screen.findByText(/no charging events/i)).toBeInTheDocument();
    expect(screen.getByText(/no schedule snapshots/i)).toBeInTheDocument();
    expect(screen.getByText(/no priced intervals/i)).toBeInTheDocument();
  });

  it('uses plain-English timeline labels and formats stored units', async () => {
    server.use(
      http.get('*/api/sessions/10/audit', () =>
        HttpResponse.json({
          ...sessionAuditFixture,
          events: [
            {
              at: '2026-07-16T20:05:00+01:00',
              type: 'target_configured',
              details: { soc: 70, target: 80, tripMode: false },
            },
            {
              at: '2026-07-17T08:36:00+01:00',
              type: 'session_reconciled',
              details: {
                trigger: 'finished',
                costMinor: 142,
                tariffCoverage: 1,
                counterEnergyWh: 7197,
                attributionIssues: 0,
                reconstructedEnergyWh: 7197,
              },
            },
          ],
        }),
      ),
    );
    render(<SessionAudit sessionId={10} />);

    expect(await screen.findByText('Charge timeline')).toBeInTheDocument();
    expect(screen.getByText('Charge target set')).toBeInTheDocument();
    expect(screen.getByText('Charging cost calculated')).toBeInTheDocument();
    expect(screen.getByText('Battery level')).toBeInTheDocument();
    expect(screen.getByText('70%')).toBeInTheDocument();
    expect(screen.getByText('Trip charge')).toBeInTheDocument();
    expect(screen.getByText('No')).toBeInTheDocument();
    expect(screen.getByText('Calculated after')).toBeInTheDocument();
    expect(screen.getByText('Charging finished')).toBeInTheDocument();
    expect(screen.getByText('Charging cost')).toBeInTheDocument();
    expect(screen.getByText('£1.42')).toBeInTheDocument();
    expect(screen.getByText('Tariff data coverage')).toBeInTheDocument();
    expect(screen.getByText('Charger reading')).toBeInTheDocument();
    expect(screen.getByText('Calculated energy')).toBeInTheDocument();
    expect(screen.getAllByText('7.20 kWh')).toHaveLength(2);
    expect(screen.queryByText('CostMinor')).not.toBeInTheDocument();
    expect(screen.queryByText('CounterEnergyWh')).not.toBeInTheDocument();
  });

  it('shows a contained error when the audit cannot be loaded', async () => {
    server.use(http.get('*/api/sessions/9/audit', () => new HttpResponse(null, { status: 500 })));
    render(<SessionAudit sessionId={9} />);

    expect(await screen.findByText(/couldn’t load this session’s audit details/i)).toBeInTheDocument();
  });
});
