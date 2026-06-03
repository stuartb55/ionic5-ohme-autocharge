import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { BatteryRing } from './BatteryRing';

describe('BatteryRing', () => {
  it('renders the percentage and an accessible label', () => {
    render(<BatteryRing percent={62} target={80} />);
    expect(screen.getByText('62')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /state of charge 62%/i })).toBeInTheDocument();
  });

  it('shows a placeholder when the percentage is unknown', () => {
    render(<BatteryRing percent={null} />);
    expect(screen.getByText('–')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /unavailable/i })).toBeInTheDocument();
  });

  it('clamps out-of-range values', () => {
    render(<BatteryRing percent={150} />);
    expect(screen.getByText('100')).toBeInTheDocument();
  });
});
