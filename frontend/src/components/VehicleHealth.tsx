import type { StatusResponse } from '../api/types';

type WarnKey = 'tyrePressureWarning' | 'washerFluidWarning' | 'keyBatteryWarning';

const WARNINGS: { key: WarnKey; label: string }[] = [
  { key: 'tyrePressureWarning', label: 'Tyre pressure' },
  { key: 'washerFluidWarning', label: 'Washer fluid' },
  { key: 'keyBatteryWarning', label: 'Key fob battery' },
];

/**
 * Read-only vehicle-health chips: the 12V auxiliary battery and any active
 * warnings (tyre/washer/key) or things left open. Renders nothing when the car
 * reported none of these, so a healthy vehicle adds no clutter.
 */
export function VehicleHealth({ health }: { health: StatusResponse['vehicle']['health'] }) {
  const warnings = WARNINGS.filter((w) => health[w.key] === true).map((w) => w.label);
  const open = health.openItems;
  const hasAux = health.auxBatteryPercent != null;

  if (!hasAux && warnings.length === 0 && open.length === 0) return null;

  return (
    <div className="vehicle-health">
      {hasAux && (
        <span className="health-chip aux" title="12V auxiliary battery">
          12V {health.auxBatteryPercent}%
        </span>
      )}
      {warnings.map((label) => (
        <span key={label} className="health-chip warn">
          <span aria-hidden="true">⚠</span> {label}
        </span>
      ))}
      {open.map((item) => (
        <span key={item} className="health-chip warn">
          <span aria-hidden="true">⚠</span> {item} open
        </span>
      ))}
    </div>
  );
}
