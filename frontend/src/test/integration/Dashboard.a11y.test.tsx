import axe from 'axe-core';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Dashboard } from '../../components/Dashboard';

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
});
