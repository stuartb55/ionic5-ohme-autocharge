import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ConnectionBadge } from './ConnectionBadge';

describe('ConnectionBadge', () => {
  it('renders the friendly status label', () => {
    render(<ConnectionBadge status="charging" />);
    expect(screen.getByText('Charging')).toBeInTheDocument();
  });

  it('applies a status-specific class', () => {
    const { container } = render(<ConnectionBadge status="paused" />);
    expect(container.querySelector('.badge.paused')).toBeTruthy();
  });
});
