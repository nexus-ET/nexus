import { useMemo } from 'react';
import type { SortingState } from '@tanstack/react-table';
import DataTable from '../ui/DataTable/DataTable';
import type { DataTableColumnDef } from '../ui/DataTable/types';

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
  onRefresh?: () => void;
  refreshing?: boolean;
  enableRowSelection?: boolean;
  persistenceKey?: string;
  enableColumnFilters?: boolean;
  showSearch?: boolean;
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
  onRefresh,
  refreshing,
  enableRowSelection = false,
  persistenceKey,
  enableColumnFilters = true,
  showSearch = true,
}: ReportTableProps<T>) {
  const tableColumns = useMemo<DataTableColumnDef<T>[]>(
    () =>
      columns.map(column => ({
        id: column.id,
        accessorFn: row => {
          try {
            const rendered = column.pdfValue?.(row);
            if (rendered != null) return rendered;
          } catch {
            /* ignore */
          }
          return '';
        },
        header: column.header,
        enableSorting: column.sortable !== false && Boolean(onSort),
        meta: {
          headerClassName: column.headerClassName,
          cellClassName: column.cellClassName,
        },
        cell: ({ row }) => column.render(row.original),
      })),
    [columns, onSort]
  );

  const sorting = useMemo<SortingState>(() => {
    if (!sortBy) return [];
    return [{ id: sortBy, desc: sortOrder === 'desc' }];
  }, [sortBy, sortOrder]);

  return (
    <DataTable
      title={title}
      columns={tableColumns}
      data={rows}
      getRowId={row => String(getRowKey(row))}
      loading={loading}
      emptyMessage={emptyMessage}
      getRowClassName={getRowClassName}
      showSearch={showSearch}
      enableColumnFilters={enableColumnFilters}
      enableRowSelection={enableRowSelection}
      manualSorting
      sorting={sorting}
      onSortingChange={next => {
        const first = next[0];
        if (first) onSort?.(first.id);
        else if (sortBy) onSort?.(sortBy);
      }}
      onRefresh={onRefresh}
      refreshing={refreshing}
      persistenceKey={persistenceKey}
      enableColumnResizing
    />
  );
}

export default ReportTable;
