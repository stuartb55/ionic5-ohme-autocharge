import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import { urlBase64ToUint8Array } from '../utils/push';

const supported = () =>
  typeof navigator !== 'undefined' &&
  'serviceWorker' in navigator &&
  typeof window !== 'undefined' &&
  'PushManager' in window;

/**
 * A bell button to enable/disable browser push. Renders nothing unless web push
 * is configured on the server and supported by the browser.
 */
export function PushToggle() {
  const [enabled, setEnabled] = useState(false);
  const [publicKey, setPublicKey] = useState('');
  const [subscribed, setSubscribed] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .getPushConfig()
      .then((c) => {
        if (cancelled) return;
        setEnabled(c.enabled);
        setPublicKey(c.publicKey);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!enabled || !supported()) return;
    navigator.serviceWorker.ready
      .then((reg) => reg.pushManager.getSubscription())
      .then((sub) => setSubscribed(!!sub))
      .catch(() => undefined);
  }, [enabled]);

  const enable = useCallback(async () => {
    setBusy(true);
    try {
      if ((await Notification.requestPermission()) !== 'granted') return;
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(publicKey),
      });
      await api.subscribePush(sub.toJSON());
      setSubscribed(true);
    } catch {
      /* permission denied or subscribe failed — leave as unsubscribed */
    } finally {
      setBusy(false);
    }
  }, [publicKey]);

  const disable = useCallback(async () => {
    setBusy(true);
    try {
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.getSubscription();
      if (sub) {
        await api.unsubscribePush(sub.endpoint).catch(() => undefined);
        await sub.unsubscribe();
      }
      setSubscribed(false);
    } finally {
      setBusy(false);
    }
  }, []);

  if (!enabled || !supported()) return null;

  return (
    <button
      type="button"
      className="push-toggle"
      onClick={() => void (subscribed ? disable() : enable())}
      disabled={busy}
      aria-pressed={subscribed}
      title={subscribed ? 'Disable push notifications' : 'Enable push notifications'}
      aria-label={subscribed ? 'Disable push notifications' : 'Enable push notifications'}
    >
      <span aria-hidden="true">{subscribed ? '🔔' : '🔕'}</span>
    </button>
  );
}
