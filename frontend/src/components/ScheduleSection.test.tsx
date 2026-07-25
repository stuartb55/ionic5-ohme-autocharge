import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { scheduleFixture } from '../test/fixtures';
import { ScheduleSection } from './ScheduleSection';

describe('ScheduleSection', () => {
  it('derives the first and final times from unsorted upstream slots', () => {
    render(
      <ScheduleSection schedule={{ ...scheduleFixture, slots: [...scheduleFixture.slots].reverse() }} />,
    );

    const summary = screen.getByLabelText('Charge plan summary');
    expect(within(summary).getByText('01:00')).toBeInTheDocument();
    expect(within(summary).getByText('05:00')).toBeInTheDocument();
    expect(within(summary).getByText('22.2 kWh')).toBeInTheDocument();
  });

  it('keeps every charging window visible without a disclosure interaction', () => {
    const { container } = render(<ScheduleSection schedule={scheduleFixture} />);

    const windows = screen.getByRole('region', { name: 'Charging windows' });
    expect(within(windows).getByText('01:00 – 03:30')).toBeVisible();
    expect(within(windows).getByText('04:30 – 05:00')).toBeVisible();
    expect(within(windows).getByText('Next window')).toBeVisible();
    expect(container.querySelector('details')).not.toBeInTheDocument();
  });
});
