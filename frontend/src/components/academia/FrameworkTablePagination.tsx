interface FrameworkTablePaginationProps {
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  pageSizeOptions: readonly number[];
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
}

const FrameworkTablePagination: React.FC<FrameworkTablePaginationProps> = ({
  page,
  pageSize,
  total,
  totalPages,
  pageSizeOptions,
  onPageChange,
  onPageSizeChange,
}) => {
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border-subtle px-6 py-4 text-sm">
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
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => onPageChange(Math.max(1, page - 1))}
            className="rounded-lg border border-border-subtle px-3 py-1 font-semibold text-text-main disabled:opacity-40"
          >
            Previous
          </button>
          <span className="text-text-muted">
            Page {page} of {Math.max(totalPages, 1)}
          </span>
          <button
            type="button"
            disabled={page >= totalPages}
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
