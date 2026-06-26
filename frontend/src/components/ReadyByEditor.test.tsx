import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ReadyByEditor } from './ReadyByEditor';

describe('ReadyByEditor', () => {
  it('saves a chosen time', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<ReadyByEditor value={null} onSave={onSave} />);

    await userEvent.type(screen.getByLabelText(/ready-by time/i), '07:30');
    await userEvent.click(screen.getByRole('button', { name: /save/i }));

    expect(onSave).toHaveBeenCalledWith('07:30');
  });

  it('clears the time with null when set', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<ReadyByEditor value="06:15" onSave={onSave} />);

    await userEvent.click(screen.getByRole('button', { name: /clear/i }));

    expect(onSave).toHaveBeenCalledWith(null);
  });

  it('offers no Clear button when unset', () => {
    render(<ReadyByEditor value={null} onSave={vi.fn()} />);
    expect(screen.queryByRole('button', { name: /clear/i })).not.toBeInTheDocument();
  });

  it('hides Clear for a non-clearable (Ohme-sourced) value', () => {
    render(<ReadyByEditor value="07:00" clearable={false} onSave={vi.fn()} />);
    expect(screen.queryByRole('button', { name: /clear/i })).not.toBeInTheDocument();
    // The time still shows and remains editable.
    expect((screen.getByLabelText(/ready-by time/i) as HTMLInputElement).value).toBe('07:00');
  });

  it('shows an error when saving fails', async () => {
    const onSave = vi.fn().mockRejectedValue(new Error('nope'));
    render(<ReadyByEditor value={null} onSave={onSave} />);

    await userEvent.type(screen.getByLabelText(/ready-by time/i), '08:00');
    await userEvent.click(screen.getByRole('button', { name: /save/i }));

    expect(await screen.findByRole('alert')).toBeInTheDocument();
  });
});
