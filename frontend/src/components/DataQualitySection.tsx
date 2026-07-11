import type { DataQualityResponse } from '../api/types';

function countLabel(value: number, singular: string, plural = `${singular}s`) {
  return `${value} ${value === 1 ? singular : plural}`;
}

function dateLabel(value: string | null | undefined) {
  if (!value) return 'Not available';
  return new Date(value).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}

function ageLabel(seconds: number | null) {
  if (seconds == null) return 'Not cached';
  if (seconds < 60) return `${seconds}s old`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m old`;
  return `${Math.round(seconds / 3600)}h old`;
}

export function DataQualitySection({ data }: { data: DataQualityResponse }) {
  if (!data.persistenceAvailable) return null;

  const sessions = data.sessions;
  const energyMissing = sessions?.missingActualEnergy ?? 0;
  const costMissing = data.actualCostExpected ? (sessions?.missingActualCost ?? 0) : 0;
  const unlinked = data.telemetry?.unlinkedLast24h ?? 0;
  const uncertain = data.consumption?.uncertainLast30d ?? 0;

  return (
    <section className="card quality-card" aria-labelledby="quality-heading">
      <header>
        <div>
          <p className="eyebrow">Operations</p>
          <h2 id="quality-heading">Data quality</h2>
        </div>
        <span className={`quality-summary ${data.status}`}>
          {data.status === 'ok' ? 'All checks clear' : data.status === 'attention' ? 'Review needed' : 'Unavailable'}
        </span>
      </header>

      {data.status === 'unavailable' ? (
        <p className="empty">Quality checks could not be read. The charging automation is unaffected.</p>
      ) : (
        <div className="quality-grid">
          <div className={energyMissing ? 'quality-item attention' : 'quality-item'}>
            <span>Session energy</span>
            <strong>{energyMissing ? countLabel(energyMissing, 'missing session') : 'Complete'}</strong>
            <small>{sessions?.completed ?? 0} completed sessions checked</small>
          </div>
          <div className={costMissing ? 'quality-item attention' : 'quality-item'}>
            <span>Actual cost</span>
            <strong>
              {!data.actualCostExpected
                ? 'Not configured'
                : costMissing
                  ? countLabel(costMissing, 'missing session')
                  : 'Complete'}
            </strong>
            <small>Only reconciled Agile costs count</small>
          </div>
          <div className={unlinked ? 'quality-item attention' : 'quality-item'}>
            <span>Session linkage</span>
            <strong>{unlinked ? countLabel(unlinked, 'unlinked sample') : 'Complete'}</strong>
            <small>Connected telemetry, last 24 hours</small>
          </div>
          <div className={uncertain ? 'quality-item attention' : 'quality-item'}>
            <span>Energy attribution</span>
            <strong>{uncertain ? countLabel(uncertain, 'uncertain interval') : 'Complete'}</strong>
            <small>Last 30 days</small>
          </div>
          <div className="quality-item">
            <span>Daily statistics</span>
            <strong>{dateLabel(data.daily?.completeThrough)}</strong>
            <small>Latest complete local day</small>
          </div>
          <div className="quality-item">
            <span>Ingestion &amp; cache</span>
            <strong>{dateLabel(data.consumption?.ingestedThrough)}</strong>
            <small>Statistics {ageLabel(data.statisticsCache.ageSeconds)}</small>
          </div>
        </div>
      )}

      {(energyMissing > 0 || costMissing > 0) && (
        <a className="quality-review-link" href="#sessions-heading">
          Review affected session records
        </a>
      )}
    </section>
  );
}
