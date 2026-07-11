import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { SessionAuditResponse } from '../api/types';
import { formatDateShort, formatMoney, formatTime } from '../utils/format';
import { SessionChargeCurve } from './SessionChargeCurve';

const label = (value: string) =>
  value.replace(/_/g, ' ').replace(/^./, (character) => character.toUpperCase());

const dateTime = (value: string | null) =>
  value ? `${formatDateShort(value)} ${formatTime(value)}` : '—';

const detailValue = (value: unknown): string => {
  if (value == null) return '—';
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
        <h3>Lifecycle</h3>
        {events.length === 0 ? <p className="empty">No lifecycle events were recorded.</p> : (
          <ol className="audit-events">
            {events.map((event, index) => (
              <li key={`${event.at}-${event.type}-${index}`}>
                <time dateTime={event.at}>{dateTime(event.at)}</time>
                <strong>{label(event.type)}</strong>
                {Object.keys(event.details).length > 0 && (
                  <dl>
                    {Object.entries(event.details)
                      .filter(([key]) => !PRIVATE_DETAIL_KEYS.has(key))
                      .map(([key, value]) => (
                      <div key={key}><dt>{label(key)}</dt><dd>{detailValue(value)}</dd></div>
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
