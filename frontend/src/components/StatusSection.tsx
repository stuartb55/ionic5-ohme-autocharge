import type { StatusResponse } from '../api/types';
import { useNow } from '../hooks/useNow';
import { formatFinishTime, formatKwh, formatMiles, formatMoney, formatPower } from '../utils/format';
import { BatteryRing } from './BatteryRing';
import { ChargeControls } from './ChargeControls';
import { ConnectionBadge } from './ConnectionBadge';
import { DayTargetsEditor } from './DayTargetsEditor';
import { ReadyByEditor } from './ReadyByEditor';
import { TargetEditor } from './TargetEditor';

function Tile({ label, value, unit }: { label: string; value: string; unit?: string }) {
  return (
    <div className="tile">
      <div className="label">{label}</div>
      <div className="value">
        {value}
        {unit ? <small> {unit}</small> : null}
      </div>
    </div>
  );
}

export function StatusSection({
  status,
  onSetTarget,
  onSetReadyBy,
  onSetDayTargets,
  onChargeChanged,
}: {
  status: StatusResponse;
  onSetTarget?: (target: number) => Promise<void>;
  /** Persist the ready-by time (or null to clear); editor hidden when omitted. */
  onSetReadyBy?: (value: string | null) => Promise<void>;
  /** Persist per-weekday target overrides; editor hidden when omitted. */
  onSetDayTargets?: (map: Record<number, number>) => Promise<void>;
  /** Refetch status after a charge-control action; controls hidden when omitted. */
  onChargeChanged?: () => void;
}) {
  const { vehicle, charger } = status;
  // The base target is what the editor sets; the effective target (which may be
  // today's per-weekday override) is what the ring and Ohme actually use.
  const baseTarget = status.config.chargeTarget;
  const target = charger.targetPercent ?? baseTarget;
  // Tick once a minute so the projection hides itself when the finish time
  // passes, without reading the impure Date.now() during render.
  const now = useNow(60_000);
  // Show the projected finish only while it's still ahead of us and the
  // session hasn't already completed.
  const showFinish =
    charger.connected &&
    charger.status !== 'finished' &&
    charger.projectedFinish != null &&
    new Date(charger.projectedFinish).getTime() > now;

  return (
    <section className="card" aria-labelledby="status-heading">
      <header>
        <div>
          <p className="eyebrow">Live status</p>
          <h2 id="status-heading">Vehicle &amp; charger</h2>
        </div>
        <ConnectionBadge status={charger.status} />
      </header>

      <div className="status-grid">
        <div className="battery-wrap">
          <BatteryRing percent={vehicle.batteryPercent} target={target} />
          <div className="battery-caption">
            <div className="vehicle">
              {vehicle.name ?? 'Vehicle'}
              {vehicle.rangeMiles != null && (
                <span className="range"> · {formatMiles(vehicle.rangeMiles)}</span>
              )}
            </div>
            {showFinish && (
              <div className="finish-eta">
                Ready by ~{formatFinishTime(charger.projectedFinish as string)}
              </div>
            )}
            {onSetTarget ? (
              <TargetEditor
                value={baseTarget}
                min={status.config.targetMin}
                max={status.config.targetMax}
                onSave={onSetTarget}
              />
            ) : (
              <div className="target">Target {baseTarget}%</div>
            )}
            {target !== baseTarget && (
              <div className="today-target">Today: {target}%</div>
            )}
            {onSetReadyBy && (
              <ReadyByEditor
                value={status.config.readyBy}
                clearable={status.config.readyByIsManual}
                onSave={onSetReadyBy}
              />
            )}
            {onSetDayTargets && (
              <DayTargetsEditor
                value={status.config.dayTargets}
                base={baseTarget}
                min={status.config.targetMin}
                max={status.config.targetMax}
                onSave={onSetDayTargets}
              />
            )}
          </div>
        </div>

        <div className="tiles">
          <Tile label="Charging rate" value={formatPower(charger.power.watts)} />
          <Tile
            label="Current"
            value={charger.power.amps ? charger.power.amps.toFixed(0) : '0'}
            unit="A"
          />
          <Tile label="Added this session" value={formatKwh(charger.sessionEnergyKwh)} />
          {charger.projectedCost != null && (
            <Tile
              label="Est. cost"
              value={formatMoney(charger.projectedCost, charger.projectedCostCurrency)}
              unit={`· ${formatKwh(charger.plannedEnergyKwh)}`}
            />
          )}
          <Tile label="Charger" value={charger.model ?? '—'} unit={charger.online ? '· online' : '· offline'} />
        </div>
      </div>

      {onChargeChanged && <ChargeControls status={status} onChanged={onChargeChanged} />}
    </section>
  );
}
