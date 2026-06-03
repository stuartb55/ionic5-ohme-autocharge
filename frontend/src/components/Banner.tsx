import type { ReactNode } from 'react';

export function Banner({
  variant = 'info',
  children,
}: {
  variant?: 'info' | 'error';
  children: ReactNode;
}) {
  return (
    <div className={`banner ${variant}`} role={variant === 'error' ? 'alert' : 'status'}>
      <span aria-hidden="true">{variant === 'error' ? '⚠' : 'ℹ'}</span>
      <span>{children}</span>
    </div>
  );
}
