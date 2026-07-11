import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { DataQualityResponse } from '../api/types';
import { DataQualitySection } from './DataQualitySection';

const quality: DataQualityResponse = {
  status: 'ok',
  generatedAt: '2026-07-11T08:00:00Z',
  persistenceAvailable: true,
  actualCostExpected: true,
  sessions: { total: 12, completed: 10, missingActualEnergy: 0, missingActualCost: 0 },
  telemetry: { unlinkedLast24h: 0 },
  consumption: { uncertainLast30d: 0, ingestedThrough: '2026-07-10T23:30:00Z' },
  daily: { completeThrough: '2026-07-10' },
  statisticsCache: { available: true, ageSeconds: 45 },
};

describe('DataQualitySection', () => {
  it('stays hidden when persistence is disabled', () => {
    const { container } = render(
      <DataQualitySection data={{ ...quality, persistenceAvailable: false }} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('shows clear checks with their coverage', () => {
    render(<DataQualitySection data={quality} />);
    expect(screen.getByText('Data quality')).toBeInTheDocument();
    expect(screen.getByText('All checks clear')).toBeInTheDocument();
    expect(screen.getByText('10 completed sessions checked')).toBeInTheDocument();
    expect(screen.getByText('Statistics 45s old')).toBeInTheDocument();
  });

  it('highlights missing session data and links to history', () => {
    render(
      <DataQualitySection
        data={{
          ...quality,
          status: 'attention',
          sessions: { ...quality.sessions!, missingActualEnergy: 2, missingActualCost: 1 },
        }}
      />,
    );
    expect(screen.getByText('Review needed')).toBeInTheDocument();
    expect(screen.getByText('2 missing sessions')).toBeInTheDocument();
    expect(screen.getByText('1 missing session')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /review affected/i })).toHaveAttribute(
      'href',
      '#sessions-heading',
    );
  });
});
