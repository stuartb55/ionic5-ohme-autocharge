import type { StatusResponse } from '../api/types';
import { DayTargetsEditor } from './DayTargetsEditor';
import { NotificationSettings } from './NotificationSettings';
import { ReadyByEditor } from './ReadyByEditor';
import { TargetEditor } from './TargetEditor';
import { TripModeEditor } from './TripModeEditor';
import { VehicleProfileEditor } from './VehicleProfileEditor';

interface Props {
  status: StatusResponse;
  activeVehicle?: { id: string; name: string | null };
  onSetTarget: (target: number) => Promise<void>;
  onSetReadyBy: (value: string | null) => Promise<void>;
  onSetDayTargets: (map: Record<number, number>) => Promise<void>;
  onSetTripMode: (enabled: boolean, target: number, readyBy: string | null) => Promise<void>;
  onSetNotifications: (
    preferences: Omit<StatusResponse['config']['notifications'], 'configured'>,
  ) => Promise<void>;
  onSetVehicleProfile: (
    vehicleId: string,
    enabled: boolean,
    target: number,
    readyBy: string | null,
  ) => Promise<void>;
}

/**
 * Future-facing charge configuration, intentionally separate from live
 * telemetry so routine status checks stay quick and low-risk actions are not
 * visually mixed with persistent settings.
 */
export function ChargeSettingsSection({
  status,
  activeVehicle,
  onSetTarget,
  onSetReadyBy,
  onSetDayTargets,
  onSetTripMode,
  onSetNotifications,
  onSetVehicleProfile,
}: Props) {
  const baseTarget = status.config.chargeTarget;
  const effectiveTarget = status.charger.targetPercent ?? baseTarget;
  const effectiveTargetLabel = status.config.tripMode.enabled
    ? 'Trip mode'
    : activeVehicle && status.config.vehicleProfiles[activeVehicle.id]
      ? `${activeVehicle.name ?? 'Vehicle'} profile`
      : 'Today';
  const overrideCount = Object.keys(status.config.dayTargets).length;

  return (
    <section className="card settings-card" aria-labelledby="settings-heading">
      <header>
        <div>
          <p className="eyebrow">Plan ahead</p>
          <h2 id="settings-heading">Charge settings</h2>
        </div>
        <div className="settings-summary" aria-label="Effective settings today">
          <strong>{effectiveTarget}%</strong>
          <span>{status.config.readyBy ? `Ready by ${status.config.readyBy}` : 'No ready-by time'}</span>
        </div>
      </header>

      <p className="settings-context">
        {effectiveTargetLabel} sets the effective target to {effectiveTarget}%
        {overrideCount > 0 ? ` · ${overrideCount} weekly ${overrideCount === 1 ? 'override' : 'overrides'}` : ''}.
      </p>

      <div className="settings-primary">
        <div className="setting-block">
          <div className="setting-label">Base target</div>
          <TargetEditor
            value={baseTarget}
            min={status.config.targetMin}
            max={status.config.targetMax}
            onSave={onSetTarget}
          />
        </div>
        <div className="setting-block">
          <div className="setting-label">Departure</div>
          <ReadyByEditor
            value={status.config.readyBy}
            clearable={status.config.readyByIsManual}
            onSave={onSetReadyBy}
          />
        </div>
      </div>

      <div className="settings-advanced">
        <DayTargetsEditor
          value={status.config.dayTargets}
          base={baseTarget}
          min={status.config.targetMin}
          max={status.config.targetMax}
          onSave={onSetDayTargets}
        />
        <TripModeEditor
          value={status.config.tripMode}
          min={status.config.targetMin}
          max={status.config.targetMax}
          onSave={onSetTripMode}
        />
        <NotificationSettings value={status.config.notifications} onSave={onSetNotifications} />
        {activeVehicle && (
          <VehicleProfileEditor
            key={activeVehicle.id}
            vehicleId={activeVehicle.id}
            vehicleName={activeVehicle.name ?? status.vehicle.name ?? 'Vehicle'}
            value={status.config.vehicleProfiles[activeVehicle.id] ?? null}
            min={status.config.targetMin}
            max={status.config.targetMax}
            onSave={onSetVehicleProfile}
          />
        )}
      </div>
    </section>
  );
}
