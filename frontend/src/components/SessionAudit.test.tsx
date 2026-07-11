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
    expect(screen.getByText('Plugged in')).toBeInTheDocument();
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

    expect(await screen.findByText(/no lifecycle events/i)).toBeInTheDocument();
    expect(screen.getByText(/no schedule snapshots/i)).toBeInTheDocument();
    expect(screen.getByText(/no priced intervals/i)).toBeInTheDocument();
  });

  it('shows a contained error when the audit cannot be loaded', async () => {
    server.use(http.get('*/api/sessions/9/audit', () => new HttpResponse(null, { status: 500 })));
    render(<SessionAudit sessionId={9} />);

    expect(await screen.findByText(/couldn’t load this session’s audit details/i)).toBeInTheDocument();
  });
});
