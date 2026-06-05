import type { Theme } from '../theme';
import { useTheme } from '../theme';

const OPTIONS: { value: Theme; label: string; icon: string }[] = [
  { value: 'light', label: 'Light', icon: '☀' },
  { value: 'system', label: 'System', icon: '◐' },
  { value: 'dark', label: 'Dark', icon: '☾' },
];

/** Segmented control to choose light / system / dark appearance. */
export function ThemeToggle() {
  const [theme, setTheme] = useTheme();

  return (
    <div className="theme-toggle" role="group" aria-label="Theme">
      {OPTIONS.map((opt) => (
        <button
          key={opt.value}
          type="button"
          className="theme-option"
          aria-pressed={theme === opt.value}
          onClick={() => setTheme(opt.value)}
          title={`${opt.label} theme`}
        >
          <span aria-hidden="true">{opt.icon}</span>
          <span className="sr-only">{opt.label} theme</span>
        </button>
      ))}
    </div>
  );
}
