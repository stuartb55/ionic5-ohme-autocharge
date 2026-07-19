import type { ReactNode } from 'react';
import type { StatusResponse } from '../api/types';
import { useNow } from '../hooks/useNow';
import {
  formatFinishTime,
  formatKwh,
  formatMiles,
  formatMoney,
  formatPower,
  statusLabel,
} from '../utils/format';
import { BatteryRing } from './BatteryRing';
import { ChargeControls } from './ChargeControls';
import { ConnectionBadge } from './ConnectionBadge';
import { Icon, type IconName } from './Icon';
import { VehicleHealth } from './VehicleHealth';

function Metric({
  icon,
  label,
  value,
  detail,
}: {
  icon: IconName;
  label: string;
  value: string;
  detail: ReactNode;
}) {
  return (
    <div className="metric-tile">
      <span className="metric-icon"><Icon name={icon} /></span>
      <div>
        <span className="metric-label">{label}</span>
        <strong className="metric-value">{value}</strong>
        <span className="metric-detail">{detail}</span>
      </div>
    </div>
  );
}

function chargingCopy(
  status: StatusResponse,
  target: number,
  finish: string | null,
): { eyebrow: string; title: string; description: string } {
  const { charger, vehicle } = status;
  const remaining = vehicle.batteryPercent == null
    ? null
    : Math.max(0, target - Math.round(vehicle.batteryPercent));

  switch (charger.status) {
    case 'charging':
      return {
        eyebrow: 'Charging now',
        title: finish ? `On track for ${finish}` : `Charging to ${target}%`,
        description: remaining != null && remaining > 0
          ? `${remaining} percentage points left to reach your target.`
          : 'The vehicle is at its target and the session is finishing up.',
      };
    case 'paused':
      return {
        eyebrow: 'Charge paused',
        title: `Target remains ${target}%`,
        description: 'Resume when you are ready. Your smart schedule is still available.',
      };
    case 'finished':
      return {
        eyebrow: 'Charge complete',
        title: `Ready at ${vehicle.batteryPercent == null ? target : Math.round(vehicle.batteryPercent)}%`,
        description: 'The vehicle can stay connected until you need it.',
      };
    case 'plugged_in':
      return {
        eyebrow: 'Connected',
        title: finish ? `Ready by ${finish}` : 'Waiting for the next smart slot',
        description: `Autocharge is managing the session to a ${target}% target.`,
      };
    case 'pending_approval':
      return {
        eyebrow: 'Action needed',
        title: 'Approve the charge in Ohme',
        description: 'The vehicle is connected, but the charger is waiting for approval.',
      };
    case 'unplugged':
      return {
        eyebrow: 'Ready for next time',
        title: 'Plug in and Autocharge takes over',
        description: `Your default target is ${target}%. No action is needed right now.`,
      };
    default:
      return {
        eyebrow: 'Checking status',
        title: 'Waiting for charger data',
        description: 'The dashboard will update automatically when a reading arrives.',
      };
  }
}

export function StatusSection({
  status,
  onChargeChanged,
}: {
  status: StatusResponse;
  /** Refetch status after a charge-control action; controls hidden when omitted. */
  onChargeChanged?: () => void;
}) {
  const { vehicle, charger } = status;
  const baseTarget = status.config.chargeTarget;
  const target = charger.targetPercent ?? baseTarget;
  const now = useNow(60_000);
  const showFinish =
    charger.connected &&
    charger.status !== 'finished' &&
    charger.projectedFinish != null &&
    new Date(charger.projectedFinish).getTime() > now;
  const finish = showFinish
    ? formatFinishTime(charger.projectedFinish as string, new Date(now), status.config.timezone)
    : null;
  const copy = chargingCopy(status, target, finish);
  const hasPower = charger.power.watts > 0;

  return (
    <section className="card status-card" id="overview" aria-labelledby="status-heading">
      <header className="status-header">
        <div>
          <p className="eyebrow">Live vehicle</p>
          <h2 id="status-heading">{vehicle.name ?? 'Your vehicle'}</h2>
        </div>
        <ConnectionBadge status={charger.status} />
      </header>

      <div className="status-hero">
        <div className="battery-panel">
          <BatteryRing percent={vehicle.batteryPercent} target={target} size={240} />
          <div className="battery-target" aria-label={`Charge target ${target}%`}>
            <span>Target</span>
            <strong>{target}%</strong>
          </div>
        </div>

        <div className="charge-story">
          <span className="charge-story-eyebrow">{copy.eyebrow}</span>
          <h3>{copy.title}</h3>
          <p>{copy.description}</p>
          <div className="vehicle-facts">
            {vehicle.rangeMiles != null && (
              <span><Icon name="route" size={17} /> {formatMiles(vehicle.rangeMiles)} range</span>
            )}
            {vehicle.isLocked != null && (
              <span className={vehicle.isLocked ? '' : 'fact-warning'}>
                {vehicle.isLocked ? 'Locked' : 'Unlocked'}
              </span>
            )}
            {vehicle.location && (
              <a
                href={`https://www.google.com/maps?q=${vehicle.location.latitude},${vehicle.location.longitude}`}
                target="_blank"
                rel="noreferrer noopener"
              >
                View location
              </a>
            )}
          </div>
          <VehicleHealth health={vehicle.health} />
        </div>
      </div>

      <div className="metric-grid" aria-label="Current charging metrics">
        <Metric
          icon="bolt"
          label="Charge speed"
          value={hasPower ? formatPower(charger.power.watts) : 'Idle'}
          detail={hasPower && charger.power.amps > 0 ? `${charger.power.amps.toFixed(0)} A` : 'No power draw'}
        />
        <Metric
          icon="energy"
          label="Added so far"
          value={formatKwh(charger.sessionEnergyKwh)}
          detail={charger.plannedEnergyKwh > 0 ? `${formatKwh(charger.plannedEnergyKwh)} planned` : 'This session'}
        />
        <Metric
          icon="wallet"
          label={charger.projectedCostMethod === 'agile'
            ? 'Estimated cost · Agile'
            : charger.projectedCostMethod === 'intelligent_go'
              ? 'Estimated cost · Intelligent Go'
              : 'Estimated cost'}
          value={charger.projectedCost != null
            ? formatMoney(charger.projectedCost, charger.projectedCostCurrency)
            : '—'}
          detail={charger.projectedCost != null ? 'For this charge plan' : 'Price unavailable'}
        />
        <Metric
          icon="plug"
          label="Charger state"
          value={statusLabel(charger.status)}
          detail={`${charger.model ?? 'Ohme'} · ${charger.online ? 'Online' : 'Offline'}`}
        />
      </div>

      <div className="vehicle-summary">
        <span>
          <span className={`summary-dot ${charger.online ? 'online' : 'offline'}`} aria-hidden="true" />
          Charger {charger.online ? 'online' : 'offline'}
        </span>
        {vehicle.sohPercent != null && <span>Battery health {vehicle.sohPercent}%</span>}
        {status.config.tripMode.enabled && <span className="trip-active">Trip charge active</span>}
      </div>

      {onChargeChanged && <ChargeControls status={status} onChanged={onChargeChanged} />}
    </section>
  );
}
