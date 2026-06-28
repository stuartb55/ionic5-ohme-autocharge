import { useCallback, useEffect, useRef, useState } from 'react';

export interface SaveAction {
  /** A save is in flight. */
  saving: boolean;
  /** The last save failed. */
  error: boolean;
  /** A save just succeeded (transient — clears itself after ~1.6s). */
  saved: boolean;
  /**
   * Run an async persist. Sets `saving` while in flight, flashes `saved` on
   * success (so the UI can confirm the write landed) or sets `error` on
   * failure. Resolves to true on success, false on failure.
   */
  run: (action: () => Promise<void>) => Promise<boolean>;
  /** Clear the error/saved flags (e.g. when the user edits again). */
  reset: () => void;
}

const SAVED_MS = 1600;

/**
 * The save/saving/error/"saved ✓" state machine shared by every editor. Before
 * this hook each editor reimplemented the saving+error flags and a `save()`
 * that toggled them; centralising it also gives a consistent success
 * confirmation (writes were previously silent on success).
 */
export function useSaveAction(): SaveAction {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(false);
  const [saved, setSaved] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  const run = useCallback(async (action: () => Promise<void>) => {
    setSaving(true);
    setError(false);
    setSaved(false);
    try {
      await action();
      setSaved(true);
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setSaved(false), SAVED_MS);
      return true;
    } catch {
      setError(true);
      return false;
    } finally {
      setSaving(false);
    }
  }, []);

  const reset = useCallback(() => {
    setError(false);
    setSaved(false);
  }, []);

  return { saving, error, saved, run, reset };
}
