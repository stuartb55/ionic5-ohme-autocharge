import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import { usePolling } from '../api/usePolling';
import { useNow } from '../hooks/useNow';
import { relativeTime } from '../utils/format';
import { Banner } from './Banner';
import { ScheduleSection } from './ScheduleSection';
import { SessionsSection } from './SessionsSection';
import { StatisticsSection } from './StatisticsSection';
import { StatusSection } from './StatusSection';
import { ThemeToggle } from './ThemeToggle';

const STATUS_INTERVAL = 15_000;
const SCHEDULE_INTERVAL = 30_000;
const STATS_INTERVAL = 300_000;
// Sessions only change on plug-in events, so a slow poll is plenty.
const SESSIONS_INTERVAL = 300_000;

function SectionSkeleton({ height }: { height: number }) {
  return <div className="card"><div className="skeleton" style={{ height }} /></div>;
}

export function Dashboard() {
  const [days, setDays] = useState(7);
  // A ticking clock so the "updated Xs ago" label and the freshness dot stay
  // live without reading the impure Date.now() during render.
  const now = useNow(5_000);

  // Build version for the footer — fetched once; it doesn't change at runtime.
  const [version, setVersion] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    api
      .getVersion(controller.signal)
      .then((r) => setVersion(r.version))
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  const status = usePolling(api.getStatus, STATUS_INTERVAL);
  const schedule = usePolling(api.getSchedule, SCHEDULE_INTERVAL);
  const statsFetcher = useCallback((signal: AbortSignal) => api.getStatistics(days, signal), [days]);
  const stats = usePolling(statsFetcher, STATS_INTERVAL, [days]);
  const sessionsFetcher = useCallback((signal: AbortSignal) => api.getSessions(8, signal), []);
  const sessions = usePolling(sessionsFetcher, SESSIONS_INTERVAL);

  // refetch() from usePolling is stable, so these are safe to capture.
  const { refetch: refetchStatus } = status;
  const { refetch: refetchSchedule } = schedule;
  const { refetch: refetchStats } = stats;
  const { refetch: refetchSessions } = sessions;

  // Persist a new charge target, then refetch status so the UI reflects it.
  const handleSetTarget = useCallback(
    async (target: number) => {
      await api.setTarget(target);
      refetchStatus();
    },
    [refetchStatus],
  );

  // Persist (or clear) the ready-by time, then refetch status.
  const handleSetReadyBy = useCallback(
    async (value: string | null) => {
      await api.setReadyBy(value);
      refetchStatus();
    },
    [refetchStatus],
  );

  // Persist the per-weekday target overrides, then refetch status.
  const handleSetDayTargets = useCallback(
    async (map: Record<number, number>) => {
      await api.setDayTargets(map);
      refetchStatus();
    },
    [refetchStatus],
  );

  // Manual refresh: ask the backend to pull a fresh live reading from Ohme,
  // then refetch every section. Even if the force-refresh fails we still
  // refetch so the button does something (shows whatever the backend has).
  const lastFetchedMs = status.lastUpdated?.getTime();
  // Rather than toggling a flag and clearing it from an effect when new data
  // lands, record when the refresh was requested (and the fetch timestamp at
  // that moment) and *derive* whether we're still spinning: the spinner clears
  // automatically once a newer status result arrives (lastFetchedMs advances)
  // or a safety timeout elapses.
  const [refreshReq, setRefreshReq] = useState<{ at: number; since?: number } | null>(null);
  const handleRefresh = useCallback(() => {
    setRefreshReq({ at: Date.now(), since: lastFetchedMs });
    void api
      .refresh()
      .catch(() => undefined)
      .finally(() => {
        refetchStatus();
        refetchSchedule();
        refetchStats();
        refetchSessions();
      });
  }, [lastFetchedMs, refetchStatus, refetchSchedule, refetchStats, refetchSessions]);

  const refreshing =
    refreshReq != null && lastFetchedMs === refreshReq.since && now - refreshReq.at < 5_000;

  const offline = status.error && !status.data;
  // Show how long ago the *backend* last polled Ohme (updatedAt), not when the
  // browser last fetched the cached snapshot. The backend only refreshes every
  // pollIntervalSeconds, so judge freshness against that cadence (with slack).
  const lastPolled = status.data?.updatedAt ? new Date(status.data.updatedAt) : null;
  const pollMs = (status.data?.config.pollIntervalSeconds ?? 180) * 1_000;
  const fresh = lastPolled != null && now - lastPolled.getTime() < pollMs * 2;

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <h1>Autocharge</h1>
          <div className="subtitle">EV charging scheduler · IONIQ&nbsp;5 + Ohme</div>
        </div>
        <div className="app-meta">
          <span className={`live-dot ${fresh ? '' : 'stale'}`} aria-hidden="true" />
          <span>Updated {relativeTime(lastPolled, new Date(now))}</span>
          <button
            type="button"
            className={`refresh-btn ${refreshing ? 'spinning' : ''}`}
            onClick={handleRefresh}
            disabled={refreshing}
            aria-label="Refresh now"
            title="Refresh now"
          >
            <span aria-hidden="true">⟳</span>
          </button>
          <ThemeToggle />
        </div>
      </header>

      {offline && (
        <Banner variant="error">
          Can&apos;t reach the charging service. Retrying automatically…
        </Banner>
      )}
      {status.data && !status.data.ready && (
        <Banner variant="info">Connecting to Ohme — waiting for the first reading…</Banner>
      )}
      {status.data?.ready && status.data.lastError && (
        <Banner variant="error">
          Can&apos;t reach Ohme — showing the last known data. Retrying automatically…
        </Banner>
      )}

      <div className="sections">
        {status.data ? (
          <StatusSection
            status={status.data}
            onSetTarget={handleSetTarget}
            onSetReadyBy={handleSetReadyBy}
            onSetDayTargets={handleSetDayTargets}
            onChargeChanged={refetchStatus}
          />
        ) : (
          <SectionSkeleton height={260} />
        )}
        {schedule.data ? <ScheduleSection schedule={schedule.data} /> : <SectionSkeleton height={180} />}
        {stats.data ? (
          <StatisticsSection stats={stats.data} days={days} onDaysChange={setDays} />
        ) : (
          <SectionSkeleton height={320} />
        )}
        {/* No skeleton: the card may legitimately never appear (history disabled). */}
        {sessions.data && <SessionsSection data={sessions.data} />}
      </div>

      <footer className="app-footer">
        Data from Ohme &amp; Hyundai Bluelink · refreshed automatically
        {version && (
          <>
            {' · '}
            <span className="version" title={version}>
              {version === 'dev' ? 'dev' : version.slice(0, 7)}
            </span>
          </>
        )}
      </footer>
    </div>
  );
}
