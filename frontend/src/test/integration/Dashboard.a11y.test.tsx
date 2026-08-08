import axe from 'axe-core';
import { render, screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { Dashboard } from '../../components/Dashboard';
import { server } from '../mocks/server';

describe('Dashboard accessibility', () => {
  it('has no automatically detectable accessibility violations', async () => {
    const { container } = render(<Dashboard />);
    await screen.findByRole('heading', { name: /statistics & savings/i });

    const results = await axe.run(container, {
      // happy-dom has no layout/paint engine, so contrast needs browser-based
      // verification; all structural ARIA and semantic rules still run here.
      rules: { 'color-contrast': { enabled: false } },
    });

    expect(results.violations.map(({ id, nodes }) => ({ id, nodes: nodes.length }))).toEqual([]);
  });

  it('keeps expanded diagnostics structurally accessible', async () => {
    server.use(
      http.get('*/api/data-quality', () =>
        HttpResponse.json({
          status: 'attention',
          generatedAt: '2026-07-11T08:00:00Z',
          persistenceAvailable: true,
          actualCostExpected: true,
          consumptionConfigured: true,
          sessions: {
            total: 12,
            completed: 10,
            missingActualEnergy: 1,
            missingActualCost: 1,
          },
          telemetry: { unlinkedLast24h: 0 },
          consumption: { uncertainLast30d: 0, ingestedThrough: '2026-07-10T23:30:00Z', totalLast30d: 0, importKwhLast30d: 0, unattributedKwhLast30d: 0, lastUncertainDate: null, needsAttention: false },
          daily: { completeThrough: '2026-07-10' },
          statisticsCache: { available: true, ageSeconds: 45 },
        }),
      ),
    );

    const { container } = render(<Dashboard />);
    await screen.findByText('Some reporting data needs attention');

    const results = await axe.run(container, {
      rules: { 'color-contrast': { enabled: false } },
    });

    expect(results.violations.map(({ id, nodes }) => ({ id, nodes: nodes.length }))).toEqual([]);
  });
});
