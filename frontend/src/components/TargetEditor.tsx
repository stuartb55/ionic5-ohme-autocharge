import { useState } from 'react';
import { useSaveAction } from '../hooks/useSaveAction';

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
 * background poll refreshing `value` can't clobber an in-progress edit. The
 * value is tappable to type an exact percent (faster than stepping ±5% across
 * the whole range on a phone).
 */
export function TargetEditor({ value, min = 10, max = 100, step = 5, onSave }: Props) {
  const [draft, setDraft] = useState(value);
  const [edited, setEdited] = useState(false);
  const [typing, setTyping] = useState(false);
  // A free-text mirror of the input while typing. Clamping the number on every
  // keystroke would fight the user (e.g. typing "5" then "55" would snap to the
  // min in between); instead the string is shown verbatim and the clamped
  // number is derived from it.
  const [typed, setTyped] = useState('');
  const { saving, error, saved, run, reset } = useSaveAction();

  // Keep the draft in sync with the server value, but only while the user has no
  // pending edit — otherwise a poll would overwrite what they're changing.
  // Adjusting state during render (rather than in an effect) is the React-
  // recommended way to derive state from a changing prop: no extra render pass.
  const [prevValue, setPrevValue] = useState(value);
  if (value !== prevValue) {
    setPrevValue(value);
    if (!edited) setDraft(value);
  }

  const change = (delta: number) => {
    reset();
    setEdited(true);
    setDraft((d) => clamp(d + delta, min, max));
  };

  // Guard on `edited` so that after a successful save (which clears `edited`)
  // the action buttons hide and the "Saved ✓" confirmation shows immediately,
  // even before the next poll refreshes `value` to the new target.
  const dirty = edited && draft !== value;

  const save = async () => {
    if (await run(() => onSave(draft))) {
      setEdited(false);
      setTyping(false);
    }
  };

  const cancel = () => {
    setEdited(false);
    setTyping(false);
    reset();
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
        {typing ? (
          <input
            type="number"
            className="target-input"
            min={min}
            max={max}
            step={step}
            value={typed}
            autoFocus
            disabled={saving}
            aria-label="Charge target percent"
            onChange={(e) => {
              reset();
              setEdited(true);
              const raw = e.target.value;
              setTyped(raw);
              const n = Number(raw);
              if (raw !== '' && !Number.isNaN(n)) setDraft(clamp(n, min, max));
            }}
            onBlur={() => setTyping(false)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') setTyping(false);
            }}
          />
        ) : (
          <button
            type="button"
            className="target-value"
            onClick={() => {
              setTyped(String(draft));
              setTyping(true);
            }}
            aria-label={`Charge target ${draft}%, tap to type an exact value`}
          >
            Target {draft}%
          </button>
        )}
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

      {saved && !dirty && (
        <span className="save-confirm" role="status">
          Saved ✓
        </span>
      )}

      {error && (
        <div className="target-error" role="alert">
          Couldn’t update target. Try again.
        </div>
      )}
    </div>
  );
}
