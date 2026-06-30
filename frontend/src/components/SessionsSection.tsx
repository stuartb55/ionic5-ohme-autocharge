import { useState } from 'react';
import { api } from '../api/client';
import type { SessionsResponse } from '../api/types';
import { formatDateShort, formatTime } from '../utils/format';
import { SessionChargeCurve } from './SessionChargeCurve';

const ACTION_LABEL: Record<string, string> = {
  configured: 'Target set',
  skipped_at_target: 'Already at target',
};

/**
 * Recent plug-in sessions from the Postgres history. Renders nothing at all
 * when persistence is disabled — the dashboard works without the feature. Each
 * row expands to show that session's charge curve (SOC + power over time).
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
            return (
              <div className="session-item" key={s.id}>
                <button
                  type="button"
                  className={`session-row ${expanded ? 'expanded' : ''}`}
                  aria-expanded={expanded}
                  onClick={() => setExpandedId(expanded ? null : s.id)}
                >
                  <span className="time">
                    {s.pluggedInAt
                      ? `${formatDateShort(s.pluggedInAt)} · ${formatTime(s.pluggedInAt)}`
                      : '—'}
                  </span>
                  <span className="detail">
                    {s.socPercent != null && s.targetPercent != null
                      ? `${s.socPercent}% → ${s.targetPercent}%`
                      : '—'}
                  </span>
                  <span className={`session-action ${s.action ?? ''}`}>
                    {ACTION_LABEL[s.action ?? ''] ?? s.action ?? ''}
                  </span>
                  <span className="session-chevron" aria-hidden="true">
                    {expanded ? '▾' : '▸'}
                  </span>
                </button>
                {expanded && <SessionChargeCurve sessionId={s.id} />}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
