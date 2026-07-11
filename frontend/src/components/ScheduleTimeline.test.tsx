import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ScheduleTimeline } from './ScheduleTimeline';
import { scheduleFixture } from '../test/fixtures';

describe('ScheduleTimeline', () => {
  it('renders an SVG with one active rect per slot plus the idle track', () => {
    const { container } = render(<ScheduleTimeline slots={scheduleFixture.slots} />);
    const rects = container.querySelectorAll('rect');
    // idle track (1) + one per slot (2)
    expect(rects.length).toBe(1 + scheduleFixture.slots.length);
  });

  it('renders nothing when there are no slots', () => {
    const { container } = render(<ScheduleTimeline slots={[]} />);
    expect(container.querySelector('svg')).toBeNull();
  });

  it('marks the current position and active charging window', () => {
    const { container } = render(
      <ScheduleTimeline slots={scheduleFixture.slots} now={new Date('2026-06-02T02:00:00+01:00')} />,
    );
    expect(container.querySelector('.timeline-now')).not.toBeNull();
    expect(container.querySelector('.timeline-segment.current')).not.toBeNull();
  });
});
