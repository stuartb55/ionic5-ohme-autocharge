import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import { usePolling } from '../api/usePolling';
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
  const [, forceTick] = useState(0);

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

  // Manual refresh: ask the backend to pull a fresh live reading from Ohme,
  // then refetch every section. Even if the force-refresh fails we still
  // refetch so the button does something (shows whatever the backend has).
  // The button spins until the next status result lands (cleared by the effect
  // below) or a safety timeout.
  const [refreshing, setRefreshing] = useState(false);
  const handleRefresh = useCallback(() => {
    setRefreshing(true);
    void api
      .refresh()
      .catch(() => undefined)
      .finally(() => {
        refetchStatus();
        refetchSchedule();
        refetchStats();
        refetchSessions();
      });
    window.setTimeout(() => setRefreshing(false), 5_000);
  }, [refetchStatus, refetchSchedule, refetchStats, refetchSessions]);

  const lastFetchedMs = status.lastUpdated?.getTime();
  useEffect(() => {
    setRefreshing(false);
  }, [lastFetchedMs]);

  // Keep the "updated Xs ago" label fresh without refetching.
  useEffect(() => {
    const id = window.setInterval(() => forceTick((t) => t + 1), 5_000);
    return () => window.clearInterval(id);
  }, []);

  const offline = status.error && !status.data;
  // Show how long ago the *backend* last polled Ohme (updatedAt), not when the
  // browser last fetched the cached snapshot. The backend only refreshes every
  // pollIntervalSeconds, so judge freshness against that cadence (with slack).
  const lastPolled = status.data?.updatedAt ? new Date(status.data.updatedAt) : null;
  const pollMs = (status.data?.config.pollIntervalSeconds ?? 180) * 1_000;
  const fresh = lastPolled != null && Date.now() - lastPolled.getTime() < pollMs * 2;

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <h1>Autocharge</h1>
          <div className="subtitle">EV charging scheduler · IONIQ&nbsp;5 + Ohme</div>
        </div>
        <div className="app-meta">
          <span className={`live-dot ${fresh ? '' : 'stale'}`} aria-hidden="true" />
          <span>Updated {relativeTime(lastPolled)}</span>
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
      </footer>
    </div>
  );
}
