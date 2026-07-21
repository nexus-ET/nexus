import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react';

interface FrameworkSortableHeaderProps<T extends string> {
  label: string;
  column: T;
  sortBy: T;
  sortDir: 'asc' | 'desc';
  onSort: (column: T) => void;
  className?: string;
  align?: 'left' | 'center';
  layout?: 'inline' | 'stacked';
}

function FrameworkSortableHeader<T extends string>({
  label,
  column,
  sortBy,
  sortDir,
  onSort,
  className = 'px-6 py-3 font-semibold',
  align = 'left',
  layout = 'inline',
}: FrameworkSortableHeaderProps<T>) {
  const icon =
    sortBy !== column ? (
      <ArrowUpDown size={13} />
    ) : sortDir === 'asc' ? (
      <ArrowUp size={13} />
    ) : (
      <ArrowDown size={13} />
    );

  const stacked = layout === 'stacked';

  const buttonClass = stacked
    ? 'flex w-full flex-col items-center gap-0.5 text-center hover:text-text-main'
    : align === 'center'
      ? 'flex w-full items-start justify-center gap-1 text-center hover:text-text-main'
      : 'flex w-full items-start gap-1 text-left hover:text-text-main';

  return (
    <th className={className}>
      <button type="button" onClick={() => onSort(column)} className={buttonClass}>
        <span
          className={
            stacked
              ? 'text-xs leading-tight break-words'
              : align === 'center'
                ? 'text-xs leading-tight break-words'
                : 'min-w-0 flex-1 text-xs leading-tight break-words'
          }
        >
          {label}
        </span>
        <span className="shrink-0 leading-none">{icon}</span>
      </button>
    </th>
  );
}

export default FrameworkSortableHeader;
