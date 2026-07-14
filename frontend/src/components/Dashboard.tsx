import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import { usePolling } from '../api/usePolling';
import { useNow } from '../hooks/useNow';
import { relativeTime } from '../utils/format';
import { Banner } from './Banner';
import { ChargeSettingsSection } from './ChargeSettingsSection';
import { DataQualitySection } from './DataQualitySection';
import { EnergyUsageSection } from './EnergyUsageSection';
import { Icon } from './Icon';
import { ScheduleSection } from './ScheduleSection';
import { SessionsSection } from './SessionsSection';
import { SohTrendSection } from './SohTrendSection';
import { StatisticsSection } from './StatisticsSection';
import { StatusSection } from './StatusSection';
import { TariffSection } from './TariffSection';
import { ThemeToggle } from './ThemeToggle';
import type { ApplyStatus, NotificationPreferences, PersistenceStatus } from '../api/types';

const STATUS_INTERVAL = 15_000;
const SCHEDULE_INTERVAL = 30_000;
const STATS_INTERVAL = 300_000;
const SESSIONS_INTERVAL = 300_000;
const TARIFF_INTERVAL = 1_800_000;
const ENERGY_INTERVAL = 300_000;
const QUALITY_INTERVAL = 300_000;
const SOH_INTERVAL = 1_800_000;

function outcomeWarning(result: {
  persistenceStatus: PersistenceStatus;
  applyStatus?: ApplyStatus;
}): string | null {
  if (result.persistenceStatus === 'memory_only') {
    return 'The change is active only in memory and will be lost when the service restarts.';
  }
  if (result.applyStatus === 'failed') {
    return 'The setting was saved, but it could not be applied to the connected charger.';
  }
  return null;
}

function SectionSkeleton({ height }: { height: number }) {
  return (
    <div className="card section-skeleton" aria-hidden="true">
      <div className="skeleton skeleton-title" />
      <div className="skeleton skeleton-copy" />
      <div className="skeleton skeleton-body" style={{ height }} />
    </div>
  );
}

function CachedNotice({ children }: { children: string }) {
  return <p className="cached-notice" role="status">{children}</p>;
}

function HeaderMeta({
  lastPolled,
  pollMs,
  lastFetchedMs,
  degraded,
  onRefresh,
}: {
  lastPolled: Date | null;
  pollMs: number;
  lastFetchedMs: number | undefined;
  degraded: boolean;
  onRefresh: () => void;
}) {
  const now = useNow(5_000);
  const [refreshReq, setRefreshReq] = useState<{ at: number; since?: number } | null>(null);
  const handleClick = useCallback(() => {
    setRefreshReq({ at: Date.now(), since: lastFetchedMs });
    onRefresh();
  }, [lastFetchedMs, onRefresh]);

  const refreshing =
    refreshReq != null && lastFetchedMs === refreshReq.since && now - refreshReq.at < 8_000;
  const fresh = !degraded && lastPolled != null && now - lastPolled.getTime() < pollMs * 2;
  const state = fresh ? 'Live' : lastPolled ? 'Stale' : 'Connecting';

  return (
    <div className="app-meta">
      <div className={`freshness ${fresh ? 'live' : 'stale'}`} role="status">
        <span className="live-dot" aria-hidden="true" />
        <span>
          <strong>{state}</strong>
          <small>{refreshing ? 'Refreshing…' : `Updated ${relativeTime(lastPolled, new Date(now))}`}</small>
        </span>
      </div>
      <button
        type="button"
        className={`refresh-btn ${refreshing ? 'spinning' : ''}`}
        onClick={handleClick}
        disabled={refreshing}
        aria-label="Refresh now"
        title="Refresh all dashboard data"
      >
        <span aria-hidden="true">↻</span>
      </button>
      <ThemeToggle />
    </div>
  );
}

function SectionError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="card section-error" role="status">
      <span>{message}</span>
      <button type="button" className="ghost-button" onClick={onRetry}>Retry</button>
    </div>
  );
}

export function Dashboard() {
  const [days, setDays] = useState(7);
  const [mutationWarning, setMutationWarning] = useState<string | null>(null);
  const [version, setVersion] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    api
      .getVersion(controller.signal)
      .then((result) => setVersion(result.version))
      .catch((error) => {
        if (!controller.signal.aborted) console.debug('version fetch failed', error);
      });
    return () => controller.abort();
  }, []);

  const status = usePolling(api.getStatus, STATUS_INTERVAL);
  const schedule = usePolling(api.getSchedule, SCHEDULE_INTERVAL);
  const statsFetcher = useCallback((signal: AbortSignal) => api.getStatistics(days, signal), [days]);
  const stats = usePolling(statsFetcher, STATS_INTERVAL, [days]);
  const sessionsFetcher = useCallback((signal: AbortSignal) => api.getSessions(8, signal), []);
  const sessions = usePolling(sessionsFetcher, SESSIONS_INTERVAL);
  const tariff = usePolling(api.getTariff, TARIFF_INTERVAL);
  const sohFetcher = useCallback((signal: AbortSignal) => api.getSohHistory(90, signal), []);
  const soh = usePolling(sohFetcher, SOH_INTERVAL);
  const [energyDate, setEnergyDate] = useState<string | null>(null);
  const energyFetcher = useCallback(
    (signal: AbortSignal) => api.getEnergyUsage(energyDate ?? undefined, signal),
    [energyDate],
  );
  const energy = usePolling(energyFetcher, ENERGY_INTERVAL, [energyDate]);
  const quality = usePolling(api.getDataQuality, QUALITY_INTERVAL);

  const { refetch: refetchStatus } = status;
  const { refetch: refetchSchedule } = schedule;
  const { refetch: refetchStats } = stats;
  const { refetch: refetchSessions } = sessions;
  const { refetch: refetchQuality } = quality;
  const { refetch: refetchTariff } = tariff;
  const { refetch: refetchSoh } = soh;
  const { refetch: refetchEnergy } = energy;

  const handleSetTarget = useCallback(async (target: number) => {
    const result = await api.setTarget(target);
    setMutationWarning(outcomeWarning(result));
    refetchStatus();
  }, [refetchStatus]);

  const handleSetReadyBy = useCallback(async (value: string | null) => {
    const result = await api.setReadyBy(value);
    setMutationWarning(outcomeWarning(result));
    refetchStatus();
  }, [refetchStatus]);

  const handleSetDayTargets = useCallback(async (map: Record<number, number>) => {
    const result = await api.setDayTargets(map);
    setMutationWarning(outcomeWarning(result));
    refetchStatus();
  }, [refetchStatus]);

  const handleSetTripMode = useCallback(
    async (enabled: boolean, target: number, readyBy: string | null) => {
      const result = await api.setTripMode(enabled, target, readyBy);
      setMutationWarning(outcomeWarning(result));
      refetchStatus();
      refetchSchedule();
    },
    [refetchStatus, refetchSchedule],
  );

  const handleSetNotifications = useCallback(
    async (preferences: Omit<NotificationPreferences, 'configured'>) => {
      const result = await api.setNotificationPreferences(preferences);
      setMutationWarning(outcomeWarning(result));
      refetchStatus();
    },
    [refetchStatus],
  );

  const lastFetchedMs = status.lastUpdated?.getTime();
  const handleRefresh = useCallback(() => {
    setMutationWarning(null);
    void api
      .refresh()
      .catch(() => {
        setMutationWarning('The live charger refresh failed. Showing the latest cached readings.');
      })
      .finally(() => {
        refetchStatus();
        refetchSchedule();
        refetchStats();
        refetchSessions();
        refetchQuality();
        refetchTariff();
        refetchSoh();
        refetchEnergy();
      });
  }, [
    refetchStatus,
    refetchSchedule,
    refetchStats,
    refetchSessions,
    refetchQuality,
    refetchTariff,
    refetchSoh,
    refetchEnergy,
  ]);

  const offline = status.error && !status.data;
  const degraded = Boolean(status.error || status.data?.lastError);
  const lastPolled = status.data?.updatedAt ? new Date(status.data.updatedAt) : null;
  const pollMs = (status.data?.config.pollIntervalSeconds ?? 180) * 1_000;

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-brand">
          <span className="brand-mark"><Icon name="bolt" size={23} /></span>
          <div>
            <p className="app-kicker">Home charging</p>
            <h1>Autocharge</h1>
            <p className="subtitle">
              {status.data?.vehicle.name ?? 'Hyundai IONIQ 5'} · managed by Ohme
            </p>
          </div>
        </div>
        <HeaderMeta
          lastPolled={lastPolled}
          pollMs={pollMs}
          lastFetchedMs={lastFetchedMs}
          degraded={degraded}
          onRefresh={handleRefresh}
        />
      </header>

      <div className="banner-stack">
        {offline && <Banner variant="error">Can&apos;t reach the charging service. Retrying automatically…</Banner>}
        {status.data && degraded && (
          <Banner variant="error">Can&apos;t reach Ohme — showing the latest saved data while we retry.</Banner>
        )}
        {status.data && !status.data.ready && (
          <Banner>Connecting to Ohme — waiting for the first reading…</Banner>
        )}
        {status.data?.automation.state === 'pending' && (
          <Banner>Configuring this plug-in session…</Banner>
        )}
        {status.data?.automation.state === 'error' && (
          <Banner variant="error">Charge automation could not configure this plug-in session. Retrying automatically…</Banner>
        )}
        {mutationWarning && <Banner variant="error">{mutationWarning}</Banner>}
      </div>

      <main className="sections" aria-busy={status.loading && !status.data}>
        <div className="dashboard-overview">
          {status.data ? (
            <StatusSection status={status.data} onChargeChanged={refetchStatus} />
          ) : status.error ? (
            <SectionError message="Couldn’t load live charging status." onRetry={refetchStatus} />
          ) : (
            <SectionSkeleton height={500} />
          )}

          <aside className="overview-sidebar" aria-label="Charge plan and preferences">
            {schedule.data ? (
              <div className="data-block">
                {schedule.error && <CachedNotice>Schedule update failed — showing the previous plan.</CachedNotice>}
                <ScheduleSection schedule={schedule.data} />
              </div>
            ) : schedule.error ? (
              <SectionError message="Couldn’t load the charge schedule." onRetry={refetchSchedule} />
            ) : (
              <SectionSkeleton height={260} />
            )}
            {status.data && (
              <ChargeSettingsSection
                status={status.data}
                onSetTarget={handleSetTarget}
                onSetReadyBy={handleSetReadyBy}
                onSetDayTargets={handleSetDayTargets}
                onSetTripMode={handleSetTripMode}
                onSetNotifications={handleSetNotifications}
              />
            )}
          </aside>
        </div>

        <div className="section-heading" id="insights">
          <div>
            <p className="eyebrow">Costs &amp; energy</p>
            <h2>See what home charging is doing for you</h2>
          </div>
          <p>Complete days only, so totals do not move underneath you.</p>
        </div>

        {stats.data ? (
          <div className="data-block">
            {stats.error && <CachedNotice>Statistics update failed — showing the last validated totals.</CachedNotice>}
            <StatisticsSection stats={stats.data} days={days} onDaysChange={setDays} />
          </div>
        ) : stats.error ? (
          <SectionError message="Couldn’t load charging costs and energy." onRetry={refetchStats} />
        ) : (
          <SectionSkeleton height={360} />
        )}

        <div className="section-heading" id="history">
          <div>
            <p className="eyebrow">History &amp; trends</p>
            <h2>Recent charging activity</h2>
          </div>
          <p>Open a session when you need the underlying measurements.</p>
        </div>

        <div className="dashboard-secondary">
          {sessions.data ? (
            <div className="data-block history-block">
              {sessions.error && <CachedNotice>History update failed — showing saved sessions.</CachedNotice>}
              <SessionsSection data={sessions.data} />
            </div>
          ) : sessions.error ? (
            <SectionError message="Couldn’t load recent sessions." onRetry={refetchSessions} />
          ) : null}
          {soh.data?.enabled ? (
            <div className="data-block">
              {soh.error && <CachedNotice>Battery-health update failed — showing saved data.</CachedNotice>}
              <SohTrendSection data={soh.data} />
            </div>
          ) : soh.error && !soh.data ? (
            <SectionError message="Couldn’t load battery health." onRetry={refetchSoh} />
          ) : null}
          {tariff.data?.enabled ? (
            <div className="data-block">
              {tariff.error && <CachedNotice>Price update failed — showing saved rates.</CachedNotice>}
              <TariffSection data={tariff.data} />
            </div>
          ) : tariff.error && !tariff.data ? (
            <SectionError message="Couldn’t load tariff prices." onRetry={refetchTariff} />
          ) : null}
          {energy.data?.enabled ? (
            <div className="data-block energy-block">
              {energy.error && <CachedNotice>Energy update failed — showing saved usage.</CachedNotice>}
              <EnergyUsageSection data={energy.data} onDateChange={setEnergyDate} />
            </div>
          ) : energy.error && !energy.data ? (
            <SectionError message="Couldn’t load household energy." onRetry={refetchEnergy} />
          ) : null}
        </div>

        {quality.data?.persistenceAvailable && (
          <details className="diagnostics" open={quality.data.status === 'attention' || undefined}>
            <summary>
              <span>
                <strong>Diagnostics &amp; data checks</strong>
                <small>Technical completeness and ingestion status</small>
              </span>
              <span className={`quality-summary ${quality.data.status}`}>
                {quality.data.status === 'ok' ? 'All checks clear' : 'Review needed'}
              </span>
            </summary>
            {quality.error && <CachedNotice>Diagnostics update failed — showing the previous checks.</CachedNotice>}
            <DataQualitySection data={quality.data} />
          </details>
        )}
      </main>

      <footer className="app-footer">
        <span>Ohme + Hyundai Bluelink</span>
        <span>Refreshes automatically</span>
        {version && <span className="version" title={version}>{version === 'dev' ? 'dev' : version.slice(0, 7)}</span>}
      </footer>
    </div>
  );
}
