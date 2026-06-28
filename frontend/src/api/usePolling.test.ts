import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { usePolling } from './usePolling';

/** A promise whose resolution is controlled by the test. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

/** Flush pending microtasks + due timers under fake timers. */
async function flush(ms = 0) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('usePolling', () => {
  it('fetches immediately and exposes data + lastUpdated', async () => {
    const fetcher = vi.fn(async () => 'one');
    const { result } = renderHook(() => usePolling(fetcher, 10_000));

    await flush();
    expect(result.current.data).toBe('one');
    expect(result.current.error).toBeNull();
    expect(result.current.lastUpdated).toBeInstanceOf(Date);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it('refetches on the interval', async () => {
    const fetcher = vi.fn(async () => 'tick');
    renderHook(() => usePolling(fetcher, 10_000));

    await flush();
    expect(fetcher).toHaveBeenCalledTimes(1);
    await flush(10_000);
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it('does not let a slow earlier response overwrite a newer one', async () => {
    const first = deferred<string>();
    const second = deferred<string>();
    const fetcher = vi
      .fn<(signal: AbortSignal) => Promise<string>>()
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);

    const { result } = renderHook(() => usePolling(fetcher, 10_000));
    await flush();

    // Second tick starts before the first run resolves.
    await flush(10_000);

    // Newer run resolves first, then the stale first run resolves late.
    await act(async () => {
      second.resolve('newer');
      first.resolve('stale');
      await Promise.resolve();
    });

    expect(result.current.data).toBe('newer');
  });

  it('aborts the in-flight request on unmount', async () => {
    let captured: AbortSignal | null = null;
    const fetcher = vi.fn((signal: AbortSignal) => {
      captured = signal;
      return new Promise<string>(() => {
        /* never resolves */
      });
    });
    const { unmount } = renderHook(() => usePolling(fetcher, 10_000));

    await flush();
    expect(captured).not.toBeNull();
    expect(captured!.aborted).toBe(false);
    unmount();
    expect(captured!.aborted).toBe(true);
  });

  it('refetch() triggers an immediate extra fetch', async () => {
    const fetcher = vi.fn(async () => 'data');
    const { result } = renderHook(() => usePolling(fetcher, 100_000));

    await flush();
    expect(fetcher).toHaveBeenCalledTimes(1);
    await act(async () => {
      result.current.refetch();
    });
    await flush();
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it('surfaces a fetch error', async () => {
    const fetcher = vi.fn(async () => {
      throw new Error('boom');
    });
    const { result } = renderHook(() => usePolling(fetcher, 10_000));

    await flush();
    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.error?.message).toBe('boom');
    expect(result.current.data).toBeNull();
  });
});
