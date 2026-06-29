import { render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { TariffResponse } from '../api/types';
import { TariffSection } from './TariffSection';

afterEach(() => {
  vi.useRealTimers();
});

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

  it('shows the slot in effect now, not just the first in the list', () => {
    // "Now" is inside the second slot's window (17:30–18:00), so the header
    // must show 8.0p — proving it selects by time rather than rates[0].
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-06-26T17:45:00Z'));
    render(<TariffSection data={data} />);
    const now = screen.getByText('Now').closest('.tariff-now') as HTMLElement;
    expect(within(now).getByText('8.0p')).toBeInTheDocument();
  });

  it('handles an empty rate list', () => {
    render(<TariffSection data={{ enabled: true, rates: [], cheapest: [] }} />);
    expect(screen.getByText(/no upcoming rates/i)).toBeInTheDocument();
  });
});
