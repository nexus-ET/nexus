import { useCallback, useEffect, useState } from 'react';
import type {
  ColumnOrderState,
  ColumnPinningState,
  ColumnSizingState,
  VisibilityState,
} from '@tanstack/react-table';
import type { DataTableViewState } from './types';

const EMPTY_VIEW: DataTableViewState = {
  columnVisibility: {},
  columnOrder: [],
  columnPinning: {},
  columnSizing: {},
};

function readJson<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export function loadDataTableViewState(
  persistenceKey: string | undefined,
  defaults?: Partial<DataTableViewState>
): DataTableViewState {
  const base: DataTableViewState = {
    columnVisibility: defaults?.columnVisibility ?? {},
    columnOrder: defaults?.columnOrder ?? [],
    columnPinning: defaults?.columnPinning ?? {},
    columnSizing: defaults?.columnSizing ?? {},
  };
  if (!persistenceKey) return base;
  const saved = readJson<Partial<DataTableViewState>>(`nexus.datatable.view.${persistenceKey}`);
  if (!saved) return base;
  return {
    columnVisibility: saved.columnVisibility ?? base.columnVisibility,
    columnOrder: Array.isArray(saved.columnOrder) ? saved.columnOrder : base.columnOrder,
    columnPinning: saved.columnPinning ?? base.columnPinning,
    columnSizing: saved.columnSizing ?? base.columnSizing,
  };
}

export function persistDataTableViewState(persistenceKey: string | undefined, state: DataTableViewState) {
  if (!persistenceKey) return;
  try {
    localStorage.setItem(`nexus.datatable.view.${persistenceKey}`, JSON.stringify(state));
  } catch {
    /* ignore quota */
  }
}

export function useDataTableViewState(
  persistenceKey: string | undefined,
  defaults?: Partial<DataTableViewState>
) {
  const [view, setView] = useState<DataTableViewState>(() =>
    loadDataTableViewState(persistenceKey, defaults)
  );

  useEffect(() => {
    persistDataTableViewState(persistenceKey, view);
  }, [persistenceKey, view]);

  const setColumnVisibility = useCallback((next: VisibilityState | ((prev: VisibilityState) => VisibilityState)) => {
    setView(prev => ({
      ...prev,
      columnVisibility: typeof next === 'function' ? next(prev.columnVisibility) : next,
    }));
  }, []);

  const setColumnOrder = useCallback((next: ColumnOrderState | ((prev: ColumnOrderState) => ColumnOrderState)) => {
    setView(prev => ({
      ...prev,
      columnOrder: typeof next === 'function' ? next(prev.columnOrder) : next,
    }));
  }, []);

  const setColumnPinning = useCallback(
    (next: ColumnPinningState | ((prev: ColumnPinningState) => ColumnPinningState)) => {
      setView(prev => ({
        ...prev,
        columnPinning: typeof next === 'function' ? next(prev.columnPinning) : next,
      }));
    },
    []
  );

  const setColumnSizing = useCallback(
    (next: ColumnSizingState | ((prev: ColumnSizingState) => ColumnSizingState)) => {
      setView(prev => ({
        ...prev,
        columnSizing: typeof next === 'function' ? next(prev.columnSizing) : next,
      }));
    },
    []
  );

  const resetView = useCallback(() => {
    setView({
      columnVisibility: defaults?.columnVisibility ?? EMPTY_VIEW.columnVisibility,
      columnOrder: defaults?.columnOrder ?? EMPTY_VIEW.columnOrder,
      columnPinning: defaults?.columnPinning ?? EMPTY_VIEW.columnPinning,
      columnSizing: EMPTY_VIEW.columnSizing,
    });
  }, [defaults]);

  return {
    view,
    setColumnVisibility,
    setColumnOrder,
    setColumnPinning,
    setColumnSizing,
    resetView,
  };
}
