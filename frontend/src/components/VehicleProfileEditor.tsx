import { useState } from 'react';
import { useSaveAction } from '../hooks/useSaveAction';

export function VehicleProfileEditor({
  vehicleId,
  vehicleName,
  value,
  min,
  max,
  onSave,
}: {
  vehicleId: string;
  vehicleName: string;
  value: { targetPercent: number; readyBy: string | null } | null;
  min: number;
  max: number;
  onSave: (
    vehicleId: string, enabled: boolean, target: number, readyBy: string | null,
  ) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [targetDraft, setTargetDraft] = useState(String(value?.targetPercent ?? 80));
  const [readyBy, setReadyBy] = useState(value?.readyBy ?? '');
  const { saving, error, saved, run, reset } = useSaveAction();
  const target = Number(targetDraft);
  const valid = Number.isFinite(target) && target >= min && target <= max;

  const save = async (enabled: boolean) => {
    if (await run(() => onSave(vehicleId, enabled, target, enabled ? readyBy || null : null))) {
      setEditing(false);
    }
  };

  if (value == null && !editing) {
    return (
      <div className="vehicle-profile-editor">
        <div>
          <strong>{vehicleName} profile</strong>
          <p className="field-hint">Use vehicle-specific charging defaults.</p>
        </div>
        <button type="button" className="ghost-button" onClick={() => { reset(); setEditing(true); }}>
          Create profile
        </button>
        {saved && <span className="save-confirm" role="status">Removed ✓</span>}
      </div>
    );
  }

  return (
    <div className="vehicle-profile-editor active">
      <div className="vehicle-profile-title">
        <strong>{vehicleName} profile</strong>
        <p className="field-hint">Applied when Bluelink identifies this vehicle; trip mode still wins.</p>
      </div>
      <label>
        <span>Target</span>
        <input
          type="number"
          min={min}
          max={max}
          step={5}
          value={targetDraft}
          disabled={saving}
          onChange={(event) => setTargetDraft(event.target.value)}
          aria-label={`${vehicleName} profile target percent`}
        />
        <span>%</span>
      </label>
      <label>
        <span>Ready by</span>
        <input
          type="time"
          value={readyBy}
          disabled={saving}
          onChange={(event) => setReadyBy(event.target.value)}
          aria-label={`${vehicleName} profile ready-by time`}
        />
        <span className="field-hint">optional</span>
      </label>
      <div className="vehicle-profile-actions">
        <button type="button" className="save" disabled={saving || !valid} onClick={() => void save(true)}>
          {saving ? 'Saving…' : value ? 'Update profile' : 'Save profile'}
        </button>
        <button
          type="button"
          className="cancel"
          disabled={saving}
          onClick={() => value ? void save(false) : setEditing(false)}
        >
          {value ? 'Remove profile' : 'Back'}
        </button>
      </div>
      {error && <div className="target-error" role="alert">Couldn’t update vehicle profile. Try again.</div>}
    </div>
  );
}
