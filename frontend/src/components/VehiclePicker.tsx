import { useState } from 'react';
import type { Vehicle } from '../api/types';

interface Props {
  vehicles: Vehicle[];
  /** Selected vehicle id, or null when using the first. */
  selected: string | null;
  onSelect: (id: string) => Promise<void>;
}

/** Account vehicle selector — rendered by the dashboard only when >1 vehicle. */
export function VehiclePicker({ vehicles, selected, onSelect }: Props) {
  const [saving, setSaving] = useState(false);
  const current = selected ?? vehicles[0]?.id ?? '';

  const handle = async (id: string) => {
    setSaving(true);
    try {
      await onSelect(id);
    } finally {
      setSaving(false);
    }
  };

  return (
    <label className="vehicle-picker">
      <span>Vehicle</span>
      <select
        value={current}
        disabled={saving}
        onChange={(e) => void handle(e.target.value)}
        aria-label="Vehicle"
      >
        {vehicles.map((v) => (
          <option key={v.id} value={v.id}>
            {v.name ?? v.model ?? v.id}
          </option>
        ))}
      </select>
    </label>
  );
}
