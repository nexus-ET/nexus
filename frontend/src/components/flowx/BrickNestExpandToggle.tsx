import { ChevronDown, ChevronRight } from 'lucide-react';

/** Compact expand/collapse control for nested sub-processes. */
export default function BrickNestExpandToggle({
  count,
  expanded,
  onToggle,
}: {
  count: number;
  expanded: boolean;
  onToggle: () => void;
}) {
  if (count <= 0) return null;

  return (
    <button
      type="button"
      onClick={e => {
        e.stopPropagation();
        onToggle();
      }}
      aria-expanded={expanded}
      className={`mt-1 inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-semibold text-white transition ${
        expanded ? 'bg-accent/90 hover:bg-accent' : 'bg-accent hover:brightness-105'
      }`}
    >
      {expanded ? <ChevronDown size={14} strokeWidth={2.5} /> : <ChevronRight size={14} strokeWidth={2.5} />}
      <span>
        {count} nested · {expanded ? 'Collapse' : 'Expand'}
      </span>
    </button>
  );
}

export function sortedNestChildren<T extends { position_index: number; title: string }>(
  children: T[] | undefined | null
): T[] {
  return [...(children ?? [])].sort((a, b) => {
    if (a.position_index !== b.position_index) return a.position_index - b.position_index;
    return a.title.localeCompare(b.title);
  });
}
