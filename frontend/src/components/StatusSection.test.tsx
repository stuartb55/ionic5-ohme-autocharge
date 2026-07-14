import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { StatusResponse } from '../api/types';
import { statusFixture } from '../test/fixtures';
import { StatusSection } from './StatusSection';
import { ChargeSettingsSection } from './ChargeSettingsSection';

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
    // A time is rendered after "On track for"; the exact value depends on the
    // viewer's timezone, so don't pin it.
    expect(screen.getByRole('heading', { name: /on track for/i })).toHaveTextContent(/\d{1,2}:\d{2}/);
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

describe('StatusSection trip mode', () => {
  it('shows the active override and uses its target', () => {
    const status: StatusResponse = {
      ...statusFixture,
      charger: { ...statusFixture.charger, targetPercent: 100 },
      config: {
        ...statusFixture.config,
        tripMode: { enabled: true, targetPercent: 100, readyBy: '05:45' },
      },
    };
    render(
      <ChargeSettingsSection
        status={status}
        onSetTarget={vi.fn()}
        onSetReadyBy={vi.fn()}
        onSetDayTargets={vi.fn()}
        onSetTripMode={vi.fn()}
        onSetNotifications={vi.fn()}
      />,
    );

    expect(screen.getByText(/trip mode active/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/trip target percent/i)).toHaveValue(100);
    expect(screen.getByText(/clears automatically/i)).toBeInTheDocument();
  });
});

describe('StatusSection projected cost', () => {
  function withCharger(overrides: Partial<StatusResponse['charger']>): StatusResponse {
    return { ...statusFixture, charger: { ...statusFixture.charger, ...overrides } };
  }

  it('shows the estimated session cost when available', () => {
    render(<StatusSection status={withCharger({ projectedCost: 1.31, projectedCostCurrency: 'GBP' })} />);
    expect(screen.getByText('Estimated cost')).toBeInTheDocument();
    expect(screen.getByText(/£1\.31/)).toBeInTheDocument();
  });

  it('makes an unavailable cost explicit', () => {
    render(<StatusSection status={withCharger({ projectedCost: null })} />);
    expect(screen.getByText('Estimated cost')).toBeInTheDocument();
    expect(screen.getByText('Price unavailable')).toBeInTheDocument();
  });

  it('flags an Agile-priced cost', () => {
    render(<StatusSection status={withCharger({ projectedCost: 0.92, projectedCostMethod: 'agile' })} />);
    expect(screen.getByText('Estimated cost · Agile')).toBeInTheDocument();
    expect(screen.queryByText('Estimated cost')).not.toBeInTheDocument();
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

  it('shows battery health when reported', () => {
    render(<StatusSection status={withVehicle({ sohPercent: 98 })} />);
    expect(screen.getByText(/Battery health 98%/)).toBeInTheDocument();
  });

  it('omits battery health when not reported', () => {
    render(<StatusSection status={withVehicle({ sohPercent: null })} />);
    expect(screen.queryByText(/Battery health/)).not.toBeInTheDocument();
  });

  it('shows lock status and a location link', () => {
    render(
      <StatusSection
        status={withVehicle({ isLocked: true, location: { latitude: 51.5, longitude: -0.12 } })}
      />,
    );
    expect(screen.getByText(/Locked/)).toBeInTheDocument();
    const link = screen.getByRole('link', { name: /view location/i });
    expect(link).toHaveAttribute('href', 'https://www.google.com/maps?q=51.5,-0.12');
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
  });

  it('shows unlocked state and omits location when unknown', () => {
    render(<StatusSection status={withVehicle({ isLocked: false, location: null })} />);
    expect(screen.getByText(/Unlocked/)).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /view location/i })).not.toBeInTheDocument();
  });
});
