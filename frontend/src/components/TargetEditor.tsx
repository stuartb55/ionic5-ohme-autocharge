import { useEffect, useState } from 'react';

interface Props {
  /** The current target from the server. */
  value: number;
  min?: number;
  max?: number;
  step?: number;
  /** Persist a new target. Should reject on failure so the editor can show an error. */
  onSave: (target: number) => Promise<void>;
}

const clamp = (n: number, min: number, max: number) => Math.min(max, Math.max(min, n));

/**
 * Inline stepper for the charge target. Edits are local until saved, so a
 * background poll refreshing `value` can't clobber an in-progress edit.
 */
export function TargetEditor({ value, min = 10, max = 100, step = 5, onSave }: Props) {
  const [draft, setDraft] = useState(value);
  const [edited, setEdited] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(false);

  // Keep the draft in sync with the server value, but only while the user has no
  // pending edit — otherwise a poll would overwrite what they're changing.
  useEffect(() => {
    if (!edited) setDraft(value);
  }, [value, edited]);

  const change = (delta: number) => {
    setError(false);
    setEdited(true);
    setDraft((d) => clamp(d + delta, min, max));
  };

  const dirty = draft !== value;

  const save = async () => {
    setSaving(true);
    setError(false);
    try {
      await onSave(draft);
      setEdited(false);
    } catch {
      setError(true);
    } finally {
      setSaving(false);
    }
  };

  const cancel = () => {
    setEdited(false);
    setError(false);
    setDraft(value);
  };

  return (
    <div className="target-editor">
      <div className="target-stepper" role="group" aria-label="Charge target">
        <button
          type="button"
          className="step"
          onClick={() => change(-step)}
          disabled={saving || draft <= min}
          aria-label="Decrease target"
        >
          −
        </button>
        <span className="target-value" aria-live="polite">
          Target {draft}%
        </span>
        <button
          type="button"
          className="step"
          onClick={() => change(step)}
          disabled={saving || draft >= max}
          aria-label="Increase target"
        >
          +
        </button>
      </div>

      {dirty && (
        <div className="target-actions">
          <button type="button" className="save" onClick={save} disabled={saving}>
            {saving ? 'Saving…' : `Save ${draft}%`}
          </button>
          <button type="button" className="cancel" onClick={cancel} disabled={saving}>
            Cancel
          </button>
        </div>
      )}

      {error && (
        <div className="target-error" role="alert">
          Couldn’t update target. Try again.
        </div>
      )}
    </div>
  );
}
