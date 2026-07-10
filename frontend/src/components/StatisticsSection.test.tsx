import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { StatisticsResponse } from '../api/types';
import { statisticsFixture } from '../test/fixtures';
import { StatisticsSection } from './StatisticsSection';

function renderSection(stats: StatisticsResponse = statisticsFixture) {
  const onDaysChange = vi.fn();
  render(<StatisticsSection stats={stats} days={7} onDaysChange={onDaysChange} />);
  return { onDaysChange };
}

describe('StatisticsSection insights', () => {
  it('shows derived insights from the daily data', () => {
    renderSection();
    // 5 of 7 days had a charge in the fixture
    expect(screen.getByText('Charging days')).toBeInTheDocument();
    expect(screen.getByText('of 7 days')).toBeInTheDocument();
    expect(screen.getByText('Best day')).toBeInTheDocument();
    expect(screen.getByText('Est. range added')).toBeInTheDocument();
    expect(screen.getByText('Total cost')).toBeInTheDocument();
    expect(screen.getByText(/Complete through/)).toHaveTextContent(/2/);
    expect(screen.getByText('Sources & methods')).toBeInTheDocument();
  });

  it('discloses source methods and matched coverage', async () => {
    renderSection();
    await userEvent.click(screen.getByText('Sources & methods'));
    expect(screen.getByText(/Ohme charge summary/)).toBeInTheDocument();
    expect(screen.getByText(/0 matched home charges/)).toBeInTheDocument();
    expect(screen.getByText(/reconciled tariff-interval cost/)).toBeInTheDocument();
  });

  it('labels a cached snapshot when the upstream is unavailable', () => {
    renderSection({ ...statisticsFixture, stale: true });
    expect(screen.getByRole('status')).toHaveTextContent('last validated statistics snapshot');
  });

  it('hides the Efficiency insight when none is measured', () => {
    renderSection(); // fixture efficiency: null
    expect(screen.queryByText('Home-energy efficiency')).not.toBeInTheDocument();
  });

  it('shows the measured Efficiency insight when present', () => {
    renderSection({ ...statisticsFixture, efficiency: { milesDriven: 168, milesPerKwh: 4, energyKwh: 42, intervalCount: 3, vehicleId: 'car-1', from: null, to: null, scope: 'matched_home_charging' } });
    expect(screen.getByText('Home-energy efficiency')).toBeInTheDocument();
    expect(screen.getByText('4 mi/kWh')).toBeInTheDocument();
    expect(screen.getByText('42 kWh across 3 matched intervals')).toBeInTheDocument();
    expect(screen.getByText('Matched distance')).toBeInTheDocument();
    expect(screen.getByText('168 mi')).toBeInTheDocument();
  });

  it('hides the Running cost insight when none is available', () => {
    renderSection(); // fixture runningCost: null
    expect(screen.queryByText('Actual home running cost')).not.toBeInTheDocument();
  });

  it('shows the Running cost insight when present', () => {
    renderSection({
      ...statisticsFixture,
      runningCost: { costPerMile: 0.083, milesDriven: 210, costTotal: 17.4, currency: 'GBP', intervalCount: 4, scope: 'matched_actual_home_charging' },
    });
    expect(screen.getByText('Actual home running cost')).toBeInTheDocument();
    expect(screen.getByText('8.3p / mi')).toBeInTheDocument();
  });

  it('shows period-over-period deltas when a comparison is present', () => {
    // Fixture: energy 42 vs prev 35 -> +20% up; savings 8.4 vs 7.2 -> +17% up.
    renderSection();
    expect(screen.getByText('▲ 20%')).toBeInTheDocument();
    expect(screen.getByText('▲ 17%')).toBeInTheDocument();
  });

  it('omits deltas when there is no comparison', () => {
    renderSection({ ...statisticsFixture, comparison: null });
    expect(screen.queryByText(/▲|▼/)).not.toBeInTheDocument();
  });
});

describe('StatisticsSection chart metric toggle', () => {
  it('offers an Energy, Savings and Cost view', async () => {
    renderSection();
    const group = screen.getByRole('group', { name: /chart metric/i });
    const cost = within(group).getByRole('button', { name: 'Cost' });

    expect(within(group).getByRole('button', { name: 'Energy' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await userEvent.click(cost);

    expect(cost).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('Daily cost')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /daily cost bar chart/i })).toBeInTheDocument();
  });
});

describe('StatisticsSection CSV export', () => {
  it('downloads a CSV when Export is clicked', async () => {
    const createObjectURL = vi.fn(() => 'blob:fake');
    const revokeObjectURL = vi.fn();
    vi.stubGlobal('URL', { ...URL, createObjectURL, revokeObjectURL });
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => {});

    renderSection();
    await userEvent.click(screen.getByRole('button', { name: /export csv/i }));

    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(clickSpy).toHaveBeenCalledOnce();

    clickSpy.mockRestore();
    vi.unstubAllGlobals();
  });
});
