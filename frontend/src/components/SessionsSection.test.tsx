import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { sessionsFixture } from '../test/fixtures';
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
});
