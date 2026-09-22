import { useEffect, useRef, useState, type ReactNode } from 'react';
import {
  ArrowDownUp,
  Check,
  ChevronDown,
  ChevronUp,
  MoreVertical,
  Pin,
  PinOff,
  RefreshCw,
  RotateCcw,
} from 'lucide-react';
import type { Column, Table } from '@tanstack/react-table';
import type { DataTableColumnMeta } from './types';

function columnLabel<TData>(column: Column<TData, unknown>): string {
  const def = column.columnDef;
  if (typeof def.header === 'string') return def.header;
  const meta = def.meta as DataTableColumnMeta | undefined;
  return column.id;
}

interface DataTableOverflowMenuProps<TData> {
  table: Table<TData>;
  onRefresh?: () => void;
  refreshing?: boolean;
  onResetView: () => void;
  /** Extra sections inside the menu */
  children?: ReactNode;
}

export function DataTableOverflowMenu<TData>({
  table,
  onRefresh,
  refreshing = false,
  onResetView,
  children,
}: DataTableOverflowMenuProps<TData>) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const hideable = table
    .getAllLeafColumns()
    .filter(col => {
      const meta = col.columnDef.meta as DataTableColumnMeta | undefined;
      if (meta?.hideFromVisibilityMenu) return false;
      return col.getCanHide();
    });

  const moveColumn = (columnId: string, direction: -1 | 1) => {
    const order = table.getState().columnOrder.length
      ? [...table.getState().columnOrder]
      : table.getAllLeafColumns().map(c => c.id);
    const index = order.indexOf(columnId);
    if (index < 0) return;
    const nextIndex = index + direction;
    if (nextIndex < 0 || nextIndex >= order.length) return;
    const next = [...order];
    const [item] = next.splice(index, 1);
    next.splice(nextIndex, 0, item);
    table.setColumnOrder(next);
  };

  const pinSide = (columnId: string, side: 'left' | 'right' | false) => {
    const pinning = table.getState().columnPinning;
    const left = (pinning.left ?? []).filter(id => id !== columnId);
    const right = (pinning.right ?? []).filter(id => id !== columnId);
    if (side === 'left') left.push(columnId);
    if (side === 'right') right.push(columnId);
    table.setColumnPinning({ left, right });
  };

  return (
    <div className="relative shrink-0" ref={rootRef}>
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-border-subtle bg-surface-bg text-text-muted transition-colors hover:border-accent/40 hover:text-text-main"
        aria-label="Table options"
        aria-expanded={open}
        aria-haspopup="menu"
        title="Table options"
      >
        <MoreVertical size={16} />
      </button>

      {open ? (
        <div
          role="menu"
          className="absolute right-0 z-40 mt-2 w-[min(100vw-2rem,20rem)] max-h-[min(70vh,28rem)] overflow-y-auto rounded-xl border border-border-subtle bg-card p-3 shadow-lg"
        >
          <div className="mb-3 space-y-1">
            {onRefresh ? (
              <button
                type="button"
                role="menuitem"
                disabled={refreshing}
                onClick={() => {
                  onRefresh();
                  setOpen(false);
                }}
                className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm text-text-main hover:bg-surface-bg disabled:opacity-50"
              >
                <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
                Refresh data
              </button>
            ) : null}
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                onResetView();
                setOpen(false);
              }}
              className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm text-text-main hover:bg-surface-bg"
            >
              <RotateCcw size={14} />
              Reset view defaults
            </button>
          </div>

          <div className="mb-3 border-t border-border-subtle pt-3">
            <p className="mb-2 px-1 text-[11px] font-bold uppercase tracking-wider text-text-muted">
              Column visibility
            </p>
            <div className="space-y-1">
              {hideable.map(column => {
                const meta = column.columnDef.meta as DataTableColumnMeta | undefined;
                const locked = Boolean(meta?.required);
                return (
                  <label
                    key={column.id}
                    className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-sm text-text-main hover:bg-surface-bg"
                  >
                    <input
                      type="checkbox"
                      className="rounded border-border-subtle"
                      checked={column.getIsVisible()}
                      disabled={locked}
                      onChange={column.getToggleVisibilityHandler()}
                    />
                    <span className="min-w-0 flex-1 truncate">{columnLabel(column)}</span>
                    {locked ? <Check size={12} className="shrink-0 text-text-muted" /> : null}
                  </label>
                );
              })}
            </div>
          </div>

          <div className="mb-3 border-t border-border-subtle pt-3">
            <p className="mb-2 px-1 text-[11px] font-bold uppercase tracking-wider text-text-muted">
              Pin & reorder
            </p>
            <div className="space-y-1">
              {table.getAllLeafColumns().map(column => {
                const meta = column.columnDef.meta as DataTableColumnMeta | undefined;
                if (meta?.hideFromVisibilityMenu) return null;
                if (!column.getIsVisible()) return null;
                const isLeft = column.getIsPinned() === 'left';
                const isRight = column.getIsPinned() === 'right';
                return (
                  <div
                    key={`pin-${column.id}`}
                    className="flex items-center gap-1 rounded-lg px-1 py-1 text-sm text-text-main"
                  >
                    <span className="min-w-0 flex-1 truncate px-1">{columnLabel(column)}</span>
                    <button
                      type="button"
                      title="Move up"
                      className="rounded p-1 text-text-muted hover:bg-surface-bg hover:text-text-main"
                      onClick={() => moveColumn(column.id, -1)}
                    >
                      <ChevronUp size={14} />
                    </button>
                    <button
                      type="button"
                      title="Move down"
                      className="rounded p-1 text-text-muted hover:bg-surface-bg hover:text-text-main"
                      onClick={() => moveColumn(column.id, 1)}
                    >
                      <ChevronDown size={14} />
                    </button>
                    <button
                      type="button"
                      title={isLeft ? 'Unpin' : 'Pin left'}
                      className={`rounded p-1 hover:bg-surface-bg ${isLeft ? 'text-accent' : 'text-text-muted hover:text-text-main'}`}
                      onClick={() => pinSide(column.id, isLeft ? false : 'left')}
                    >
                      {isLeft ? <PinOff size={14} /> : <Pin size={14} />}
                    </button>
                    <button
                      type="button"
                      title={isRight ? 'Unpin' : 'Pin right'}
                      className={`rounded p-1 hover:bg-surface-bg ${isRight ? 'text-accent' : 'text-text-muted hover:text-text-main'}`}
                      onClick={() => pinSide(column.id, isRight ? false : 'right')}
                    >
                      <ArrowDownUp size={14} className={isRight ? 'rotate-90' : 'rotate-90 opacity-60'} />
                    </button>
                  </div>
                );
              })}
            </div>
          </div>

          {children}
        </div>
      ) : null}
    </div>
  );
}

/** Standalone overflow for pages that keep a custom <table> but share the menu UX. */
export interface StandaloneTableOverflowProps {
  columns: Array<{
    id: string;
    label: string;
    visible: boolean;
    required?: boolean;
    pinned?: 'left' | 'right' | false;
  }>;
  onToggleVisibility: (id: string) => void;
  onMoveColumn: (id: string, direction: -1 | 1) => void;
  onPinColumn: (id: string, side: 'left' | 'right' | false) => void;
  onRefresh?: () => void;
  refreshing?: boolean;
  onResetView: () => void;
  className?: string;
}

export function StandaloneTableOverflowMenu({
  columns,
  onToggleVisibility,
  onMoveColumn,
  onPinColumn,
  onRefresh,
  refreshing = false,
  onResetView,
  className = '',
}: StandaloneTableOverflowProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div className={`relative shrink-0 ${className}`.trim()} ref={rootRef}>
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-border-subtle bg-surface-bg text-text-muted transition-colors hover:border-accent/40 hover:text-text-main"
        aria-label="Table options"
        aria-expanded={open}
        aria-haspopup="menu"
        title="Table options"
      >
        <MoreVertical size={16} />
      </button>

      {open ? (
        <div
          role="menu"
          className="absolute right-0 z-40 mt-2 w-[min(100vw-2rem,20rem)] max-h-[min(70vh,28rem)] overflow-y-auto rounded-xl border border-border-subtle bg-card p-3 shadow-lg"
        >
          <div className="mb-3 space-y-1">
            {onRefresh ? (
              <button
                type="button"
                role="menuitem"
                disabled={refreshing}
                onClick={() => {
                  onRefresh();
                  setOpen(false);
                }}
                className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm text-text-main hover:bg-surface-bg disabled:opacity-50"
              >
                <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
                Refresh data
              </button>
            ) : null}
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                onResetView();
                setOpen(false);
              }}
              className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm text-text-main hover:bg-surface-bg"
            >
              <RotateCcw size={14} />
              Reset view defaults
            </button>
          </div>

          <div className="mb-3 border-t border-border-subtle pt-3">
            <p className="mb-2 px-1 text-[11px] font-bold uppercase tracking-wider text-text-muted">
              Column visibility
            </p>
            <div className="space-y-1">
              {columns.map(column => (
                <label
                  key={column.id}
                  className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-sm text-text-main hover:bg-surface-bg"
                >
                  <input
                    type="checkbox"
                    className="rounded border-border-subtle"
                    checked={column.visible}
                    disabled={column.required}
                    onChange={() => onToggleVisibility(column.id)}
                  />
                  <span className="min-w-0 flex-1 truncate">{column.label}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="border-t border-border-subtle pt-3">
            <p className="mb-2 px-1 text-[11px] font-bold uppercase tracking-wider text-text-muted">
              Pin & reorder
            </p>
            <div className="space-y-1">
              {columns
                .filter(c => c.visible)
                .map(column => (
                  <div
                    key={`pin-${column.id}`}
                    className="flex items-center gap-1 rounded-lg px-1 py-1 text-sm text-text-main"
                  >
                    <span className="min-w-0 flex-1 truncate px-1">{column.label}</span>
                    <button
                      type="button"
                      title="Move up"
                      className="rounded p-1 text-text-muted hover:bg-surface-bg hover:text-text-main"
                      onClick={() => onMoveColumn(column.id, -1)}
                    >
                      <ChevronUp size={14} />
                    </button>
                    <button
                      type="button"
                      title="Move down"
                      className="rounded p-1 text-text-muted hover:bg-surface-bg hover:text-text-main"
                      onClick={() => onMoveColumn(column.id, 1)}
                    >
                      <ChevronDown size={14} />
                    </button>
                    <button
                      type="button"
                      title={column.pinned === 'left' ? 'Unpin' : 'Pin left'}
                      className={`rounded p-1 hover:bg-surface-bg ${column.pinned === 'left' ? 'text-accent' : 'text-text-muted'}`}
                      onClick={() =>
                        onPinColumn(column.id, column.pinned === 'left' ? false : 'left')
                      }
                    >
                      {column.pinned === 'left' ? <PinOff size={14} /> : <Pin size={14} />}
                    </button>
                    <button
                      type="button"
                      title={column.pinned === 'right' ? 'Unpin' : 'Pin right'}
                      className={`rounded p-1 hover:bg-surface-bg ${column.pinned === 'right' ? 'text-accent' : 'text-text-muted'}`}
                      onClick={() =>
                        onPinColumn(column.id, column.pinned === 'right' ? false : 'right')
                      }
                    >
                      <ArrowDownUp size={14} className="rotate-90 opacity-70" />
                    </button>
                  </div>
                ))}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
