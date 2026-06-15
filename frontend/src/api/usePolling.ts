import { useCallback, useEffect, useRef, useState } from 'react';

export interface PollingState<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
  lastUpdated: Date | null;
  refetch: () => void;
}

/**
 * Fetch `fetcher` immediately and then every `intervalMs`. Keeps the previous
 * data visible while refetching so the UI never flashes empty on each tick.
 * Aborts the in-flight request on unmount.
 */
export function usePolling<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  intervalMs: number,
  deps: readonly unknown[] = [],
): PollingState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [tick, setTick] = useState(0);

  // Keep the latest fetcher without making it a dependency of the effect. The
  // ref is synced in an effect (not during render) so the next interval tick
  // always calls the current fetcher; the initial value covers the first run.
  const fetcherRef = useRef(fetcher);
  useEffect(() => {
    fetcherRef.current = fetcher;
  });

  const refetch = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    let cancelled = false;
    let runId = 0;
    let inFlight: AbortController | null = null;

    const run = async () => {
      // Abort any still-in-flight request and tag this run, so a slow earlier
      // response can never overwrite the data from a newer tick.
      inFlight?.abort();
      const controller = new AbortController();
      inFlight = controller;
      const myRun = ++runId;
      try {
        const result = await fetcherRef.current(controller.signal);
        if (cancelled || myRun !== runId) return;
        setData(result);
        setError(null);
        setLastUpdated(new Date());
      } catch (err) {
        if (cancelled || controller.signal.aborted || myRun !== runId) return;
        setError(err instanceof Error ? err : new Error(String(err)));
      } finally {
        if (!cancelled && myRun === runId) setLoading(false);
      }
    };

    run();
    const id = window.setInterval(run, intervalMs);
    return () => {
      cancelled = true;
      inFlight?.abort();
      window.clearInterval(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, tick, ...deps]);

  return { data, error, loading, lastUpdated, refetch };
}
