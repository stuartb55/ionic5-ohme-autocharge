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
    // The fixture's projectedFinish is 2026-06-02T05:00+01:00; pin "now" before
    // it. Both are absolute instants, so the show/hide logic is timezone-
    // independent — but the rendered clock string is not, so assertions below
    // match a time pattern rather than a fixed value (exact formatting is
    // covered by format.test.ts).
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date('2026-06-02T00:08:00+01:00'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows when the charge is projected to finish', () => {
    render(<StatusSection status={statusFixture} />);
    // A time is rendered after "Ready by ~"; the exact value depends on the
    // viewer's timezone, so don't pin it.
    expect(screen.getByText(/ready by ~/i)).toHaveTextContent(/\d{1,2}:\d{2}/);
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

describe('StatusSection driving range', () => {
  function withVehicle(overrides: Partial<StatusResponse['vehicle']>): StatusResponse {
    return { ...statusFixture, vehicle: { ...statusFixture.vehicle, ...overrides } };
  }

  it('shows the range next to the vehicle name', () => {
    render(<StatusSection status={withVehicle({ rangeMiles: 180 })} />);
    expect(screen.getByText(/180 mi/)).toBeInTheDocument();
  });

  it('omits the range when not reported', () => {
    render(<StatusSection status={withVehicle({ rangeMiles: null })} />);
    expect(screen.queryByText(/mi$/)).not.toBeInTheDocument();
  });
});
