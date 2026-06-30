import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { StatusResponse } from '../api/types';
import { VehicleHealth } from './VehicleHealth';

type Health = StatusResponse['vehicle']['health'];

const healthy: Health = {
  auxBatteryPercent: null,
  tyrePressureWarning: false,
  washerFluidWarning: false,
  keyBatteryWarning: false,
  openItems: [],
};

describe('VehicleHealth', () => {
  it('renders nothing when there is no health data and no warnings', () => {
    const { container } = render(<VehicleHealth health={healthy} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows the 12V auxiliary battery when reported', () => {
    render(<VehicleHealth health={{ ...healthy, auxBatteryPercent: 85 }} />);
    expect(screen.getByText('12V 85%')).toBeInTheDocument();
  });

  it('lists only the active warnings', () => {
    render(
      <VehicleHealth
        health={{ ...healthy, tyrePressureWarning: true, keyBatteryWarning: true }}
      />,
    );
    expect(screen.getByText(/tyre pressure/i)).toBeInTheDocument();
    expect(screen.getByText(/key fob battery/i)).toBeInTheDocument();
    expect(screen.queryByText(/washer fluid/i)).not.toBeInTheDocument();
  });

  it('lists anything left open', () => {
    render(<VehicleHealth health={{ ...healthy, openItems: ['Boot', 'Front-left door'] }} />);
    expect(screen.getByText(/boot open/i)).toBeInTheDocument();
    expect(screen.getByText(/front-left door open/i)).toBeInTheDocument();
  });
});
