import { useState } from 'react';

interface Props {
  /** Current ready-by time ("HH:MM") from the server, or null when unset. */
  value: string | null;
  /** Persist a new time, or null to clear it. Rejects on failure. */
  onSave: (value: string | null) => Promise<void>;
}

/**
 * Optional "ready-by" departure time. Edits are local until saved, so a
 * background poll refreshing `value` can't clobber an in-progress edit.
 */
export function ReadyByEditor({ value, onSave }: Props) {
  const [draft, setDraft] = useState(value ?? '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(false);

  // Keep the draft synced to the server value while the user isn't editing.
  const [prevValue, setPrevValue] = useState(value);
  const [edited, setEdited] = useState(false);
  if (value !== prevValue) {
    setPrevValue(value);
    if (!edited) setDraft(value ?? '');
  }

  const current = value ?? '';
  const dirty = draft !== current;

  const run = async (next: string | null) => {
    setSaving(true);
    setError(false);
    try {
      await onSave(next);
      setEdited(false);
    } catch {
      setError(true);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="ready-by-editor">
      <label className="ready-by-field">
        <span>Ready by</span>
        <input
          type="time"
          value={draft}
          disabled={saving}
          onChange={(e) => {
            setEdited(true);
            setError(false);
            setDraft(e.target.value);
          }}
          aria-label="Ready-by time"
        />
      </label>
      <div className="ready-by-actions">
        {dirty && draft !== '' && (
          <button type="button" className="save" onClick={() => run(draft)} disabled={saving}>
            {saving ? 'Saving…' : 'Save'}
          </button>
        )}
        {value != null && (
          <button
            type="button"
            className="cancel"
            onClick={() => {
              setDraft('');
              void run(null);
            }}
            disabled={saving}
          >
            Clear
          </button>
        )}
      </div>
      {error && (
        <div className="target-error" role="alert">
          Couldn’t update ready-by time. Try again.
        </div>
      )}
    </div>
  );
}
