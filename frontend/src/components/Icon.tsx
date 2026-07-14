import type { ReactNode } from 'react';

export type IconName =
  | 'bolt'
  | 'calendar'
  | 'clock'
  | 'energy'
  | 'plug'
  | 'route'
  | 'wallet';

const paths: Record<IconName, ReactNode> = {
  bolt: <path d="m13 2-9 12h7l-1 8 10-13h-7V2Z" />,
  calendar: (
    <>
      <rect x="3" y="5" width="18" height="16" rx="3" />
      <path d="M8 3v4M16 3v4M3 10h18" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3.5 2" />
    </>
  ),
  energy: (
    <>
      <rect x="3" y="6" width="17" height="12" rx="3" />
      <path d="M20 10h1.5v4H20M9.5 9 7 13h3l-.5 2L13 11h-3l.5-2Z" />
    </>
  ),
  plug: (
    <>
      <path d="M8 3v5M16 3v5M6 8h12v2a6 6 0 0 1-6 6 6 6 0 0 1-6-6V8Z" />
      <path d="M12 16v5" />
    </>
  ),
  route: (
    <>
      <circle cx="6" cy="18" r="2.5" />
      <circle cx="18" cy="6" r="2.5" />
      <path d="M8.5 18h2a3 3 0 0 0 3-3 3 3 0 0 0-3-3h3a3 3 0 0 0 3-3V8.5" />
    </>
  ),
  wallet: (
    <>
      <path d="M4 6.5h14a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H5a3 3 0 0 1-3-3V7a3 3 0 0 1 3-3h11v2.5" />
      <path d="M15 11h5v5h-5a2.5 2.5 0 0 1 0-5Z" />
    </>
  ),
};

export function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  return (
    <svg
      className="icon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}
