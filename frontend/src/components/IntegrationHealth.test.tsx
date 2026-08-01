import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { IntegrationHealth } from './IntegrationHealth';

describe('IntegrationHealth', () => {
  it('summarises action-needed and optional integrations', () => {
    render(
      <IntegrationHealth data={{ integrations: [
        { id: 'ohme', name: 'Ohme charger', configured: true, status: 'healthy', detail: 'Connected.' },
        { id: 'history', name: 'Charging history', configured: true, status: 'attention', detail: 'Postgres unavailable.' },
        { id: 'tariff', name: 'Octopus tariff', configured: false, status: 'disabled', detail: 'Set tariff variables.' },
      ] }} />,
    );

    expect(screen.getByText('1 action needed')).toBeInTheDocument();
    expect(screen.getByText('Charging history')).toBeInTheDocument();
    expect(screen.getByText('Action needed')).toBeInTheDocument();
    expect(screen.getByText('Optional')).toBeInTheDocument();
  });
});
