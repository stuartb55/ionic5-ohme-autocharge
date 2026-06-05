interface Props {
  onRefresh: () => void;
  spinning?: boolean;
}

/** Header button that re-fetches all dashboard data on demand. */
export function RefreshButton({ onRefresh, spinning = false }: Props) {
  return (
    <button
      type="button"
      className="refresh-button"
      onClick={onRefresh}
      disabled={spinning}
      aria-label="Refresh data"
      title="Refresh data"
      data-spinning={spinning || undefined}
    >
      <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false">
        <path
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M20 11a8 8 0 1 0-.7 3.3M20 5v6h-6"
        />
      </svg>
    </button>
  );
}
