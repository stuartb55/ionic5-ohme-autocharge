import type { StatusResponse } from '../api/types';
import { DayTargetsEditor } from './DayTargetsEditor';
import { Icon } from './Icon';
import { NotificationSettings } from './NotificationSettings';
import { ReadyByEditor } from './ReadyByEditor';
import { TargetEditor } from './TargetEditor';
import { TripModeEditor } from './TripModeEditor';

interface Props {
  status: StatusResponse;
  onSetTarget: (target: number) => Promise<void>;
  onSetReadyBy: (value: string | null) => Promise<void>;
  onSetDayTargets: (map: Record<number, number>) => Promise<void>;
  onSetTripMode: (enabled: boolean, target: number, readyBy: string | null) => Promise<void>;
  onSetNotifications: (
    preferences: Omit<StatusResponse['config']['notifications'], 'configured'>,
  ) => Promise<void>;
}

/**
 * The two settings used day-to-day stay visible. Less frequent scheduling and
 * notification controls live in a single disclosure so the dashboard remains
 * quick to scan on a phone.
 */
export function ChargeSettingsSection({
  status,
  onSetTarget,
  onSetReadyBy,
  onSetDayTargets,
  onSetTripMode,
  onSetNotifications,
}: Props) {
  const baseTarget = status.config.chargeTarget;
  const effectiveTarget = status.charger.targetPercent ?? baseTarget;
  const overrideCount = Object.keys(status.config.dayTargets).length;
  const effectiveSource = status.config.tripMode.enabled
    ? 'One-off trip charge'
    : overrideCount > 0
      ? 'Weekly overrides set'
      : 'Default plan';

  return (
    <section className="card settings-card" aria-labelledby="settings-heading">
      <header>
        <div>
          <p className="eyebrow">Your routine</p>
          <h2 id="settings-heading">Charge preferences</h2>
        </div>
        <div className="settings-summary" aria-label="Charge settings summary">
          <strong>{effectiveTarget}%</strong>
          <span>{effectiveSource}</span>
        </div>
      </header>

      <p className="settings-context">
        These defaults are applied automatically whenever you plug in.
      </p>

      <div className="settings-primary">
        <div className="setting-block">
          <div className="setting-heading">
            <span className="setting-icon"><Icon name="energy" /></span>
            <div>
              <span className="setting-label">Charge to</span>
              <span className="setting-help">Everyday battery target</span>
            </div>
          </div>
          <TargetEditor
            value={baseTarget}
            min={status.config.targetMin}
            max={status.config.targetMax}
            onSave={onSetTarget}
          />
        </div>
        <div className="setting-block">
          <div className="setting-heading">
            <span className="setting-icon"><Icon name="clock" /></span>
            <div>
              <span className="setting-label">Ready by</span>
              <span className="setting-help">Optional departure time</span>
            </div>
          </div>
          <ReadyByEditor
            value={status.config.readyBy}
            clearable={status.config.readyByIsManual}
            onSave={onSetReadyBy}
          />
        </div>
      </div>

      <details className="settings-more" open={status.config.tripMode.enabled || undefined}>
        <summary>
          <span>
            More options
            <small>Weekly targets, one-off trips and alerts</small>
          </span>
          {(overrideCount > 0 || status.config.tripMode.enabled) && (
            <span className="settings-count">
              {status.config.tripMode.enabled ? 'Trip active' : `${overrideCount} scheduled`}
            </span>
          )}
        </summary>
        <div className="settings-advanced">
          <TripModeEditor
            value={status.config.tripMode}
            min={status.config.targetMin}
            max={status.config.targetMax}
            onSave={onSetTripMode}
          />
          <DayTargetsEditor
            value={status.config.dayTargets}
            base={baseTarget}
            min={status.config.targetMin}
            max={status.config.targetMax}
            onSave={onSetDayTargets}
          />
          <NotificationSettings value={status.config.notifications} onSave={onSetNotifications} />
        </div>
      </details>
    </section>
  );
}
