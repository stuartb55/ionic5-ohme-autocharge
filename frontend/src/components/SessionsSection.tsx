import { useState } from 'react';
import { api } from '../api/client';
import type {
  ChargeSessionEntry,
  SessionReviewFilter,
  SessionReviewIssue,
  SessionsResponse,
} from '../api/types';
import { formatDateShort, formatTime } from '../utils/format';
import { SessionAudit } from './SessionAudit';

const ACTION_LABEL: Record<string, string> = {
  configured: 'Target set',
  skipped_at_target: 'Already at target',
};

const REVIEW_LABEL: Record<SessionReviewIssue, string> = {
  missing_energy: 'Energy unavailable',
  missing_cost: 'Cost unavailable',
};

function countLabel(value: number, singular: string, plural = `${singular}s`) {
  return `${value} ${value === 1 ? singular : plural}`;
}

function sessionMatchesReview(
  session: ChargeSessionEntry,
  review: SessionReviewFilter,
) {
  return review === 'any'
    ? session.reviewIssues.length > 0
    : session.reviewIssues.includes(review);
}

/**
 * Recent plug-in sessions from the Postgres history. Renders nothing at all
 * when persistence is disabled — the dashboard works without the feature. Each
 * row expands to explain that session's measurements and provenance.
 */
export function SessionsSection({
  data,
  reviewFilter = null,
  reviewTotal = 0,
  onClearReview,
}: {
  data: SessionsResponse;
  reviewFilter?: SessionReviewFilter | null;
  reviewTotal?: number;
  onClearReview?: () => void;
}) {
  const [expandedId, setExpandedId] = useState<number | null>(null);

  if (!data.enabled) return null;

  const responseMatchesMode = data.review === reviewFilter;
  const visibleSessions = responseMatchesMode
    ? reviewFilter
      ? data.sessions.filter((session) => sessionMatchesReview(session, reviewFilter))
      : data.sessions
    : [];
  const showExports = data.sessions.length > 0 || reviewTotal > 0;

  return (
    <section className="card" aria-labelledby="sessions-heading">
      <header>
        <div>
          <p className="eyebrow">History</p>
          <h2 id="sessions-heading" tabIndex={-1}>
            {reviewFilter ? 'Sessions needing attention' : 'Recent sessions'}
          </h2>
        </div>
        <div className="session-actions">
          {reviewFilter && onClearReview && (
            <button type="button" className="ghost-button" onClick={onClearReview}>
              Show recent
            </button>
          )}
          {showExports && (
            <>
              {/* Full history (not just the rows shown) — the backend serves it as
                  a download. Plain links so the browser handles the file save. */}
              <a className="ghost-button" href={api.sessionsExportUrl('csv')} download>
                Export CSV
              </a>
              <a className="ghost-button" href={api.sessionsExportUrl('json')} download>
                JSON
              </a>
            </>
          )}
        </div>
      </header>

      {reviewFilter && (
        <div className="session-review-summary" role="status">
          <span className="session-review-summary-icon" aria-hidden="true">!</span>
          <span>
            <strong>
              {reviewTotal > 0
                ? `${countLabel(reviewTotal, 'session')} ${
                    reviewTotal === 1 ? 'needs' : 'need'
                  } attention`
                : 'Reviewing session completeness'}
            </strong>
            <small>
              {!responseMatchesMode
                ? 'Finding the affected records…'
                : visibleSessions.length < reviewTotal
                  ? `Showing the newest ${visibleSessions.length} matching records. Export the full history for older sessions.`
                  : 'Open a row to inspect its measurements and audit trail.'}
            </small>
          </span>
        </div>
      )}

      {!responseMatchesMode ? (
        <p className="empty" role="status">
          {reviewFilter ? 'Loading affected sessions…' : 'Loading recent sessions…'}
        </p>
      ) : visibleSessions.length === 0 ? (
        <p className="empty">
          {reviewFilter
            ? 'No sessions currently match this check. The source data may have reconciled since the diagnostics were refreshed.'
            : 'No plug-in sessions recorded yet.'}
        </p>
      ) : (
        <div className="session-list">
          <div className="session-head" aria-hidden="true">
            <span className="time">When</span>
            <span className="detail">Battery → target</span>
            <span className="session-action">Result</span>
          </div>
          {visibleSessions.map((s) => {
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
            if (
              s.reviewIssues.length === 0
              && s.quality
              && s.quality !== 'reconciled'
              && s.quality !== 'complete'
            ) {
              extras.push(`Data: ${s.quality.replace(/_/g, ' ')}`);
            }
            if (s.vehicleName) extras.push(s.vehicleName);
            const detail = [battery, ...extras].filter(Boolean).join(' · ') || '—';
            return (
              <div
                className={`session-item ${s.reviewIssues.length > 0 ? 'needs-review' : ''}`}
                id={`session-${s.id}`}
                key={s.id}
              >
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
                  <span className="detail" data-label="Charge">
                    <span>{detail}</span>
                    {s.reviewIssues.length > 0 && (
                      <span className="session-review-flags">
                        {s.reviewIssues.map((issue) => (
                          <span className="session-review-flag" key={issue}>
                            {REVIEW_LABEL[issue]}
                          </span>
                        ))}
                      </span>
                    )}
                  </span>
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
