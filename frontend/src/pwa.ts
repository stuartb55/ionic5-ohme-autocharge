/**
 * Register the service worker (production only). The SW provides an offline app
 * shell and handles web push. Skipped in dev to avoid interfering with Vite HMR,
 * and a no-op where the API is unavailable (e.g. tests/SSR).
 */
export function registerServiceWorker(): void {
  if (!import.meta.env.PROD) return;
  if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return;
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => undefined);
  });
}
