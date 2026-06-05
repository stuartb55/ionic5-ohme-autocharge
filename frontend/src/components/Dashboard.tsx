import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import { usePolling } from '../api/usePolling';
import { relativeTime } from '../utils/format';
import { RefreshButton } from './RefreshButton';
import { Banner } from './Banner';
import { ScheduleSection } from './ScheduleSection';
import { StatisticsSection } from './StatisticsSection';
import { StatusSection } from './StatusSection';

const STATUS_INTERVAL = 15_000;
const SCHEDULE_INTERVAL = 30_000;
const STATS_INTERVAL = 300_000;

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

  const [refreshing, setRefreshing] = useState(false);
  const spinTimer = useRef<number | undefined>(undefined);

  // refetch() from usePolling is stable, so this is safe to capture.
  const refetchStatus = status.refetch;
  const refetchSchedule = schedule.refetch;
  const refetchStats = stats.refetch;

  const handleRefresh = useCallback(() => {
    refetchStatus();
    refetchSchedule();
    refetchStats();
    // Brief spin so the click registers visually even when the new data is
    // identical to what's already on screen.
    setRefreshing(true);
    window.clearTimeout(spinTimer.current);
    spinTimer.current = window.setTimeout(() => setRefreshing(false), 800);
  }, [refetchStatus, refetchSchedule, refetchStats]);

  // Keep the "updated Xs ago" label fresh without refetching.
  useEffect(() => {
    const id = window.setInterval(() => forceTick((t) => t + 1), 5_000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => () => window.clearTimeout(spinTimer.current), []);

  const offline = status.error && !status.data;
  const fresh = status.lastUpdated && Date.now() - status.lastUpdated.getTime() < STATUS_INTERVAL * 2;

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <h1>Autocharge</h1>
          <div className="subtitle">EV charging scheduler · IONIQ&nbsp;5 + Ohme</div>
        </div>
        <div className="app-meta">
          <span className={`live-dot ${fresh ? '' : 'stale'}`} aria-hidden="true" />
          <span>Updated {relativeTime(status.lastUpdated)}</span>
          <RefreshButton onRefresh={handleRefresh} spinning={refreshing} />
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

      <div className="sections">
        {status.data ? <StatusSection status={status.data} /> : <SectionSkeleton height={260} />}
        {schedule.data ? <ScheduleSection schedule={schedule.data} /> : <SectionSkeleton height={180} />}
        {stats.data ? (
          <StatisticsSection stats={stats.data} days={days} onDaysChange={setDays} />
        ) : (
          <SectionSkeleton height={320} />
        )}
      </div>

      <footer className="app-footer">
        Data from Ohme &amp; Hyundai Bluelink · refreshed automatically
      </footer>
    </div>
  );
}
