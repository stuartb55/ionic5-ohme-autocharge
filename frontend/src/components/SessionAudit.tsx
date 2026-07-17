import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { SessionAuditResponse } from '../api/types';
import { formatDateShort, formatMoney, formatTime } from '../utils/format';
import { SessionChargeCurve } from './SessionChargeCurve';

const label = (value: string) =>
  value
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[_-]+/g, ' ')
    .replace(/^./, (character) => character.toUpperCase());

const EVENT_LABELS: Record<string, string> = {
  charge_control: 'Charging control requested',
  charging_finished: 'Charging finished',
  finished: 'Charging finished',
  plugged_in: 'Vehicle plugged in',
  reconciliation_skipped: 'Cost calculation skipped',
  session_reconciled: 'Charging cost calculated',
  skipped_at_target: 'Already at charge target',
  target_configured: 'Charge target set',
  target_reapplied: 'Charge target updated',
  target_reapply_skipped: 'Charge target update skipped',
  trip_mode_consumed: 'Trip charge cleared',
};

const DETAIL_LABELS: Record<string, string> = {
  action: 'Action',
  attributionIssues: 'Data gaps',
  costMinor: 'Charging cost',
  counterEnergyWh: 'Charger reading',
  energyWh: 'Energy added',
  maxCharge: 'Maximum charge',
  readyBy: 'Ready by',
  reason: 'Reason',
  reconstructedEnergyWh: 'Calculated energy',
  soc: 'Battery level',
  soc_percent: 'Battery level',
  status: 'Charger status',
  tariffCoverage: 'Tariff data coverage',
  target: 'Charge target',
  trigger: 'Calculated after',
  tripMode: 'Trip charge',
};

const eventLabel = (value: string) => EVENT_LABELS[value] ?? label(value);

const detailLabel = (key: string) => DETAIL_LABELS[key] ?? label(key);

const dateTime = (value: string | null) =>
  value ? `${formatDateShort(value)} ${formatTime(value)}` : '—';

const DETAIL_VALUE_LABELS: Record<string, string> = {
  finished: 'Charging finished',
  no_energy_counter: 'No charger energy reading',
  no_telemetry: 'No charging data',
  plugged_in: 'Plugged in',
  unplugged: 'Vehicle unplugged',
};

const ENERGY_DETAIL_KEYS = new Set(['counterEnergyWh', 'energyWh', 'reconstructedEnergyWh']);
const PERCENT_DETAIL_KEYS = new Set(['soc', 'soc_percent', 'target']);

const detailValue = (key: string, value: unknown, currency: string | null): string => {
  if (value == null) return '—';
  if (typeof value === 'number') {
    if (ENERGY_DETAIL_KEYS.has(key)) return `${(value / 1000).toFixed(2)} kWh`;
    if (PERCENT_DETAIL_KEYS.has(key)) return `${value}%`;
    if (key === 'costMinor') return formatMoney(value / 100, currency);
    if (key === 'tariffCoverage') return `${Math.round(value * 100)}%`;
  }
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'string' && DETAIL_VALUE_LABELS[value]) {
    return DETAIL_VALUE_LABELS[value];
  }
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  return JSON.stringify(value);
};

const PRIVATE_DETAIL_KEYS = new Set([
  'session_key', 'sessionKey', 'vehicle_id', 'vehicleId', 'vin', 'charger_id', 'chargerId',
]);

/** On-demand evidence behind one history row, including the original timeline. */
export function SessionAudit({ sessionId }: { sessionId: number }) {
  const [audit, setAudit] = useState<SessionAuditResponse | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    api.getSessionAudit(sessionId, controller.signal)
      .then((response) => {
        if (!controller.signal.aborted) setAudit(response);
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => controller.abort();
  }, [sessionId]);

  if (failed) {
    return <p className="session-audit empty">Couldn’t load this session’s audit details.</p>;
  }
  if (!audit) return <div className="session-audit skeleton" style={{ minHeight: 180 }} />;

  const { session, events, schedules, intervals } = audit;
  const currency = session.costCurrency ?? intervals.find((item) => item.currency)?.currency ?? null;

  return (
    <div className="session-audit">
      <div className="audit-summary" aria-label="Session measurement summary">
        <div><span>Measured energy</span><strong>{session.actualEnergyWh == null ? '—' : `${(session.actualEnergyWh / 1000).toFixed(2)} kWh`}</strong></div>
        <div><span>Actual cost</span><strong>{session.actualCostMinor == null ? '—' : formatMoney(session.actualCostMinor / 100, currency)}</strong></div>
        <div><span>Data quality</span><strong>{label(session.quality)}</strong></div>
        <div><span>Tariff coverage</span><strong>{session.tariffCoverage == null ? '—' : `${Math.round(session.tariffCoverage * 100)}%`}</strong></div>
        <div><span>Reconstructed</span><strong>{session.reconstructedEnergyWh == null ? '—' : `${(session.reconstructedEnergyWh / 1000).toFixed(2)} kWh`}</strong></div>
        <div><span>Reconciliation delta</span><strong>{session.reconciliationDeltaWh == null ? '—' : `${session.reconciliationDeltaWh.toLocaleString()} Wh`}</strong></div>
      </div>

      <div className="audit-section">
        <h3>Charge timeline</h3>
        {events.length === 0 ? <p className="empty">No charging events were recorded.</p> : (
          <ol className="audit-events">
            {events.map((event, index) => (
              <li key={`${event.at}-${event.type}-${index}`}>
                <time dateTime={event.at}>{dateTime(event.at)}</time>
                <strong>{eventLabel(event.type)}</strong>
                {Object.keys(event.details).length > 0 && (
                  <dl>
                    {Object.entries(event.details)
                      .filter(([key]) => !PRIVATE_DETAIL_KEYS.has(key))
                      .map(([key, value]) => (
                        <div key={key}><dt>{detailLabel(key)}</dt><dd>{detailValue(key, value, currency)}</dd></div>
                      ))}
                  </dl>
                )}
              </li>
            ))}
          </ol>
        )}
      </div>

      <div className="audit-section">
        <h3>Schedule revisions</h3>
        {schedules.length === 0 ? <p className="empty">No schedule snapshots were recorded.</p> : (
          <div className="audit-schedules">
            {schedules.map((schedule) => (
              <div key={`${schedule.revision}-${schedule.recordedAt}`}>
                <strong>Revision {schedule.revision} · {label(schedule.reason)}</strong>
                <span>{dateTime(schedule.recordedAt)} · {schedule.slots.length} {schedule.slots.length === 1 ? 'slot' : 'slots'}</span>
                {(schedule.nextSlotStart || schedule.nextSlotEnd) && <span>Next: {dateTime(schedule.nextSlotStart)} – {dateTime(schedule.nextSlotEnd)}</span>}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="audit-section">
        <h3>Priced charging intervals</h3>
        {intervals.length === 0 ? <p className="empty">No priced intervals were recorded.</p> : (
          <div className="audit-table-wrap">
            <table className="audit-table">
              <thead><tr><th>Time</th><th>Energy</th><th>Rate</th><th>Cost</th><th>Quality</th></tr></thead>
              <tbody>
                {intervals.map((interval) => (
                  <tr key={`${interval.start}-${interval.end}`}>
                    <td>{formatTime(interval.start)}–{formatTime(interval.end)}</td>
                    <td>{(interval.energyWh / 1000).toFixed(2)} kWh</td>
                    <td>{interval.rateMinorPerKwh == null ? '—' : `${interval.rateMinorPerKwh.toFixed(2)}${interval.currency === 'GBP' ? 'p' : ` ${interval.currency ?? ''}`}/kWh`}</td>
                    <td>{interval.costMinor == null ? '—' : formatMoney(interval.costMinor / 100, interval.currency)}</td>
                    <td>{label(interval.quality)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="audit-section">
        <h3>Charge curve</h3>
        <SessionChargeCurve sessionId={sessionId} />
      </div>
    </div>
  );
}
