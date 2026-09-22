import type { ReactNode } from 'react';
import type {
  ColumnDef,
  ColumnOrderState,
  ColumnPinningState,
  ColumnSizingState,
  RowSelectionState,
  SortingState,
  VisibilityState,
} from '@tanstack/react-table';

export type DataTableSortDirection = 'asc' | 'desc';

export interface DataTableColumnMeta {
  /** Column filter placeholder */
  filterPlaceholder?: string;
  /** Lock visibility toggle (always shown) */
  required?: boolean;
  /** Hide from overflow visibility list */
  hideFromVisibilityMenu?: boolean;
  headerClassName?: string;
  cellClassName?: string;
  /** Default pin side when resetting */
  defaultPin?: 'left' | 'right';
}

export type DataTableColumnDef<TData> = ColumnDef<TData, unknown> & {
  meta?: DataTableColumnMeta;
};

export interface DataTableViewState {
  columnVisibility: VisibilityState;
  columnOrder: ColumnOrderState;
  columnPinning: ColumnPinningState;
  columnSizing: ColumnSizingState;
}

export interface DataTableProps<TData> {
  columns: DataTableColumnDef<TData>[];
  data: TData[];
  getRowId: (row: TData) => string;
  title?: ReactNode;
  loading?: boolean;
  emptyMessage?: string;
  className?: string;
  tableClassName?: string;
  /** Persist view prefs (visibility / order / pin / sizing) */
  persistenceKey?: string;
  /** Controlled global search */
  globalFilter?: string;
  onGlobalFilterChange?: (value: string) => void;
  globalFilterPlaceholder?: string;
  /** Hide built-in search (when page already has search) */
  showSearch?: boolean;
  /** Manual (server) sorting */
  manualSorting?: boolean;
  sorting?: SortingState;
  onSortingChange?: (sorting: SortingState) => void;
  /** Row selection */
  enableRowSelection?: boolean;
  rowSelection?: RowSelectionState;
  onRowSelectionChange?: (selection: RowSelectionState) => void;
  /** Column filters under headers */
  enableColumnFilters?: boolean;
  /** Drag resize */
  enableColumnResizing?: boolean;
  /** Show toolbar (search + overflow) */
  showToolbar?: boolean;
  /** Extra controls between search and overflow */
  toolbarExtra?: ReactNode;
  /** Primary compact actions left of overflow */
  toolbarPrimary?: ReactNode;
  onRefresh?: () => void;
  refreshing?: boolean;
  getRowClassName?: (row: TData) => string;
  /** Initial / reset defaults */
  defaultColumnVisibility?: VisibilityState;
  defaultColumnOrder?: ColumnOrderState;
  defaultColumnPinning?: ColumnPinningState;
}
