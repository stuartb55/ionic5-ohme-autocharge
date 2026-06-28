import { useState } from 'react';
import { useSaveAction } from '../hooks/useSaveAction';

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

interface Props {
  /** Current per-weekday overrides keyed by weekday string ("0".."6"). */
  value: Record<string, number>;
  /** The base target shown as the "no override" option. */
  base: number;
  min: number;
  max: number;
  step?: number;
  /** Persist the full replacement map (weekday number -> percent). Rejects on failure. */
  onSave: (map: Record<number, number>) => Promise<void>;
}

/**
 * Optional per-weekday charge targets, tucked in a <details> so they don't
 * clutter the status card. Seven day chips lay out as a 7-across row on
 * desktop and wrap to 4-across on narrow screens. Edits are local until saved.
 */
export function DayTargetsEditor({ value, base, min, max, step = 5, onSave }: Props) {
  const toDraft = (v: Record<string, number>) =>
    DAYS.map((_, i) => (v[String(i)] != null ? String(v[String(i)]) : ''));

  const [draft, setDraft] = useState<string[]>(() => toDraft(value));
  const [prev, setPrev] = useState(value);
  const [edited, setEdited] = useState(false);
  const { saving, error, saved, run, reset } = useSaveAction();

  // Resync the draft to the server value while the user isn't mid-edit.
  if (value !== prev) {
    setPrev(value);
    if (!edited) setDraft(toDraft(value));
  }

  // Signal in the collapsed summary that overrides are configured, so a
  // forgotten Monday=65% isn't invisible behind a closed <details>.
  const overrideCount = Object.keys(value).length;

  const options: number[] = [];
  for (let p = max; p >= min; p -= step) options.push(p);

  const change = (i: number, v: string) => {
    setEdited(true);
    reset();
    setDraft((d) => d.map((x, j) => (j === i ? v : x)));
  };

  const save = async () => {
    const map: Record<number, number> = {};
    draft.forEach((s, i) => {
      if (s !== '') map[i] = Number(s);
    });
    if (await run(() => onSave(map))) setEdited(false);
  };

  return (
    <details className="day-targets">
      <summary>
        Per-day targets
        {overrideCount > 0 && (
          <span className="badge day-targets-count">
            {overrideCount} {overrideCount === 1 ? 'override' : 'overrides'}
          </span>
        )}
      </summary>
      <div className="day-chips">
        {DAYS.map((day, i) => (
          <div key={day} className={`day-chip${draft[i] ? ' day-chip--override' : ''}`}>
            <span className="day-chip-name">{day}</span>
            <select
              value={draft[i]}
              disabled={saving}
              onChange={(e) => change(i, e.target.value)}
              aria-label={`${day} target`}
            >
              <option value="">Base ({base}%)</option>
              {options.map((p) => (
                <option key={p} value={p}>
                  {p}%
                </option>
              ))}
            </select>
          </div>
        ))}
      </div>
      {edited && (
        <button type="button" className="save" onClick={save} disabled={saving}>
          {saving ? 'Saving…' : 'Save per-day'}
        </button>
      )}
      {saved && !edited && (
        <span className="save-confirm" role="status">
          Saved ✓
        </span>
      )}
      {error && (
        <div className="target-error" role="alert">
          Couldn't update per-day targets. Try again.
        </div>
      )}
    </details>
  );
}
