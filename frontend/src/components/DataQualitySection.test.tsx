import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { DataQualityResponse } from '../api/types';
import { dataQualityStatusLabel } from '../utils/dataQuality';
import { DataQualitySection } from './DataQualitySection';

const quality: DataQualityResponse = {
  status: 'ok',
  generatedAt: '2026-07-11T08:00:00Z',
  persistenceAvailable: true,
  actualCostExpected: true,
  consumptionConfigured: true,
  sessions: { total: 12, completed: 10, missingActualEnergy: 0, missingActualCost: 0 },
  telemetry: { unlinkedLast24h: 0 },
  consumption: { uncertainLast30d: 0, ingestedThrough: '2026-07-10T23:30:00Z' },
  daily: { completeThrough: '2026-07-10' },
  statisticsCache: { available: true, ageSeconds: 45 },
};

describe('DataQualitySection', () => {
  it('stays hidden when persistence is disabled', () => {
    const { container } = render(
      <DataQualitySection
        data={{ ...quality, persistenceAvailable: false }}
        onReviewSessions={vi.fn()}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('explains clear checks and separates freshness metadata', () => {
    render(<DataQualitySection data={quality} onReviewSessions={vi.fn()} />);

    expect(screen.getByText('No reporting gaps found')).toBeInTheDocument();
    expect(screen.getByText('Completeness checks')).toBeInTheDocument();
    expect(screen.getByText('All 10 completed sessions have measured energy.')).toBeInTheDocument();
    expect(screen.queryByText('Actual charging cost')).not.toBeInTheDocument();
    expect(screen.getByText('Data freshness')).toBeInTheDocument();
    expect(screen.getByText('Updated less than a minute ago')).toBeInTheDocument();
    expect(dataQualityStatusLabel(quality)).toBe('No issues found');
  });

  it('prioritises missing session data and opens a filtered review', async () => {
    const onReviewSessions = vi.fn();
    const attention = {
      ...quality,
      status: 'attention' as const,
      sessions: { ...quality.sessions!, missingActualEnergy: 2, missingActualCost: 1 },
    };
    render(
      <DataQualitySection data={attention} onReviewSessions={onReviewSessions} />,
    );

    expect(screen.getByText('Some reporting data needs attention')).toBeInTheDocument();
    expect(screen.getByText(/2 completed sessions are missing measured energy/i)).toBeInTheDocument();
    expect(screen.queryByText(/could not be priced/i)).not.toBeInTheDocument();
    expect(dataQualityStatusLabel(attention)).toBe('1 check needs attention');

    await userEvent.click(screen.getByRole('button', { name: /review 2 affected sessions/i }));
    expect(onReviewSessions).toHaveBeenCalledWith('missing_energy');
  });

  it('treats optional integrations as neutral when they are not configured', () => {
    render(
      <DataQualitySection
        data={{
          ...quality,
          actualCostExpected: false,
          consumptionConfigured: false,
          consumption: null,
        }}
        onReviewSessions={vi.fn()}
      />,
    );

    const energyCheck = screen.getByText('Car vs home energy').closest('li');
    expect(energyCheck).not.toBeNull();
    expect(within(energyCheck!).getByText('Not set up')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /affected session/i })).not.toBeInTheDocument();
  });

  it('shows a reassuring unavailable state without presenting false failures', () => {
    render(
      <DataQualitySection
        data={{
          ...quality,
          status: 'unavailable',
          sessions: null,
          telemetry: null,
          consumption: null,
          daily: null,
        }}
        onReviewSessions={vi.fn()}
      />,
    );

    expect(screen.getByText('Data checks are temporarily unavailable')).toBeInTheDocument();
    expect(screen.getByText(/charging and target automation are unaffected/i)).toBeInTheDocument();
    expect(dataQualityStatusLabel({ ...quality, status: 'unavailable' })).toBe('Checks unavailable');
  });
});
