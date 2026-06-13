import type { ChargerStatus } from '../api/types';

/** Human-friendly label for a charger status. */
export function statusLabel(status: ChargerStatus): string {
  const map: Record<ChargerStatus, string> = {
    unplugged: 'Unplugged',
    pending_approval: 'Awaiting approval',
    charging: 'Charging',
    plugged_in: 'Plugged in',
    paused: 'Paused',
    finished: 'Finished',
    unknown: 'Unknown',
  };
  return map[status] ?? 'Unknown';
}

/** Convert watts to a compact kW string, e.g. 7400 -> "7.4 kW". */
export function formatPower(watts: number): string {
  if (!watts || watts <= 0) return '0 kW';
  return `${(watts / 1000).toFixed(1)} kW`;
}

export function formatKwh(kwh: number): string {
  return `${kwh.toFixed(kwh >= 100 ? 0 : 1)} kWh`;
}

const NBSP = ' ';

export function formatMoney(amount: number, currency: string | null): string {
  if (currency) {
    try {
      return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(amount);
    } catch {
      /* fall through to plain formatting for unknown currency codes */
    }
  }
  return `${amount.toFixed(2)}${currency ? NBSP + currency : ''}`;
}

/**
 * Per-kWh energy price. Unit rates are conventionally quoted in the minor
 * currency unit (pence for GBP), so e.g. 0.125 GBP renders as "12.5p" rather
 * than the misleading "£0.13" that whole-currency formatting would produce.
 * Falls back to standard money formatting for non-GBP currencies.
 */
export function formatPricePerKwh(amount: number, currency: string | null): string {
  if (currency === 'GBP') {
    return `${(amount * 100).toFixed(1)}p`;
  }
  return formatMoney(amount, currency);
}

/** "01:00" from an ISO timestamp, in the viewer's locale time. */
export function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

/**
 * Projected charge finish: "06:30" when it's today, otherwise "Sat 06:30" —
 * overnight charges routinely finish on the next calendar day.
 */
export function formatFinishTime(iso: string, now: Date = new Date()): string {
  const d = new Date(iso);
  const time = d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  if (d.toDateString() === now.toDateString()) return time;
  return `${d.toLocaleDateString(undefined, { weekday: 'short' })} ${time}`;
}

export function formatDateShort(iso: string | null): string {
  if (!iso) return '';
  return new Date(iso).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric' });
}

/** "12s ago" / "3m ago" relative time, for the "last updated" footer. */
export function relativeTime(from: Date | null, now: Date = new Date()): string {
  if (!from) return 'never';
  const seconds = Math.max(0, Math.round((now.getTime() - from.getTime()) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  return `${hours}h ago`;
}
