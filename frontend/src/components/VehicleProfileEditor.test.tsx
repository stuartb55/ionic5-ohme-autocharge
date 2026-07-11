import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { VehicleProfileEditor } from './VehicleProfileEditor';

describe('VehicleProfileEditor', () => {
  it('creates vehicle-specific target and departure defaults', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(
      <VehicleProfileEditor
        vehicleId="car-2"
        vehicleName="Kona"
        value={null}
        min={10}
        max={100}
        onSave={onSave}
      />,
    );
    await userEvent.click(screen.getByRole('button', { name: /create profile/i }));
    fireEvent.change(screen.getByLabelText(/kona profile target/i), { target: { value: '95' } });
    fireEvent.change(screen.getByLabelText(/kona profile ready-by/i), { target: { value: '05:45' } });
    await userEvent.click(screen.getByRole('button', { name: /save profile/i }));
    expect(onSave).toHaveBeenCalledWith('car-2', true, 95, '05:45');
  });

  it('labels profile precedence and can remove it', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(
      <VehicleProfileEditor
        vehicleId="car-2"
        vehicleName="Kona"
        value={{ targetPercent: 90, readyBy: null }}
        min={10}
        max={100}
        onSave={onSave}
      />,
    );
    expect(screen.getByText(/trip mode still wins/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /remove profile/i }));
    expect(onSave).toHaveBeenCalledWith('car-2', false, 90, null);
  });

  it('reports a failed profile save without discarding the edit', async () => {
    render(
      <VehicleProfileEditor
        vehicleId="car-1"
        vehicleName="IONIQ 5"
        value={null}
        min={10}
        max={100}
        onSave={vi.fn().mockRejectedValue(new Error('offline'))}
      />,
    );
    await userEvent.click(screen.getByRole('button', { name: /create profile/i }));
    await userEvent.click(screen.getByRole('button', { name: /save profile/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn’t update vehicle profile/i);
    expect(screen.getByLabelText(/ioniq 5 profile target/i)).toBeInTheDocument();
  });
});
