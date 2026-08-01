import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { TomorrowOverrideEditor } from './TomorrowOverrideEditor';

describe('TomorrowOverrideEditor', () => {
  it('creates a temporary target and departure plan', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(
      <TomorrowOverrideEditor
        value={{ enabled: false, date: null, targetPercent: null, readyBy: null }}
        baseTarget={80}
        min={10}
        max={100}
        onSave={onSave}
      />,
    );

    await userEvent.click(screen.getByRole('button', { name: /plan tomorrow/i }));
    await userEvent.clear(screen.getByLabelText(/tomorrow target percent/i));
    await userEvent.type(screen.getByLabelText(/tomorrow target percent/i), '95');
    await userEvent.type(screen.getByLabelText(/tomorrow ready-by/i), '06:30');
    await userEvent.click(screen.getByRole('button', { name: /save for tomorrow/i }));

    expect(onSave).toHaveBeenCalledWith(true, 95, '06:30');
  });

  it('cancels an active dated plan', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(
      <TomorrowOverrideEditor
        value={{ enabled: true, date: '2026-06-03', targetPercent: 90, readyBy: null }}
        baseTarget={80}
        min={10}
        max={100}
        onSave={onSave}
      />,
    );

    await userEvent.click(screen.getByRole('button', { name: /cancel tomorrow plan/i }));
    expect(onSave).toHaveBeenCalledWith(false, 90, null);
  });
});
