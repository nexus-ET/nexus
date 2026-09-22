import { useMemo, useState, type CSSProperties } from 'react';
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnFiltersState,
  type SortingState,
  type Updater,
} from '@tanstack/react-table';
import { ArrowDown, ArrowUp, ArrowUpDown, Loader2, Search } from 'lucide-react';
import { DataTableOverflowMenu } from './DataTableOverflowMenu';
import type { DataTableColumnMeta, DataTableProps } from './types';
import { useDataTableViewState } from './useDataTableViewState';

function resolveUpdater<T>(updater: Updater<T>, current: T): T {
  return typeof updater === 'function' ? (updater as (old: T) => T)(current) : updater;
}

function SortGlyph({ sorted }: { sorted: false | 'asc' | 'desc' }) {
  if (sorted === 'asc') return <ArrowUp size={12} />;
  if (sorted === 'desc') return <ArrowDown size={12} />;
  return <ArrowUpDown size={12} className="opacity-40" />;
}

function pinStyle(
  pinned: false | 'left' | 'right',
  start: number | undefined
): CSSProperties | undefined {
  if (!pinned) return undefined;
  return {
    position: 'sticky',
    [pinned]: start ?? 0,
    zIndex: 2,
    background: 'var(--color-card, #fff)',
  };
}

function DataTable<TData>({
  columns,
  data,
  getRowId,
  title,
  loading = false,
  emptyMessage = 'No records found.',
  className = '',
  tableClassName = '',
  persistenceKey,
  globalFilter: controlledFilter,
  onGlobalFilterChange,
  globalFilterPlaceholder = 'Search…',
  showSearch = true,
  manualSorting = false,
  sorting: controlledSorting,
  onSortingChange,
  enableRowSelection = false,
  rowSelection: controlledSelection,
  onRowSelectionChange,
  enableColumnFilters = false,
  enableColumnResizing = true,
  showToolbar = true,
  toolbarExtra,
  toolbarPrimary,
  onRefresh,
  refreshing = false,
  getRowClassName,
  defaultColumnVisibility,
  defaultColumnOrder,
  defaultColumnPinning,
}: DataTableProps<TData>) {
  const {
    view,
    setColumnVisibility,
    setColumnOrder,
    setColumnPinning,
    setColumnSizing,
    resetView,
  } = useDataTableViewState(persistenceKey, {
    columnVisibility: defaultColumnVisibility,
    columnOrder: defaultColumnOrder,
    columnPinning: defaultColumnPinning,
  });

  const [internalSorting, setInternalSorting] = useState<SortingState>([]);
  const [internalFilter, setInternalFilter] = useState('');
  const [internalSelection, setInternalSelection] = useState({});
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);

  const sorting = controlledSorting ?? internalSorting;
  const globalFilter = controlledFilter ?? internalFilter;
  const rowSelection = controlledSelection ?? internalSelection;

  const selectionColumn = useMemo(() => {
    if (!enableRowSelection) return [] as typeof columns;
    return [
      {
        id: '__select',
        size: 40,
        enableSorting: false,
        enableHiding: false,
        enableResizing: false,
        meta: { hideFromVisibilityMenu: true, required: true } satisfies DataTableColumnMeta,
        header: ({ table }) => (
          <input
            type="checkbox"
            aria-label="Select all rows"
            checked={table.getIsAllPageRowsSelected()}
            ref={el => {
              if (el) el.indeterminate = table.getIsSomePageRowsSelected();
            }}
            onChange={table.getToggleAllPageRowsSelectedHandler()}
          />
        ),
        cell: ({ row }) => (
          <input
            type="checkbox"
            aria-label="Select row"
            checked={row.getIsSelected()}
            disabled={!row.getCanSelect()}
            onChange={row.getToggleSelectedHandler()}
          />
        ),
      },
    ] as typeof columns;
  }, [enableRowSelection]);

  const allColumns = useMemo(() => [...selectionColumn, ...columns], [selectionColumn, columns]);

  const table = useReactTable({
    data,
    columns: allColumns,
    getRowId: row => String(getRowId(row)),
    state: {
      sorting,
      globalFilter,
      rowSelection,
      columnVisibility: view.columnVisibility,
      columnOrder: view.columnOrder,
      columnPinning: view.columnPinning,
      columnSizing: view.columnSizing,
      columnFilters,
    },
    onSortingChange: updater => {
      const next = resolveUpdater(updater, sorting);
      if (onSortingChange) onSortingChange(next);
      else setInternalSorting(next);
    },
    onGlobalFilterChange: updater => {
      const next = resolveUpdater(updater, globalFilter);
      if (onGlobalFilterChange) onGlobalFilterChange(next);
      else setInternalFilter(next);
    },
    onRowSelectionChange: updater => {
      const next = resolveUpdater(updater, rowSelection);
      if (onRowSelectionChange) onRowSelectionChange(next);
      else setInternalSelection(next);
    },
    onColumnVisibilityChange: updater => setColumnVisibility(resolveUpdater(updater, view.columnVisibility)),
    onColumnOrderChange: updater => setColumnOrder(resolveUpdater(updater, view.columnOrder)),
    onColumnPinningChange: updater => setColumnPinning(resolveUpdater(updater, view.columnPinning)),
    onColumnSizingChange: updater => setColumnSizing(resolveUpdater(updater, view.columnSizing)),
    onColumnFiltersChange: setColumnFilters,
    enableRowSelection,
    enableColumnResizing,
    columnResizeMode: 'onChange',
    manualSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: manualSorting ? undefined : getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    defaultColumn: {
      minSize: 64,
      size: 160,
      maxSize: 640,
      enableSorting: true,
    },
  });

  const leafCount = table.getVisibleLeafColumns().length;

  return (
    <div
      className={`overflow-hidden rounded-2xl border border-border-subtle bg-card ${className}`.trim()}
    >
      {title || showToolbar ? (
        <div className="flex flex-wrap items-center gap-3 border-b border-border-subtle bg-surface-bg px-4 py-3 md:px-5">
          {title ? (
            <div className="min-w-0 flex-1">
              {typeof title === 'string' ? (
                <h2 className="text-base font-semibold text-text-main">{title}</h2>
              ) : (
                title
              )}
            </div>
          ) : (
            <div className="min-w-0 flex-1" />
          )}

          {showToolbar ? (
            <div className="ml-auto flex flex-wrap items-center gap-2">
              {showSearch ? (
                <div className="flex min-w-[12rem] items-center gap-2 rounded-xl border border-border-subtle bg-card px-3 py-2 text-sm">
                  <Search size={14} className="shrink-0 text-text-muted" />
                  <input
                    type="search"
                    value={globalFilter}
                    onChange={e => table.setGlobalFilter(e.target.value)}
                    placeholder={globalFilterPlaceholder}
                    aria-label="Search table"
                    className="w-full min-w-0 border-0 bg-transparent outline-none placeholder:text-text-muted"
                  />
                </div>
              ) : null}
              {toolbarExtra}
              {toolbarPrimary}
              <DataTableOverflowMenu
                table={table}
                onRefresh={onRefresh}
                refreshing={refreshing}
                onResetView={resetView}
              />
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="overflow-x-auto">
        <table
          className={`min-w-full divide-y divide-border-subtle ${tableClassName}`.trim()}
          style={{ width: table.getCenterTotalSize() }}
        >
          <thead className="bg-surface-bg">
            {table.getHeaderGroups().map(headerGroup => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map(header => {
                  const meta = header.column.columnDef.meta as DataTableColumnMeta | undefined;
                  const canSort = header.column.getCanSort();
                  const pinned = header.column.getIsPinned();
                  return (
                    <th
                      key={header.id}
                      scope="col"
                      colSpan={header.colSpan}
                      style={{
                        width: header.getSize(),
                        ...pinStyle(pinned, header.column.getStart(pinned || 'left')),
                      }}
                      className={`relative px-3 py-3 text-left text-[11px] font-bold uppercase tracking-wider text-text-muted ${meta?.headerClassName ?? ''}`.trim()}
                    >
                      {header.isPlaceholder ? null : (
                        <div className="flex flex-col gap-1">
                          <button
                            type="button"
                            disabled={!canSort}
                            onClick={header.column.getToggleSortingHandler()}
                            className={`inline-flex items-center gap-1.5 ${canSort ? 'hover:text-text-main' : 'cursor-default'}`}
                          >
                            {flexRender(header.column.columnDef.header, header.getContext())}
                            {canSort ? <SortGlyph sorted={header.column.getIsSorted()} /> : null}
                          </button>
                          {enableColumnFilters && header.column.getCanFilter() ? (
                            <input
                              type="search"
                              value={(header.column.getFilterValue() as string) ?? ''}
                              onChange={e => header.column.setFilterValue(e.target.value)}
                              placeholder={meta?.filterPlaceholder ?? 'Filter…'}
                              className="w-full rounded-md border border-border-subtle bg-card px-2 py-1 text-[11px] font-normal normal-case tracking-normal text-text-main outline-none focus:border-accent"
                              onClick={e => e.stopPropagation()}
                            />
                          ) : null}
                        </div>
                      )}
                      {enableColumnResizing && header.column.getCanResize() ? (
                        <div
                          onMouseDown={header.getResizeHandler()}
                          onTouchStart={header.getResizeHandler()}
                          className={`absolute right-0 top-0 h-full w-1 cursor-col-resize touch-none select-none bg-transparent hover:bg-accent/40 ${header.column.getIsResizing() ? 'bg-accent' : ''}`}
                        />
                      ) : null}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody className="divide-y divide-border-subtle bg-card">
            {loading ? (
              <tr>
                <td colSpan={Math.max(leafCount, 1)} className="px-4 py-10 text-center text-sm text-text-muted">
                  <Loader2 size={18} className="mr-2 inline animate-spin" />
                  Loading…
                </td>
              </tr>
            ) : table.getRowModel().rows.length === 0 ? (
              <tr>
                <td colSpan={Math.max(leafCount, 1)} className="px-4 py-10 text-center text-sm text-text-muted">
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              table.getRowModel().rows.map(row => (
                <tr
                  key={row.id}
                  className={`hover:bg-surface-bg/40 transition-colors ${getRowClassName?.(row.original) ?? ''}`.trim()}
                >
                  {row.getVisibleCells().map(cell => {
                    const meta = cell.column.columnDef.meta as DataTableColumnMeta | undefined;
                    const pinned = cell.column.getIsPinned();
                    return (
                      <td
                        key={cell.id}
                        style={{
                          width: cell.column.getSize(),
                          ...pinStyle(pinned, cell.column.getStart(pinned || 'left')),
                        }}
                        className={`px-3 py-3 text-sm text-text-main align-top ${meta?.cellClassName ?? ''}`.trim()}
                      >
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    );
                  })}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default DataTable;
