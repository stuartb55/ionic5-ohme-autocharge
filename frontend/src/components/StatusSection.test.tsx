import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { StatusResponse } from '../api/types';
import { statusFixture } from '../test/fixtures';
import { StatusSection } from './StatusSection';

function withCharger(overrides: Partial<StatusResponse['charger']>): StatusResponse {
  return { ...statusFixture, charger: { ...statusFixture.charger, ...overrides } };
}

describe('StatusSection projected finish', () => {
  beforeEach(() => {
    // The fixture's projectedFinish is 05:00 on 2026-06-02; pin "now" before it.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date('2026-06-02T00:08:00+01:00'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows when the charge is projected to finish', () => {
    render(<StatusSection status={statusFixture} />);
    expect(screen.getByText(/ready by ~/i)).toHaveTextContent('05:00');
  });

  it('hides the projection once the finish time has passed', () => {
    vi.setSystemTime(new Date('2026-06-02T06:00:00+01:00'));
    render(<StatusSection status={statusFixture} />);
    expect(screen.queryByText(/ready by/i)).not.toBeInTheDocument();
  });

  it('hides the projection when disconnected or finished', () => {
    const { rerender } = render(
      <StatusSection status={withCharger({ connected: false, projectedFinish: null })} />,
    );
    expect(screen.queryByText(/ready by/i)).not.toBeInTheDocument();

    rerender(<StatusSection status={withCharger({ status: 'finished' })} />);
    expect(screen.queryByText(/ready by/i)).not.toBeInTheDocument();
  });
});
