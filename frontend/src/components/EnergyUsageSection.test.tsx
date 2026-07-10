import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { EnergyUsageResponse } from '../api/types';
import { EnergyUsageSection } from './EnergyUsageSection';

afterEach(() => {
  vi.useRealTimers();
});

const data: EnergyUsageResponse = {
  enabled: true,
  date: '2026-06-01',
  currency: 'GBP',
  slots: [
    { start: '2026-06-01T00:00:00+00:00', end: '2026-06-01T00:30:00+00:00', importKwh: 1.5, carKwh: 1.0, houseKwh: 0.5, unattributedKwh: 0, quality: 'good' },
    { start: '2026-06-01T00:30:00+00:00', end: '2026-06-01T01:00:00+00:00', importKwh: 0.4, carKwh: 0, houseKwh: 0.4, unattributedKwh: 0, quality: 'good' },
  ],
  totals: { importKwh: 1.9, carKwh: 1.0, houseKwh: 0.9, unattributedKwh: 0 },
};

describe('EnergyUsageSection', () => {
  it('renders nothing when disabled', () => {
    const { container } = render(
      <EnergyUsageSection
        data={{ enabled: false, date: null, slots: [], totals: null }}
        onDateChange={() => {}}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('shows the day totals split into car and rest-of-house', () => {
    render(<EnergyUsageSection data={data} onDateChange={() => {}} />);
    expect(screen.getByText('House vs car')).toBeInTheDocument();
    // Totals (formatKwh renders one decimal + " kWh").
    expect(screen.getByText('1.9 kWh')).toBeInTheDocument(); // import
    expect(screen.getByText('1.0 kWh')).toBeInTheDocument(); // car
    expect(screen.getByText('0.9 kWh')).toBeInTheDocument(); // house
  });

  it('pages to the previous day via the day selector', async () => {
    const onDateChange = vi.fn();
    const user = userEvent.setup();
    render(<EnergyUsageSection data={data} onDateChange={onDateChange} />);
    await user.click(screen.getByLabelText('Previous day'));
    expect(onDateChange).toHaveBeenCalledWith('2026-05-31');
  });

  it('disables next once the shown day is the latest available (yesterday)', () => {
    // "Now" is 2026-06-02, so the latest navigable day is 2026-06-01 — the day
    // shown — and the Next button must be disabled.
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-06-02T10:00:00Z'));
    render(<EnergyUsageSection data={data} onDateChange={() => {}} />);
    expect(screen.getByLabelText('Next day')).toBeDisabled();
    expect(screen.getByLabelText('Previous day')).toBeEnabled();
  });

  it('shows an empty state when the day has no slots', () => {
    render(
      <EnergyUsageSection
        data={{ ...data, slots: [], totals: { importKwh: 0, carKwh: 0, houseKwh: 0, unattributedKwh: 0 } }}
        onDateChange={() => {}}
      />,
    );
    expect(screen.getByText(/no consumption data/i)).toBeInTheDocument();
  });

  it('surfaces energy that could not be attributed confidently', () => {
    const uncertain: EnergyUsageResponse = {
      ...data,
      slots: [{
        start: '2026-06-01T00:00:00+00:00', end: '2026-06-01T00:30:00+00:00',
        importKwh: 1.2, carKwh: 0, houseKwh: 0, unattributedKwh: 1.2,
        quality: 'uncertain_gap',
      }],
      totals: { importKwh: 1.2, carKwh: 0, houseKwh: 0, unattributedKwh: 1.2 },
    };
    render(<EnergyUsageSection data={uncertain} onDateChange={() => {}} />);
    expect(screen.getAllByText('Unattributed')).toHaveLength(2); // total label + legend
    expect(screen.getAllByText('1.2 kWh')).toHaveLength(2);
  });
});
