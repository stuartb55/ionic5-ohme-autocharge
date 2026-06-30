import { api } from '../api/client';
import type { SessionsResponse } from '../api/types';
import { formatDateShort, formatTime } from '../utils/format';

const ACTION_LABEL: Record<string, string> = {
  configured: 'Target set',
  skipped_at_target: 'Already at target',
};

/**
 * Recent plug-in sessions from the Postgres history. Renders nothing at all
 * when persistence is disabled — the dashboard works without the feature.
 */
export function SessionsSection({ data }: { data: SessionsResponse }) {
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
          {data.sessions.map((s) => (
            <div className="session-row" key={s.id}>
              <span className="time">
                {s.pluggedInAt ? `${formatDateShort(s.pluggedInAt)} · ${formatTime(s.pluggedInAt)}` : '—'}
              </span>
              <span className="detail">
                {s.socPercent != null && s.targetPercent != null
                  ? `${s.socPercent}% → ${s.targetPercent}%`
                  : '—'}
              </span>
              <span className={`session-action ${s.action ?? ''}`}>
                {ACTION_LABEL[s.action ?? ''] ?? s.action ?? ''}
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
