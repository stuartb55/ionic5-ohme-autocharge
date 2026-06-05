import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { TargetEditor } from './TargetEditor';

describe('TargetEditor', () => {
  it('shows the current target and no actions until edited', () => {
    render(<TargetEditor value={80} onSave={vi.fn()} />);
    expect(screen.getByText('Target 80%')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /save/i })).not.toBeInTheDocument();
  });

  it('steps the draft and saves the new value', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<TargetEditor value={80} onSave={onSave} step={5} />);

    await userEvent.click(screen.getByRole('button', { name: /increase target/i }));
    expect(screen.getByText('Target 85%')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /save 85%/i }));
    expect(onSave).toHaveBeenCalledWith(85);
  });

  it('clamps at the max and disables the increase button', async () => {
    render(<TargetEditor value={100} onSave={vi.fn()} />);
    expect(screen.getByRole('button', { name: /increase target/i })).toBeDisabled();
  });

  it('cancel reverts the draft to the server value', async () => {
    render(<TargetEditor value={80} onSave={vi.fn()} />);
    await userEvent.click(screen.getByRole('button', { name: /decrease target/i }));
    expect(screen.getByText('Target 75%')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /cancel/i }));
    expect(screen.getByText('Target 80%')).toBeInTheDocument();
  });

  it('surfaces an error when saving fails', async () => {
    const onSave = vi.fn().mockRejectedValue(new Error('boom'));
    render(<TargetEditor value={80} onSave={onSave} />);
    await userEvent.click(screen.getByRole('button', { name: /increase target/i }));
    await userEvent.click(screen.getByRole('button', { name: /save/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn’t update target/i);
  });
});
