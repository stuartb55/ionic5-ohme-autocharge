import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import { usePolling } from '../api/usePolling';
import { useNow } from '../hooks/useNow';
import { relativeTime } from '../utils/format';
import { Banner } from './Banner';
import { ChargeSettingsSection } from './ChargeSettingsSection';
import { DataQualitySection } from './DataQualitySection';
import { EnergyUsageSection } from './EnergyUsageSection';
import { ScheduleSection } from './ScheduleSection';
import { SessionsSection } from './SessionsSection';
import { SohTrendSection } from './SohTrendSection';
import { StatisticsSection } from './StatisticsSection';
import { StatusSection } from './StatusSection';
import { TariffSection } from './TariffSection';
import { ThemeToggle } from './ThemeToggle';
import { VehiclePicker } from './VehiclePicker';
import type {
  ApplyStatus,
  NotificationPreferences,
  PersistenceStatus,
  VehiclesResponse,
} from '../api/types';

const STATUS_INTERVAL = 15_000;
const SCHEDULE_INTERVAL = 30_000;
const STATS_INTERVAL = 300_000;
// Sessions only change on plug-in events, so a slow poll is plenty.
const SESSIONS_INTERVAL = 300_000;
const TARIFF_INTERVAL = 1_800_000; // 30 min
// Household consumption lags ~a day and only updates on the backend's slow
// ingest cadence, so a 5-min poll is more than enough.
const ENERGY_INTERVAL = 300_000;
const QUALITY_INTERVAL = 300_000;
// SoH only moves a fraction of a percent over months — refresh rarely.
const SOH_INTERVAL = 1_800_000; // 30 min

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

/**
 * Header freshness chip + manual-refresh button. Owns its own ticking clock so
 * the 5s "Updated Xs ago" / freshness tick re-renders only this chip, not the
 * whole dashboard (the charts, sessions and tariff don't consume `now`).
 */
function HeaderMeta({
  lastPolled,
  pollMs,
  lastFetchedMs,
  onRefresh,
}: {
  lastPolled: Date | null;
  pollMs: number;
  lastFetchedMs: number | undefined;
  onRefresh: () => void;
}) {
  const now = useNow(5_000);
  // Record when refresh was requested (and the fetch timestamp then) and derive
  // whether we're still spinning: it clears once a newer status result arrives
  // (lastFetchedMs advances) or a safety timeout elapses.
  const [refreshReq, setRefreshReq] = useState<{ at: number; since?: number } | null>(null);
  const handleClick = useCallback(() => {
    setRefreshReq({ at: Date.now(), since: lastFetchedMs });
    onRefresh();
  }, [lastFetchedMs, onRefresh]);

  const refreshing =
    refreshReq != null && lastFetchedMs === refreshReq.since && now - refreshReq.at < 5_000;
  const fresh = lastPolled != null && now - lastPolled.getTime() < pollMs * 2;

  return (
    <div className="app-meta">
      <span className={`live-dot ${fresh ? '' : 'stale'}`} aria-hidden="true" />
      <span aria-live="polite">{refreshing ? 'Refreshing…' : `Updated ${relativeTime(lastPolled, new Date(now))}`}</span>
      <button
        type="button"
        className={`refresh-btn ${refreshing ? 'spinning' : ''}`}
        onClick={handleClick}
        disabled={refreshing}
        aria-label="Refresh now"
        title="Refresh now"
      >
        <span aria-hidden="true">⟳</span>
      </button>
      <ThemeToggle />
    </div>
  );
}

function SectionError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="card section-error" role="status">
      <span>{message}</span>
      <button type="button" className="ghost-button" onClick={onRetry}>
        Retry
      </button>
    </div>
  );
}

export function Dashboard() {
  const [days, setDays] = useState(7);
  const [mutationWarning, setMutationWarning] = useState<string | null>(null);

  // Build version for the footer — fetched once; it doesn't change at runtime.
  const [version, setVersion] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    api
      .getVersion(controller.signal)
      .then((r) => setVersion(r.version))
      .catch((err) => {
        if (!controller.signal.aborted) console.debug('version fetch failed', err);
      });
    return () => controller.abort();
  }, []);

  // Account vehicles — fetched on demand (a live Bluelink call), so not polled.
  // The picker only appears when there's more than one.
  const [vehicles, setVehicles] = useState<VehiclesResponse | null>(null);
  const loadVehicles = useCallback((signal?: AbortSignal) => {
    api
      .getVehicles(signal)
      .then(setVehicles)
      .catch((err) => {
        if (!signal?.aborted) console.debug('vehicle list fetch failed', err);
      });
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    loadVehicles(controller.signal);
    return () => controller.abort();
  }, [loadVehicles]);

  const status = usePolling(api.getStatus, STATUS_INTERVAL);
  const schedule = usePolling(api.getSchedule, SCHEDULE_INTERVAL);
  const statsFetcher = useCallback((signal: AbortSignal) => api.getStatistics(days, signal), [days]);
  const stats = usePolling(statsFetcher, STATS_INTERVAL, [days]);
  const sessionsFetcher = useCallback((signal: AbortSignal) => api.getSessions(8, signal), []);
  const sessions = usePolling(sessionsFetcher, SESSIONS_INTERVAL);
  // Agile rates change at most once a day; a slow poll is plenty.
  const tariff = usePolling(api.getTariff, TARIFF_INTERVAL);
  const sohFetcher = useCallback((signal: AbortSignal) => api.getSohHistory(90, signal), []);
  const soh = usePolling(sohFetcher, SOH_INTERVAL);
  // Household-vs-car energy. null = the backend default (yesterday); the user
  // can page to earlier days via the card's day selector.
  const [energyDate, setEnergyDate] = useState<string | null>(null);
  const energyFetcher = useCallback(
    (signal: AbortSignal) => api.getEnergyUsage(energyDate ?? undefined, signal),
    [energyDate],
  );
  const energy = usePolling(energyFetcher, ENERGY_INTERVAL, [energyDate]);
  const quality = usePolling(api.getDataQuality, QUALITY_INTERVAL);

  // refetch() from usePolling is stable, so these are safe to capture.
  const { refetch: refetchStatus } = status;
  const { refetch: refetchSchedule } = schedule;
  const { refetch: refetchStats } = stats;
  const { refetch: refetchSessions } = sessions;
  const { refetch: refetchQuality } = quality;
  const { refetch: refetchTariff } = tariff;
  const { refetch: refetchSoh } = soh;
  const { refetch: refetchEnergy } = energy;

  // Persist a new charge target, then refetch status so the UI reflects it.
  const handleSetTarget = useCallback(
    async (target: number) => {
      const result = await api.setTarget(target);
      setMutationWarning(outcomeWarning(result));
      refetchStatus();
    },
    [refetchStatus],
  );

  // Persist (or clear) the ready-by time, then refetch status.
  const handleSetReadyBy = useCallback(
    async (value: string | null) => {
      const result = await api.setReadyBy(value);
      setMutationWarning(outcomeWarning(result));
      refetchStatus();
    },
    [refetchStatus],
  );

  // Persist the per-weekday target overrides, then refetch status.
  const handleSetDayTargets = useCallback(
    async (map: Record<number, number>) => {
      const result = await api.setDayTargets(map);
      setMutationWarning(outcomeWarning(result));
      refetchStatus();
    },
    [refetchStatus],
  );

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

  const handleSetVehicleProfile = useCallback(
    async (vehicleId: string, enabled: boolean, target: number, readyBy: string | null) => {
      const result = await api.setVehicleProfile(vehicleId, enabled, target, readyBy);
      setMutationWarning(outcomeWarning(result));
      refetchStatus();
      refetchSchedule();
    },
    [refetchStatus, refetchSchedule],
  );

  // Switch the tracked Hyundai vehicle, then refresh vehicles + status.
  const handleSelectVehicle = useCallback(
    async (id: string) => {
      const result = await api.setVehicle(id);
      setMutationWarning(outcomeWarning(result));
      loadVehicles();
      refetchStatus();
    },
    [loadVehicles, refetchStatus],
  );

  // Manual refresh: ask the backend to pull a fresh live reading from Ohme,
  // then refetch every section. Even if the force-refresh fails we still
  // refetch so the button does something (shows whatever the backend has). The
  // spinner state lives in HeaderMeta (which owns the ticking clock).
  const lastFetchedMs = status.lastUpdated?.getTime();
  const handleRefresh = useCallback(() => {
    void api
      .refresh()
      .catch(() => undefined)
      .finally(() => {
        refetchStatus();
        refetchSchedule();
        refetchStats();
        refetchSessions();
        refetchQuality();
      });
  }, [refetchStatus, refetchSchedule, refetchStats, refetchSessions, refetchQuality]);

  const offline = status.error && !status.data;
  // Show how long ago the *backend* last polled Ohme (updatedAt), not when the
  // browser last fetched the cached snapshot. The backend only refreshes every
  // pollIntervalSeconds, so judge freshness against that cadence (with slack).
  const lastPolled = status.data?.updatedAt ? new Date(status.data.updatedAt) : null;
  const pollMs = (status.data?.config.pollIntervalSeconds ?? 180) * 1_000;
  const activeVehicle = vehicles?.vehicles.find((vehicle) => vehicle.id === vehicles.selected)
    ?? vehicles?.vehicles[0];

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <h1>Autocharge</h1>
          <div className="subtitle">Smart EV charging · Hyundai Bluelink + Ohme</div>
        </div>
        <HeaderMeta
          lastPolled={lastPolled}
          pollMs={pollMs}
          lastFetchedMs={lastFetchedMs}
          onRefresh={handleRefresh}
        />
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
      {status.data?.automation.state === 'pending' && (
        <Banner variant="info">Configuring this plug-in session…</Banner>
      )}
      {status.data?.automation.state === 'error' && (
        <Banner variant="error">
          Charge automation could not configure this plug-in session. Retrying automatically…
        </Banner>
      )}
      {mutationWarning && <Banner variant="error">{mutationWarning}</Banner>}

      {vehicles && vehicles.vehicles.length > 1 && (
        <div className="vehicle-bar">
          <VehiclePicker
            vehicles={vehicles.vehicles}
            selected={vehicles.selected}
            onSelect={handleSelectVehicle}
          />
        </div>
      )}

      <main className="sections" aria-busy={status.loading && !status.data}>
        <div className="dashboard-overview">
          {status.data ? (
            <StatusSection status={status.data} onChargeChanged={refetchStatus} />
          ) : status.error ? (
            <SectionError message="Couldn’t load live charging status." onRetry={refetchStatus} />
          ) : (
            <SectionSkeleton height={420} />
          )}
          {schedule.data ? (
            <ScheduleSection schedule={schedule.data} />
          ) : schedule.error ? (
            <SectionError message="Couldn’t load the charge schedule." onRetry={refetchSchedule} />
          ) : (
            <SectionSkeleton height={320} />
          )}
        </div>
        {status.data && (
          <ChargeSettingsSection
            status={status.data}
            onSetTarget={handleSetTarget}
            onSetReadyBy={handleSetReadyBy}
            onSetDayTargets={handleSetDayTargets}
            onSetTripMode={handleSetTripMode}
            onSetNotifications={handleSetNotifications}
            activeVehicle={activeVehicle}
            onSetVehicleProfile={handleSetVehicleProfile}
          />
        )}
        {stats.data ? (
          <StatisticsSection stats={stats.data} days={days} onDaysChange={setDays} />
        ) : stats.error ? (
          <SectionError message="Couldn’t load statistics." onRetry={refetchStats} />
        ) : (
          <SectionSkeleton height={320} />
        )}
        <div className="dashboard-secondary">
          {sessions.data ? <SessionsSection data={sessions.data} /> : sessions.error ? (
            <SectionError message="Couldn’t load recent sessions." onRetry={refetchSessions} />
          ) : null}
          {soh.data?.enabled ? <SohTrendSection data={soh.data} /> : soh.error ? (
            <SectionError message="Couldn’t load battery health." onRetry={refetchSoh} />
          ) : null}
          {tariff.data?.enabled ? <TariffSection data={tariff.data} /> : tariff.error ? (
            <SectionError message="Couldn’t load tariff prices." onRetry={refetchTariff} />
          ) : null}
          {energy.data?.enabled ? (
            <EnergyUsageSection data={energy.data} onDateChange={setEnergyDate} />
          ) : energy.error ? (
            <SectionError message="Couldn’t load household energy." onRetry={refetchEnergy} />
          ) : null}
          {quality.data ? <DataQualitySection data={quality.data} /> : quality.error ? (
            <SectionError message="Couldn’t load data quality." onRetry={refetchQuality} />
          ) : null}
        </div>
      </main>

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
