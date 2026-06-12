import { useState } from 'react';
import { api } from '../api/client';
import type { StatusResponse } from '../api/types';

interface Props {
  status: StatusResponse;
  /** Called after a successful action so the parent refetches status. */
  onChanged: () => void;
}

type Action = 'pause' | 'resume' | 'boost-on' | 'boost-off';

/**
 * Charge controls: pause/resume the active session and toggle Ohme's
 * max-charge ("boost") mode. Rendered only while the car is plugged in.
 * Boost abandons the smart (off-peak) schedule and charges flat-out, so
 * enabling it asks for an inline confirmation first.
 */
export function ChargeControls({ status, onChanged }: Props) {
  const [busy, setBusy] = useState<Action | null>(null);
  const [confirmBoost, setConfirmBoost] = useState(false);
  const [error, setError] = useState(false);

  const { charger } = status;
  if (!charger.connected) return null;

  const run = async (action: Action, call: () => Promise<unknown>) => {
    setBusy(action);
    setError(false);
    try {
      await call();
      onChanged();
    } catch {
      setError(true);
    } finally {
      setBusy(null);
      setConfirmBoost(false);
    }
  };

  const paused = charger.status === 'paused';
  const pausable = charger.status === 'charging' || charger.status === 'plugged_in';
  const boost = charger.maxCharge;

  return (
    <div className="charge-controls" role="group" aria-label="Charge controls">
      {paused && (
        <button
          type="button"
          className="ghost-button"
          disabled={busy !== null}
          onClick={() => run('resume', () => api.resumeCharge())}
        >
          {busy === 'resume' ? 'Resuming…' : 'Resume charging'}
        </button>
      )}
      {pausable && (
        <button
          type="button"
          className="ghost-button"
          disabled={busy !== null}
          onClick={() => run('pause', () => api.pauseCharge())}
        >
          {busy === 'pause' ? 'Pausing…' : 'Pause charging'}
        </button>
      )}

      {boost ? (
        <button
          type="button"
          className="ghost-button"
          disabled={busy !== null}
          onClick={() => run('boost-off', () => api.setMaxCharge(false))}
        >
          {busy === 'boost-off' ? 'Stopping…' : 'Stop boost'}
        </button>
      ) : confirmBoost ? (
        <>
          <button
            type="button"
            className="ghost-button boost-confirm"
            disabled={busy !== null}
            onClick={() => run('boost-on', () => api.setMaxCharge(true))}
          >
            {busy === 'boost-on' ? 'Starting…' : 'Confirm boost'}
          </button>
          <button
            type="button"
            className="ghost-button"
            disabled={busy !== null}
            onClick={() => setConfirmBoost(false)}
          >
            Cancel
          </button>
        </>
      ) : (
        <button
          type="button"
          className="ghost-button"
          disabled={busy !== null}
          onClick={() => setConfirmBoost(true)}
          title="Charge at full rate now, ignoring the smart schedule"
        >
          Boost charge
        </button>
      )}

      {error && (
        <span className="target-error" role="alert">
          Action failed — try again.
        </span>
      )}
    </div>
  );
}
