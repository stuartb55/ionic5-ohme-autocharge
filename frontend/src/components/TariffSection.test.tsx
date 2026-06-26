import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { TariffResponse } from '../api/types';
import { TariffSection } from './TariffSection';

const data: TariffResponse = {
  enabled: true,
  currency: 'GBP',
  rates: [
    { from: '2026-06-26T17:00:00Z', to: '2026-06-26T17:30:00Z', pricePerKwh: 0.2 },
    { from: '2026-06-26T17:30:00Z', to: '2026-06-26T18:00:00Z', pricePerKwh: 0.08 },
  ],
  cheapest: [{ from: '2026-06-26T17:30:00Z', to: '2026-06-26T18:00:00Z', pricePerKwh: 0.08 }],
};

describe('TariffSection', () => {
  it('shows the current price and cheapest upcoming slots', () => {
    render(<TariffSection data={data} />);
    // Current price (first rate) in the header, GBP rendered as pence.
    const now = screen.getByText('Now').closest('.tariff-now') as HTMLElement;
    expect(within(now).getByText('20.0p')).toBeInTheDocument();
    // Cheapest list.
    expect(screen.getByText('Cheapest upcoming')).toBeInTheDocument();
    expect(screen.getByText('8.0p')).toBeInTheDocument();
  });

  it('handles an empty rate list', () => {
    render(<TariffSection data={{ enabled: true, rates: [], cheapest: [] }} />);
    expect(screen.getByText(/no upcoming rates/i)).toBeInTheDocument();
  });
});
