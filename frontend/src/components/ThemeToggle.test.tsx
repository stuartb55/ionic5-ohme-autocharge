import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { ThemeToggle } from './ThemeToggle';

describe('ThemeToggle', () => {
  it('defaults to system and applies it to <html>', () => {
    render(<ThemeToggle />);
    expect(screen.getByRole('button', { name: /system theme/i })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    // matchMedia stub reports light.
    expect(document.documentElement.dataset.theme).toBe('light');
  });

  it('switches to dark, persists, and updates <html data-theme>', async () => {
    render(<ThemeToggle />);
    await userEvent.click(screen.getByRole('button', { name: /dark theme/i }));

    expect(screen.getByRole('button', { name: /dark theme/i })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(localStorage.getItem('autocharge-theme')).toBe('dark');
  });
});
