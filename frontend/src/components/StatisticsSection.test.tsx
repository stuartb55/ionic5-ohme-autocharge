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
  });

  it('hides the Efficiency insight when none is measured', () => {
    renderSection(); // fixture efficiency: null
    expect(screen.queryByText('Efficiency')).not.toBeInTheDocument();
  });

  it('shows the measured Efficiency insight when present', () => {
    renderSection({ ...statisticsFixture, efficiency: { milesDriven: 168, milesPerKwh: 4 } });
    expect(screen.getByText('Efficiency')).toBeInTheDocument();
    expect(screen.getByText('4 mi/kWh')).toBeInTheDocument();
    expect(screen.getByText('over 168 mi')).toBeInTheDocument();
    // The range estimate uses the measured rate, not the assumed 3.5.
    expect(screen.getByText('@ 4 mi/kWh')).toBeInTheDocument();
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
