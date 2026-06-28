interface Props {
  percent: number | null;
  target?: number | null;
  size?: number;
}

function ringColor(percent: number): string {
  if (percent >= 80) return 'var(--success)';
  if (percent >= 40) return 'var(--brand)';
  if (percent >= 15) return 'var(--warning)';
  return 'var(--danger)';
}

/**
 * Circular state-of-charge gauge drawn with SVG. The thin outer notch marks the
 * configured charge target so the user can see how far the current SOC is from it.
 */
export function BatteryRing({ percent, target, size = 220 }: Props) {
  const stroke = 16;
  const r = (size - stroke) / 2;
  const cx = size / 2;
  const cy = size / 2;
  const circumference = 2 * Math.PI * r;
  const known = percent !== null && !Number.isNaN(percent);
  const value = known ? Math.min(100, Math.max(0, percent as number)) : 0;
  const dash = (value / 100) * circumference;
  const color = ringColor(value);

  // Target marker angle (degrees from top, clockwise). Clamp so a misconfigured
  // target (>100 or <0) can't place the marker off the ring.
  const clampedTarget = target != null ? Math.min(100, Math.max(0, target)) : null;
  const targetAngle = clampedTarget != null ? (clampedTarget / 100) * 360 - 90 : null;
  const markerRad = targetAngle != null ? (targetAngle * Math.PI) / 180 : 0;
  const markerCos = Math.cos(markerRad);
  const markerSin = Math.sin(markerRad);
  // A short radial tick straddling the ring stroke, so the target reads as a
  // deliberate marker (a small dot was nearly invisible, and vanished under the
  // fill arc when SOC was near target).
  const tickInner = r - stroke / 2 - 2;
  const tickOuter = r + stroke / 2 + 2;

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      role="img"
      aria-label={known ? `State of charge ${Math.round(value)}%` : 'State of charge unavailable'}
    >
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--charge-track)" strokeWidth={stroke} />
      {known && (
        <circle
          cx={cx}
          cy={cy}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${dash} ${circumference}`}
          transform={`rotate(-90 ${cx} ${cy})`}
          style={{ transition: 'stroke-dasharray 0.6s ease, stroke 0.4s ease' }}
        />
      )}
      {targetAngle != null && (
        <line
          x1={cx + tickInner * markerCos}
          y1={cy + tickInner * markerSin}
          x2={cx + tickOuter * markerCos}
          y2={cy + tickOuter * markerSin}
          stroke="var(--warning)"
          strokeWidth={3}
          strokeLinecap="round"
          aria-hidden="true"
        />
      )}
      <text x={cx} y={cy - 2} textAnchor="middle" dominantBaseline="central"
        style={{ fontSize: size * 0.26, fontWeight: 750, fill: 'var(--text)' }}>
        {known ? `${Math.round(value)}` : '–'}
      </text>
      {known && (
        <text x={cx} y={cy + size * 0.16} textAnchor="middle"
          style={{ fontSize: size * 0.07, fill: 'var(--text-muted)', fontWeight: 600 }}>
          % CHARGE
        </text>
      )}
    </svg>
  );
}
