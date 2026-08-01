const ITEMS = [
  ['today', 'Today'],
  ['plan', 'Plan'],
  ['insights', 'Insights'],
  ['history', 'History'],
  ['settings', 'Settings'],
] as const;

export function SectionNav() {
  return (
    <nav className="section-nav" aria-label="Dashboard sections">
      {ITEMS.map(([id, label]) => <a key={id} href={`#${id}`}>{label}</a>)}
    </nav>
  );
}
