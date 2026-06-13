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
});
