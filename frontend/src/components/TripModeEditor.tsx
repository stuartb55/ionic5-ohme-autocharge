import { useState } from 'react';
import type { StatusResponse } from '../api/types';
import { useSaveAction } from '../hooks/useSaveAction';

type TripMode = StatusResponse['config']['tripMode'];

export function TripModeEditor({
  value,
  min,
  max,
  onSave,
}: {
  value: TripMode;
  min: number;
  max: number;
  onSave: (enabled: boolean, target: number, readyBy: string | null) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [targetDraft, setTargetDraft] = useState(String(value.targetPercent ?? 100));
  const [readyBy, setReadyBy] = useState(value.readyBy ?? '');
  const { saving, error, saved, run, reset } = useSaveAction();
  const parsedTarget = Number(targetDraft);
  const target = Number.isFinite(parsedTarget)
    ? Math.min(max, Math.max(min, parsedTarget))
    : 100;

  const activate = async () => {
    if (await run(() => onSave(true, target, readyBy || null))) setEditing(false);
  };
  const cancel = async () => {
    if (await run(() => onSave(false, target, null))) setEditing(false);
  };
  const close = () => {
    if (value.enabled) void cancel();
    else setEditing(false);
  };

  if (!value.enabled && !editing) {
    return (
      <div className="trip-mode-editor">
        <div>
          <strong>Trip charge</strong>
          <p className="field-hint">Temporarily use a higher target for the next charge.</p>
        </div>
        <button type="button" className="ghost-button" onClick={() => { reset(); setEditing(true); }}>
          Plan trip charge
        </button>
        {saved && <span className="save-confirm" role="status">Cancelled ✓</span>}
      </div>
    );
  }

  return (
    <div className={`trip-mode-editor ${value.enabled ? 'active' : ''}`}>
      <div className="trip-mode-title">
        <strong>{value.enabled ? 'Trip mode active' : 'Plan a trip charge'}</strong>
        <p className="field-hint">
          {value.enabled ? 'This override clears automatically when the car unplugs.' : 'Applies to the current or next physical charging session only.'}
        </p>
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
          aria-label="Trip target percent"
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
          aria-label="Trip ready-by time"
        />
        <span className="field-hint">optional</span>
      </label>
      <div className="trip-mode-actions">
        <button
          type="button"
          className="save"
          disabled={saving || targetDraft === '' || parsedTarget < min || parsedTarget > max}
          onClick={() => void activate()}
        >
          {saving ? 'Saving…' : value.enabled ? 'Update trip' : 'Activate'}
        </button>
        <button type="button" className="cancel" disabled={saving} onClick={close}>
          {value.enabled ? 'Cancel trip mode' : 'Back'}
        </button>
      </div>
      {error && <div className="target-error" role="alert">Couldn’t update trip mode. Try again.</div>}
    </div>
  );
}
