import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { Vehicle } from '../api/types';
import { VehiclePicker } from './VehiclePicker';

const FLEET: Vehicle[] = [
  { id: 'car-1', name: 'IONIQ 5', model: 'IONIQ 5' },
  { id: 'car-2', name: 'Kona', model: 'Kona' },
];

describe('VehiclePicker', () => {
  it('lists vehicles and selects the current one', () => {
    render(<VehiclePicker vehicles={FLEET} selected="car-2" onSelect={vi.fn()} />);
    expect((screen.getByLabelText('Vehicle') as HTMLSelectElement).value).toBe('car-2');
    expect(screen.getByRole('option', { name: 'IONIQ 5' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Kona' })).toBeInTheDocument();
  });

  it('falls back to the first vehicle when none selected', () => {
    render(<VehiclePicker vehicles={FLEET} selected={null} onSelect={vi.fn()} />);
    expect((screen.getByLabelText('Vehicle') as HTMLSelectElement).value).toBe('car-1');
  });

  it('calls onSelect with the chosen id', async () => {
    const onSelect = vi.fn().mockResolvedValue(undefined);
    render(<VehiclePicker vehicles={FLEET} selected="car-1" onSelect={onSelect} />);
    await userEvent.selectOptions(screen.getByLabelText('Vehicle'), 'car-2');
    expect(onSelect).toHaveBeenCalledWith('car-2');
  });
});
