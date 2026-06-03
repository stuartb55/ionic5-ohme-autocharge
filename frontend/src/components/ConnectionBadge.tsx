import type { ChargerStatus } from '../api/types';
import { statusLabel } from '../utils/format';

export function ConnectionBadge({ status }: { status: ChargerStatus }) {
  return (
    <span className={`badge ${status}`} role="status" aria-label={`Charger status: ${statusLabel(status)}`}>
      <span className="pip" aria-hidden="true" />
      {statusLabel(status)}
    </span>
  );
}
