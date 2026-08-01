import type { StatusResponse, VehiclesResponse } from '../api/types';
import { DayTargetsEditor } from './DayTargetsEditor';
import { Icon } from './Icon';
import { NotificationSettings } from './NotificationSettings';
import { ReadyByEditor } from './ReadyByEditor';
import { TargetEditor } from './TargetEditor';
import { TomorrowOverrideEditor } from './TomorrowOverrideEditor';
import { TripModeEditor } from './TripModeEditor';
import { VehiclePicker } from './VehiclePicker';
import { VehicleProfileEditor } from './VehicleProfileEditor';

interface Props {
  status: StatusResponse;
  vehicles: VehiclesResponse | null;
  onSetTarget: (target: number) => Promise<void>;
  onSetReadyBy: (value: string | null) => Promise<void>;
  onSetDayTargets: (map: Record<number, number>) => Promise<void>;
  onSetTripMode: (enabled: boolean, target: number, readyBy: string | null) => Promise<void>;
  onSetTomorrowOverride: (enabled: boolean, target: number, readyBy: string | null) => Promise<void>;
  onSetVehicle: (vehicleId: string) => Promise<void>;
  onSetVehicleProfile: (
    vehicleId: string, enabled: boolean, target: number, readyBy: string | null,
  ) => Promise<void>;
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
  vehicles,
  onSetTarget,
  onSetReadyBy,
  onSetDayTargets,
  onSetTripMode,
  onSetTomorrowOverride,
  onSetVehicle,
  onSetVehicleProfile,
  onSetNotifications,
}: Props) {
  const baseTarget = status.config.chargeTarget;
  const effectiveTarget = status.config.effectiveTarget;
  const overrideCount = Object.keys(status.config.dayTargets).length;
  const sourceLabels = {
    trip: 'One-off trip charge',
    tomorrow: 'Tomorrow-only plan',
    vehicle_profile: 'Vehicle profile',
    weekday: 'Today’s weekly target',
    default: 'Default plan',
    ohme: 'Ohme schedule',
    none: 'No departure time',
  } as const;
  const effectiveSource = sourceLabels[status.config.effectiveTargetSource];
  const readyBySource = sourceLabels[status.config.effectiveReadyBySource];
  const fleet = vehicles?.vehicles ?? [];
  const activeVehicleId = vehicles?.selected ?? fleet[0]?.id ?? null;
  const activeVehicle = fleet.find((vehicle) => vehicle.id === activeVehicleId) ?? null;
  const activeProfile = activeVehicleId
    ? status.config.vehicleProfiles[activeVehicleId] ?? null
    : null;
  const tomorrowActive = status.config.tomorrowOverride.enabled;

  return (
    <section className="card settings-card" id="settings" aria-labelledby="settings-heading">
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

      {fleet.length > 1 && (
        <div className="settings-vehicle-picker">
          <VehiclePicker
            vehicles={fleet}
            selected={vehicles?.selected ?? null}
            onSelect={onSetVehicle}
          />
          <span className="field-hint">Preferences below apply to the selected vehicle.</span>
        </div>
      )}

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
              <span className="setting-provenance">Active: {effectiveTarget}% · {effectiveSource}</span>
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
              <span className="setting-provenance">
                Active: {status.config.effectiveReadyBy ?? 'no time'} · {readyBySource}
              </span>
            </div>
          </div>
          <ReadyByEditor
            value={status.config.readyBy}
            clearable={status.config.readyByIsManual}
            onSave={onSetReadyBy}
          />
        </div>
      </div>

      <details className="settings-more" open={status.config.tripMode.enabled || tomorrowActive || undefined}>
        <summary>
          <span>
            More options
            <small>Weekly targets, one-off trips and alerts</small>
          </span>
          {(overrideCount > 0 || status.config.tripMode.enabled || tomorrowActive) && (
            <span className="settings-count">
              {status.config.tripMode.enabled
                ? 'Trip active'
                : tomorrowActive
                  ? 'Tomorrow planned'
                  : `${overrideCount} scheduled`}
            </span>
          )}
        </summary>
        <div className="settings-advanced">
          <TomorrowOverrideEditor
            value={status.config.tomorrowOverride}
            baseTarget={baseTarget}
            min={status.config.targetMin}
            max={status.config.targetMax}
            onSave={onSetTomorrowOverride}
          />
          <TripModeEditor
            value={status.config.tripMode}
            min={status.config.targetMin}
            max={status.config.targetMax}
            onSave={onSetTripMode}
          />
          {activeVehicle && fleet.length > 1 && (
            <VehicleProfileEditor
              vehicleId={activeVehicle.id}
              vehicleName={activeVehicle.name ?? activeVehicle.model ?? 'Selected vehicle'}
              value={activeProfile}
              defaultTarget={baseTarget}
              min={status.config.targetMin}
              max={status.config.targetMax}
              onSave={onSetVehicleProfile}
            />
          )}
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
