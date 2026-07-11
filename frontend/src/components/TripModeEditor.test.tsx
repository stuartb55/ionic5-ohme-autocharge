import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { TripModeEditor } from './TripModeEditor';

describe('TripModeEditor', () => {
  it('activates a one-session target with an optional departure time', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(
      <TripModeEditor
        value={{ enabled: false, targetPercent: null, readyBy: null }}
        min={10}
        max={100}
        onSave={onSave}
      />,
    );

    await userEvent.click(screen.getByRole('button', { name: /plan trip charge/i }));
    const target = screen.getByLabelText(/trip target percent/i);
    await userEvent.clear(target);
    await userEvent.type(target, '95');
    await userEvent.type(screen.getByLabelText(/trip ready-by time/i), '06:30');
    await userEvent.click(screen.getByRole('button', { name: /activate/i }));

    expect(onSave).toHaveBeenCalledWith(true, 95, '06:30');
  });

  it('clearly labels and cancels an active override', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(
      <TripModeEditor
        value={{ enabled: true, targetPercent: 100, readyBy: '05:45' }}
        min={10}
        max={100}
        onSave={onSave}
      />,
    );

    expect(screen.getByText(/clears automatically when the car unplugs/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /cancel trip mode/i }));
    expect(onSave).toHaveBeenCalledWith(false, 100, null);
  });

  it('keeps the planner open and reports a failed save', async () => {
    const onSave = vi.fn().mockRejectedValue(new Error('offline'));
    render(
      <TripModeEditor
        value={{ enabled: false, targetPercent: null, readyBy: null }}
        min={10}
        max={100}
        onSave={onSave}
      />,
    );

    await userEvent.click(screen.getByRole('button', { name: /plan trip charge/i }));
    await userEvent.click(screen.getByRole('button', { name: /activate/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn’t update trip mode/i);
    expect(screen.getByLabelText(/trip target percent/i)).toBeInTheDocument();
  });
});
