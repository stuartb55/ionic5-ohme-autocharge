import { useState } from 'react';
import { useSaveAction } from '../hooks/useSaveAction';

interface Props {
  /** Current ready-by time ("HH:MM") from the server, or null when unset. */
  value: string | null;
  /**
   * Whether the value is a clearable local override. When false (e.g. the time
   * came from Ohme's own rule), the Clear button is hidden — there's nothing of
   * ours to clear; editing the time creates an override instead.
   */
  clearable?: boolean;
  /** Persist a new time, or null to clear it. Rejects on failure. */
  onSave: (value: string | null) => Promise<void>;
}

/**
 * Optional "ready-by" departure time. Edits are local until saved, so a
 * background poll refreshing `value` can't clobber an in-progress edit.
 */
export function ReadyByEditor({ value, clearable = true, onSave }: Props) {
  const [draft, setDraft] = useState(value ?? '');
  const { saving, error, saved, run, reset } = useSaveAction();

  // Keep the draft synced to the server value while the user isn't editing.
  const [prevValue, setPrevValue] = useState(value);
  const [edited, setEdited] = useState(false);
  if (value !== prevValue) {
    setPrevValue(value);
    if (!edited) setDraft(value ?? '');
  }

  const current = value ?? '';
  // Guard on `edited` so a successful save hides the Save button and reveals the
  // "Saved ✓" confirmation immediately, before the next poll refreshes `value`.
  const dirty = edited && draft !== current;

  const run_ = async (next: string | null) => {
    if (await run(() => onSave(next))) setEdited(false);
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
            reset();
            setDraft(e.target.value);
          }}
          aria-label="Ready-by time"
        />
      </label>
      <div className="ready-by-actions">
        {dirty && draft !== '' && (
          <button type="button" className="save" onClick={() => run_(draft)} disabled={saving}>
            {saving ? 'Saving…' : 'Save'}
          </button>
        )}
        {value != null && clearable && (
          <button
            type="button"
            className="cancel"
            onClick={() => {
              setDraft('');
              void run_(null);
            }}
            disabled={saving}
          >
            Clear
          </button>
        )}
        {saved && !dirty && (
          <span className="save-confirm" role="status">
            Saved ✓
          </span>
        )}
      </div>
      {/* Clarify where a pre-filled time came from: Ohme's own rule vs the user's
          override (only the latter has a Clear button). */}
      {value != null && !dirty && (
        <p className="field-hint">{clearable ? 'Your override' : 'From Ohme’s schedule'}</p>
      )}
      {error && (
        <div className="target-error" role="alert">
          Couldn’t update ready-by time. Try again.
        </div>
      )}
    </div>
  );
}
