import type {
  DataQualityResponse,
  SessionReviewFilter,
} from '../api/types';
import {
  dataQualityIssueCount,
  dataQualityStatusLabel,
} from '../utils/dataQuality';

type CheckState = 'attention' | 'ok' | 'neutral';

interface QualityCheck {
  key: string;
  title: string;
  state: CheckState;
  status: string;
  description: string;
}

function countLabel(value: number, singular: string, plural = `${singular}s`) {
  return `${value} ${value === 1 ? singular : plural}`;
}

function dateLabel(value: string | null | undefined) {
  if (!value) return 'Not available yet';
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  const date = dateOnly
    ? new Date(Date.UTC(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3])))
    : new Date(value);
  if (Number.isNaN(date.getTime())) return 'Not available yet';
  return date.toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    ...(dateOnly ? { timeZone: 'UTC' } : {}),
  });
}

function dateTimeLabel(value: string | null | undefined) {
  if (!value) return 'Not available yet';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Not available yet';
  return date.toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function ageLabel(seconds: number | null) {
  if (seconds == null) return 'Not ready yet';
  if (seconds < 60) return 'Updated less than a minute ago';
  if (seconds < 3600) return `Updated ${Math.round(seconds / 60)}m ago`;
  if (seconds < 86_400) return `Updated ${Math.round(seconds / 3600)}h ago`;
  return `Updated ${Math.round(seconds / 86_400)}d ago`;
}

function CheckRow({ check }: { check: QualityCheck }) {
  return (
    <li className={`quality-check ${check.state}`}>
      <span className="quality-check-icon" aria-hidden="true">
        {check.state === 'attention' ? '!' : check.state === 'ok' ? '✓' : '–'}
      </span>
      <span className="quality-check-copy">
        <strong>{check.title}</strong>
        <span>{check.description}</span>
      </span>
      <span className={`quality-check-state ${check.state}`}>{check.status}</span>
    </li>
  );
}

export function DataQualitySection({
  data,
  onReviewSessions,
}: {
  data: DataQualityResponse;
  onReviewSessions: (filter: SessionReviewFilter) => void;
}) {
  if (!data.persistenceAvailable) return null;

  const sessions = data.sessions;
  const completed = sessions?.completed ?? 0;
  const energyMissing = sessions?.missingActualEnergy ?? 0;
  const unlinked = data.telemetry?.unlinkedLast24h ?? 0;
  const uncertain = data.consumptionConfigured
    ? (data.consumption?.uncertainLast30d ?? 0)
    : 0;
  const issueCount = dataQualityIssueCount(data);
  const sessionIssueTotal = energyMissing;
  const sessionReviewFilter: SessionReviewFilter = 'missing_energy';

  const checks: QualityCheck[] = [
    {
      key: 'session-energy',
      title: 'Charging session energy',
      state: energyMissing > 0 ? 'attention' : completed > 0 ? 'ok' : 'neutral',
      status: energyMissing > 0 ? 'Needs review' : completed > 0 ? 'Good' : 'Waiting for data',
      description:
        energyMissing > 0
          ? `${countLabel(energyMissing, 'completed session')} ${
              energyMissing === 1 ? 'is' : 'are'
            } missing measured energy, so energy totals may be incomplete.`
          : completed > 0
            ? `All ${countLabel(completed, 'completed session')} have measured energy.`
            : 'No completed charging sessions are available to check yet.',
    },
    {
      key: 'charger-readings',
      title: 'Charger readings',
      state: unlinked > 0 ? 'attention' : 'ok',
      status: unlinked > 0 ? 'Needs attention' : 'Good',
      description:
        unlinked > 0
          ? `${countLabel(unlinked, 'connected reading')} ${
              unlinked === 1 ? 'was' : 'were'
            } not attached to a session in the last 24 hours.`
          : 'All connected charger readings were attached to a session in the last 24 hours.',
    },
    {
      key: 'home-energy',
      title: 'Car vs home energy',
      state: !data.consumptionConfigured
        ? 'neutral'
        : uncertain > 0
          ? 'attention'
          : 'ok',
      status: !data.consumptionConfigured
        ? 'Not set up'
        : uncertain > 0
          ? 'Needs attention'
          : 'Good',
      description: !data.consumptionConfigured
        ? 'Household energy checks will appear after Octopus consumption is configured.'
        : uncertain > 0
          ? `${countLabel(uncertain, 'half-hour period')} could not be confidently split between the car and home in the last 30 days.`
          : 'Every imported half-hour period was confidently split between the car and home.',
    },
  ];
  const attentionChecks = checks.filter((check) => check.state === 'attention');
  const remainingChecks = checks.filter((check) => check.state !== 'attention');

  if (data.status === 'unavailable') {
    return (
      <div className="quality-panel">
        <div className="quality-overview unavailable" role="status">
          <span className="quality-overview-icon" aria-hidden="true">?</span>
          <div>
            <strong>Data checks are temporarily unavailable</strong>
            <p>Charging and target automation are unaffected. The dashboard will try again automatically.</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="quality-panel">
      <div className={`quality-overview ${issueCount > 0 ? 'attention' : 'ok'}`} role="status">
        <span className="quality-overview-icon" aria-hidden="true">
          {issueCount > 0 ? '!' : '✓'}
        </span>
        <div>
          <strong>{issueCount > 0 ? 'Some reporting data needs attention' : 'No reporting gaps found'}</strong>
          <p>
            {issueCount > 0
              ? `${dataQualityStatusLabel(data)}. Charging and target automation are unaffected.`
              : 'Configured history and energy checks are clear.'}
          </p>
        </div>
        {sessionIssueTotal > 0 && (
          <button
            type="button"
            className="quality-review-button"
            onClick={() => onReviewSessions(sessionReviewFilter)}
          >
            Review {countLabel(sessionIssueTotal, 'affected session')}
            <span aria-hidden="true">→</span>
          </button>
        )}
      </div>

      {attentionChecks.length > 0 && (
        <section className="quality-check-group" aria-labelledby="quality-attention-heading">
          <h3 id="quality-attention-heading">Needs attention</h3>
          <ul className="quality-check-list">
            {attentionChecks.map((check) => <CheckRow check={check} key={check.key} />)}
          </ul>
          <p className="quality-guidance">
            {sessionIssueTotal > 0
              ? 'Open an affected session to inspect its measurements and audit trail. Missing source data may reconcile automatically later.'
              : 'These source checks update automatically as new readings arrive.'}
          </p>
        </section>
      )}

      <section className="quality-check-group" aria-labelledby="quality-other-heading">
        <h3 id="quality-other-heading">
          {attentionChecks.length > 0 ? 'Other checks' : 'Completeness checks'}
        </h3>
        <ul className="quality-check-list">
          {remainingChecks.map((check) => <CheckRow check={check} key={check.key} />)}
        </ul>
      </section>

      <section className="quality-freshness" aria-labelledby="quality-freshness-heading">
        <div>
          <h3 id="quality-freshness-heading">Data freshness</h3>
          <p>When each reporting source was last complete or refreshed.</p>
        </div>
        <dl>
          <div>
            <dt>Daily statistics</dt>
            <dd>
              {data.daily?.completeThrough
                ? `Complete through ${dateLabel(data.daily.completeThrough)}`
                : 'No complete day available yet'}
            </dd>
          </div>
          <div>
            <dt>Household usage</dt>
            <dd>
              {data.consumptionConfigured
                ? data.consumption?.ingestedThrough
                  ? `Imported through ${dateTimeLabel(data.consumption.ingestedThrough)}`
                  : 'No household usage imported yet'
                : 'Not configured'}
            </dd>
          </div>
          <div>
            <dt>Dashboard summary</dt>
            <dd>{ageLabel(data.statisticsCache.ageSeconds)}</dd>
          </div>
          <div>
            <dt>Checks last run</dt>
            <dd>{dateTimeLabel(data.generatedAt)}</dd>
          </div>
        </dl>
      </section>
    </div>
  );
}
