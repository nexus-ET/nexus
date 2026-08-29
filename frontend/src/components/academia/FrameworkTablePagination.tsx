export const FRAMEWORK_PAGE_SIZE_OPTIONS = [20, 50, 100] as const;

interface FrameworkTablePaginationProps {
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  pageSizeOptions?: readonly number[];
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
  /** Top bar uses bottom border; bottom bar uses top border (default). */
  variant?: 'top' | 'bottom';
}

type PageToken = number | 'ellipsis';

function range(from: number, to: number): number[] {
  const items: number[] = [];
  for (let i = from; i <= to; i += 1) items.push(i);
  return items;
}

/** Compact window: 1 … 8 9 10 … 42 */
function pageNumberSequence(current: number, pageCount: number, siblingCount = 1): PageToken[] {
  if (pageCount <= 1) return pageCount === 1 ? [1] : [];

  const totalSlots = siblingCount * 2 + 5;
  if (pageCount <= totalSlots) return range(1, pageCount);

  const leftSibling = Math.max(current - siblingCount, 1);
  const rightSibling = Math.min(current + siblingCount, pageCount);
  const showLeftEllipsis = leftSibling > 2;
  const showRightEllipsis = rightSibling < pageCount - 1;

  if (!showLeftEllipsis && showRightEllipsis) {
    const leftCount = 3 + 2 * siblingCount;
    return [...range(1, leftCount), 'ellipsis', pageCount];
  }
  if (showLeftEllipsis && !showRightEllipsis) {
    const rightCount = 3 + 2 * siblingCount;
    return [1, 'ellipsis', ...range(pageCount - rightCount + 1, pageCount)];
  }
  return [1, 'ellipsis', ...range(leftSibling, rightSibling), 'ellipsis', pageCount];
}

const pageButtonClass =
  'min-w-8 rounded-lg border px-2 py-1 font-semibold disabled:opacity-40';

const FrameworkTablePagination: React.FC<FrameworkTablePaginationProps> = ({
  page,
  pageSize,
  total,
  totalPages,
  pageSizeOptions = FRAMEWORK_PAGE_SIZE_OPTIONS,
  onPageChange,
  onPageSizeChange,
  variant = 'bottom',
}) => {
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);
  const pageCount = Math.max(totalPages, Math.ceil(total / pageSize) || 0, total === 0 ? 0 : 1);
  const tokens = pageNumberSequence(page, pageCount);
  const borderClass = variant === 'top' ? 'border-b' : 'border-t';

  return (
    <div
      className={`flex flex-wrap items-center justify-between gap-3 ${borderClass} border-border-subtle px-6 py-4 text-sm`}
    >
      <div className="text-text-muted">
        Showing {from}–{to} of {total}
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-text-muted">
          Page size
          <select
            value={pageSize}
            onChange={event => onPageSizeChange(Number(event.target.value))}
            className="rounded-lg border border-border-subtle bg-surface-bg px-2 py-1 text-text-main"
          >
            {pageSizeOptions.map(size => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => onPageChange(Math.max(1, page - 1))}
            className="rounded-lg border border-border-subtle px-3 py-1 font-semibold text-text-main disabled:opacity-40"
          >
            Previous
          </button>
          {tokens.map((token, index) =>
            token === 'ellipsis' ? (
              <span key={`ellipsis-${index}`} className="px-1 text-text-muted" aria-hidden>
                …
              </span>
            ) : (
              <button
                key={token}
                type="button"
                aria-current={token === page ? 'page' : undefined}
                aria-label={`Page ${token}`}
                onClick={() => onPageChange(token)}
                className={`${pageButtonClass} ${
                  token === page
                    ? 'border-accent bg-accent text-text-dark-bg'
                    : 'border-border-subtle text-text-main'
                }`}
              >
                {token}
              </button>
            )
          )}
          <button
            type="button"
            disabled={page >= pageCount}
            onClick={() => onPageChange(page + 1)}
            className="rounded-lg border border-border-subtle px-3 py-1 font-semibold text-text-main disabled:opacity-40"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
};

export default FrameworkTablePagination;
