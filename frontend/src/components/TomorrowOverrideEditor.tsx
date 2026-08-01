import { useState } from 'react';
import type { StatusResponse } from '../api/types';
import { useSaveAction } from '../hooks/useSaveAction';

type TomorrowOverride = StatusResponse['config']['tomorrowOverride'];

function dateLabel(value: string | null): string {
  if (!value) return 'tomorrow';
  return new Intl.DateTimeFormat(undefined, {
    weekday: 'long',
    day: 'numeric',
    month: 'short',
    timeZone: 'UTC',
  }).format(new Date(`${value}T12:00:00Z`));
}

export function TomorrowOverrideEditor({
  value,
  baseTarget,
  min,
  max,
  onSave,
}: {
  value: TomorrowOverride;
  baseTarget: number;
  min: number;
  max: number;
  onSave: (enabled: boolean, target: number, readyBy: string | null) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [targetDraft, setTargetDraft] = useState(String(value.targetPercent ?? baseTarget));
  const [readyBy, setReadyBy] = useState(value.readyBy ?? '');
  const { saving, error, saved, run, reset } = useSaveAction();
  const parsedTarget = Number(targetDraft);
  const valid = Number.isFinite(parsedTarget) && parsedTarget >= min && parsedTarget <= max;

  const save = async (enabled: boolean) => {
    if (await run(() => onSave(enabled, parsedTarget, enabled ? readyBy || null : null))) {
      setEditing(false);
    }
  };

  if (!value.enabled && !editing) {
    return (
      <div className="tomorrow-override-editor">
        <div>
          <strong>Tomorrow only</strong>
          <p className="field-hint">Use a different target or departure time for tomorrow.</p>
        </div>
        <button type="button" className="ghost-button" onClick={() => { reset(); setEditing(true); }}>
          Plan tomorrow
        </button>
        {saved && <span className="save-confirm" role="status">Cancelled ✓</span>}
      </div>
    );
  }

  return (
    <div className={`tomorrow-override-editor ${value.enabled ? 'active' : ''}`}>
      <div className="tomorrow-override-title">
        <strong>{value.enabled ? `Plan active for ${dateLabel(value.date)}` : 'Plan tomorrow'}</strong>
        <p className="field-hint">
          Effective now for overnight charging, then clears after the selected day.
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
          aria-label="Tomorrow target percent"
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
          aria-label="Tomorrow ready-by time"
        />
        <span className="field-hint">optional</span>
      </label>
      <div className="tomorrow-override-actions">
        <button
          type="button"
          className="save"
          disabled={saving || !valid}
          onClick={() => void save(true)}
        >
          {saving ? 'Saving…' : value.enabled ? 'Update plan' : 'Save for tomorrow'}
        </button>
        <button
          type="button"
          className="cancel"
          disabled={saving}
          onClick={() => value.enabled ? void save(false) : setEditing(false)}
        >
          {value.enabled ? 'Cancel tomorrow plan' : 'Back'}
        </button>
      </div>
      {error && <div className="target-error" role="alert">Couldn’t update tomorrow’s plan. Try again.</div>}
    </div>
  );
}
