import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { SohHistoryResponse } from '../api/types';
import { SohTrendSection } from './SohTrendSection';

function resp(overrides: Partial<SohHistoryResponse>): SohHistoryResponse {
  return { enabled: true, history: [], ...overrides };
}

describe('SohTrendSection', () => {
  it('renders nothing when disabled', () => {
    const { container } = render(<SohTrendSection data={resp({ enabled: false })} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing with no readings', () => {
    const { container } = render(<SohTrendSection data={resp({ history: [] })} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows the current value but no line for a single reading', () => {
    render(
      <SohTrendSection data={resp({ history: [{ date: '2026-01-01T00:00:00Z', sohPercent: 100 }] })} />,
    );
    expect(screen.getByText('100%')).toBeInTheDocument();
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(screen.getByText(/no change recorded yet/i)).toBeInTheDocument();
  });

  it('plots a trend and shows the change since the first reading', () => {
    render(
      <SohTrendSection
        data={resp({
          history: [
            { date: '2026-01-01T00:00:00Z', sohPercent: 100 },
            { date: '2026-03-01T00:00:00Z', sohPercent: 99 },
            { date: '2026-06-01T00:00:00Z', sohPercent: 97 },
          ],
        })}
      />,
    );
    expect(screen.getByText('97%')).toBeInTheDocument();
    // 97 − 100 = −3, shown as a downward change.
    expect(screen.getByText(/▼ 3% since/)).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /battery health trend, now 97%/i })).toBeInTheDocument();
  });
});
