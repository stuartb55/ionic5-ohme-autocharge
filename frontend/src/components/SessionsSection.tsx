import { useState } from 'react';
import { api } from '../api/client';
import type { SessionsResponse } from '../api/types';
import { formatDateShort, formatTime } from '../utils/format';
import { SessionAudit } from './SessionAudit';

const ACTION_LABEL: Record<string, string> = {
  configured: 'Target set',
  skipped_at_target: 'Already at target',
};

/**
 * Recent plug-in sessions from the Postgres history. Renders nothing at all
 * when persistence is disabled — the dashboard works without the feature. Each
 * row expands to explain that session's measurements and provenance.
 */
export function SessionsSection({ data }: { data: SessionsResponse }) {
  const [expandedId, setExpandedId] = useState<number | null>(null);

  if (!data.enabled) return null;

  return (
    <section className="card" aria-labelledby="sessions-heading">
      <header>
        <div>
          <p className="eyebrow">History</p>
          <h2 id="sessions-heading">Recent sessions</h2>
        </div>
        {data.sessions.length > 0 && (
          <div className="session-actions">
            {/* Full history (not just the rows shown) — the backend serves it as
                a download. Plain links so the browser handles the file save. */}
            <a className="ghost-button" href={api.sessionsExportUrl('csv')} download>
              Export CSV
            </a>
            <a className="ghost-button" href={api.sessionsExportUrl('json')} download>
              JSON
            </a>
          </div>
        )}
      </header>

      {data.sessions.length === 0 ? (
        <p className="empty">No plug-in sessions recorded yet.</p>
      ) : (
        <div className="session-list">
          <div className="session-head" aria-hidden="true">
            <span className="time">When</span>
            <span className="detail">Battery → target</span>
            <span className="session-action">Result</span>
          </div>
          {data.sessions.map((s) => {
            const expanded = expandedId === s.id;
            const battery =
              s.socPercent != null && s.targetPercent != null
                ? `${s.socPercent}% → ${s.targetPercent}%`
                : null;
            const extras: string[] = [];
            if (s.topupPercent != null) extras.push(`+${s.topupPercent}%`);
            if (s.odometerMiles != null) extras.push(`${Math.round(s.odometerMiles).toLocaleString()} mi`);
            if (s.sohPercent != null) extras.push(`SoH ${s.sohPercent}%`);
            if (s.actualEnergyKwh != null) extras.push(`${s.actualEnergyKwh.toFixed(1)} kWh actual`);
            if (s.actualCost != null) {
              extras.push(`${new Intl.NumberFormat(undefined, { style: 'currency', currency: s.costCurrency ?? 'GBP' }).format(s.actualCost)} actual`);
            }
            if (s.quality && s.quality !== 'reconciled' && s.quality !== 'complete') {
              extras.push(`Data: ${s.quality.replace(/_/g, ' ')}`);
            }
            if (s.vehicleName) extras.push(s.vehicleName);
            const detail = [battery, ...extras].filter(Boolean).join(' · ') || '—';
            return (
              <div className="session-item" id={`session-${s.id}`} key={s.id}>
                <button
                  type="button"
                  className={`session-row ${expanded ? 'expanded' : ''}`}
                  aria-expanded={expanded}
                  onClick={() => setExpandedId(expanded ? null : s.id)}
                >
                  <span className="time" data-label="When">
                    {s.pluggedInAt
                      ? `${formatDateShort(s.pluggedInAt)} · ${formatTime(s.pluggedInAt)}`
                      : '—'}
                  </span>
                  <span className="detail" data-label="Charge">{detail}</span>
                  <span className={`session-action ${s.action ?? ''}`} data-label="Result">
                    {ACTION_LABEL[s.action ?? ''] ?? s.action ?? ''}
                  </span>
                  <span className="session-chevron" aria-hidden="true">
                    {expanded ? '▾' : '▸'}
                  </span>
                </button>
                {expanded && <SessionAudit sessionId={s.id} />}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
