import { useEffect, useState } from 'react';

/**
 * Returns a `now` timestamp (epoch ms) that refreshes on an interval. Values
 * derived from the current time (e.g. "is this still fresh?", "has the finish
 * time passed?") can be computed from this instead of reading the impure
 * `Date.now()` during render — the value is stable between ticks, so renders
 * stay pure (react-hooks/purity), while the interval keeps the UI live.
 */
export function useNow(intervalMs: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs]);
  return now;
}
