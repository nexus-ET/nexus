import React from 'react';
import { ArrowDown, ArrowUp, ArrowUpDown, Loader2 } from 'lucide-react';

export interface ReportColumn<T> {
  id: string;
  header: string;
  render: (row: T) => React.ReactNode;
  pdfValue?: (row: T) => string;
  headerClassName?: string;
  cellClassName?: string;
  sortable?: boolean;
}

interface ReportTableProps<T> {
  title?: string;
  columns: ReportColumn<T>[];
  rows: T[];
  loading?: boolean;
  emptyMessage?: string;
  getRowKey: (row: T) => string | number;
  getRowClassName?: (row: T) => string;
  sortBy?: string;
  sortOrder?: 'asc' | 'desc';
  onSort?: (columnId: string) => void;
}

function SortIndicator({
  columnId,
  sortBy,
  sortOrder,
}: {
  columnId: string;
  sortBy?: string;
  sortOrder?: 'asc' | 'desc';
}) {
  if (sortBy !== columnId) {
    return <ArrowUpDown size={12} className="opacity-40" />;
  }
  return sortOrder === 'asc' ? <ArrowUp size={12} /> : <ArrowDown size={12} />;
}

function ReportTable<T>({
  title,
  columns,
  rows,
  loading = false,
  emptyMessage = 'No records found for the selected filters.',
  getRowKey,
  getRowClassName,
  sortBy,
  sortOrder,
  onSort,
}: ReportTableProps<T>) {
  return (
    <div className="rounded-2xl border border-border-subtle bg-card overflow-hidden">
      {title ? (
        <div className="border-b border-border-subtle bg-surface-bg px-4 py-3 md:px-5">
          <h2 className="text-base font-semibold text-text-main">{title}</h2>
        </div>
      ) : null}

      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-border-subtle">
          <thead className="bg-surface-bg">
            <tr>
              {columns.map(column => {
                const isSortable = column.sortable !== false && Boolean(onSort);
                const headerContent = (
                  <span className="inline-flex items-center gap-1.5">
                    {column.header}
                    {isSortable ? (
                      <SortIndicator columnId={column.id} sortBy={sortBy} sortOrder={sortOrder} />
                    ) : null}
                  </span>
                );

                return (
                  <th
                    key={column.id}
                    scope="col"
                    className={`px-4 py-3 text-left text-[11px] font-bold uppercase tracking-wider text-text-muted ${column.headerClassName ?? ''}`}
                  >
                    {isSortable ? (
                      <button
                        type="button"
                        onClick={() => onSort?.(column.id)}
                        className="inline-flex items-center gap-1.5 hover:text-text-main transition-colors"
                      >
                        {headerContent}
                      </button>
                    ) : (
                      headerContent
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody className="divide-y divide-border-subtle bg-card">
            {loading ? (
              <tr>
                <td colSpan={columns.length} className="px-4 py-10 text-center text-sm text-text-muted">
                  <Loader2 size={18} className="inline animate-spin mr-2" />
                  Loading report...
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="px-4 py-10 text-center text-sm text-text-muted">
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              rows.map(row => (
                <tr
                  key={getRowKey(row)}
                  className={`hover:bg-surface-bg/40 transition-colors ${getRowClassName?.(row) ?? ''}`}
                >
                  {columns.map(column => (
                    <td
                      key={column.id}
                      className={`px-4 py-3 text-sm text-text-main align-top ${column.cellClassName ?? ''}`}
                    >
                      {column.render(row)}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default ReportTable;
