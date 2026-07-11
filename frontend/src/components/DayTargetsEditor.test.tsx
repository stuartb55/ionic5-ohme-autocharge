import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { DayTargetsEditor } from './DayTargetsEditor';

describe('DayTargetsEditor', () => {
  it('saves the full map of chosen day overrides', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<DayTargetsEditor value={{}} base={80} min={10} max={100} onSave={onSave} />);

    // Set Friday (index 4) to 100%.
    await userEvent.selectOptions(screen.getByLabelText('Fri target'), '100');
    await userEvent.click(screen.getByRole('button', { name: /save per-day/i }));

    expect(onSave).toHaveBeenCalledWith({ 4: 100 });
  });

  it('drops a day set back to Base', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<DayTargetsEditor value={{ '4': 100 }} base={80} min={10} max={100} onSave={onSave} />);

    await userEvent.selectOptions(screen.getByLabelText('Fri target'), '');
    await userEvent.click(screen.getByRole('button', { name: /save per-day/i }));

    expect(onSave).toHaveBeenCalledWith({});
  });

  it('shows no Save button until edited', () => {
    render(<DayTargetsEditor value={{}} base={80} min={10} max={100} onSave={vi.fn()} />);
    expect(screen.queryByRole('button', { name: /save per-day/i })).not.toBeInTheDocument();
  });

  it('signals active overrides with a count badge on the summary', () => {
    render(
      <DayTargetsEditor value={{ '0': 65, '4': 100 }} base={80} min={10} max={100} onSave={vi.fn()} />,
    );
    expect(screen.getByText(/2 overrides/i)).toBeInTheDocument();
  });

  it('has no override badge when none are set', () => {
    const { container } = render(
      <DayTargetsEditor value={{}} base={80} min={10} max={100} onSave={vi.fn()} />,
    );
    expect(container.querySelector('.day-targets-count')).not.toBeInTheDocument();
  });
});
