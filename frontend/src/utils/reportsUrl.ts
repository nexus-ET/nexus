export const SYNC_LOGS_LIMITS = [25, 50, 100] as const;
export type SyncLogsLimit = (typeof SYNC_LOGS_LIMITS)[number];

export const SYNC_LOGS_SORT_FIELDS = [
  'attempt_timestamp',
  'sync_mode',
  'source',
  'triggered_by_user',
  'status',
  'results_count',
  'leads_created',
  'leads_seen',
  'message',
] as const;

export type SyncLogsSortField = (typeof SYNC_LOGS_SORT_FIELDS)[number];
export type SortOrder = 'asc' | 'desc';

export type SyncLogsQueryState = {
  page: number;
  limit: SyncLogsLimit;
  startDate: string;
  endDate: string;
  sortBy: SyncLogsSortField;
  sortOrder: SortOrder;
};

const DEFAULT_STATE: SyncLogsQueryState = {
  page: 1,
  limit: 25,
  startDate: '',
  endDate: '',
  sortBy: 'attempt_timestamp',
  sortOrder: 'desc',
};

const SYNC_LOGS_LIMIT_STORAGE_KEY = 'nexus.reports.syncLogs.limit';

function readStoredSyncLogsLimit(): SyncLogsLimit | null {
  if (typeof window === 'undefined') return null;
  try {
    const parsed = Number(window.localStorage.getItem(SYNC_LOGS_LIMIT_STORAGE_KEY));
    if (parsed === 25 || parsed === 50 || parsed === 100) return parsed;
  } catch {
    // Ignore private mode / blocked storage.
  }
  return null;
}

function storeSyncLogsLimit(limit: SyncLogsLimit): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(SYNC_LOGS_LIMIT_STORAGE_KEY, String(limit));
  } catch {
    // Ignore private mode / blocked storage.
  }
}

function parseLimit(value: string | null): SyncLogsLimit {
  if (value !== null && value !== '') {
    const parsed = Number(value);
    if (parsed === 50 || parsed === 100) return parsed;
    return 25;
  }
  return readStoredSyncLogsLimit() ?? DEFAULT_STATE.limit;
}

function parsePage(value: string | null): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 1) return 1;
  return Math.floor(parsed);
}

function parseSortBy(value: string | null): SyncLogsSortField {
  if (value && (SYNC_LOGS_SORT_FIELDS as readonly string[]).includes(value)) {
    return value as SyncLogsSortField;
  }
  return DEFAULT_STATE.sortBy;
}

function parseSortOrder(value: string | null): SortOrder {
  return value === 'asc' ? 'asc' : 'desc';
}

export function readSyncLogsQuery(params: URLSearchParams): SyncLogsQueryState {
  const limitParam = params.get('limit');
  const limit = parseLimit(limitParam);
  if (limitParam !== null && limitParam !== '') {
    storeSyncLogsLimit(limit);
  }

  return {
    page: parsePage(params.get('page')),
    limit,
    startDate: params.get('start_date') || '',
    endDate: params.get('end_date') || '',
    sortBy: parseSortBy(params.get('sort_by')),
    sortOrder: parseSortOrder(params.get('sort_order')),
  };
}

export function writeSyncLogsQuery(
  current: URLSearchParams,
  patch: Partial<SyncLogsQueryState>
): URLSearchParams {
  const next = new URLSearchParams(current);
  const merged: SyncLogsQueryState = { ...readSyncLogsQuery(current), ...patch };

  storeSyncLogsLimit(merged.limit);

  if (merged.page > 1) next.set('page', String(merged.page));
  else next.delete('page');

  if (merged.limit !== DEFAULT_STATE.limit) next.set('limit', String(merged.limit));
  else next.delete('limit');

  if (merged.startDate) next.set('start_date', merged.startDate);
  else next.delete('start_date');

  if (merged.endDate) next.set('end_date', merged.endDate);
  else next.delete('end_date');

  if (merged.sortBy !== DEFAULT_STATE.sortBy) next.set('sort_by', merged.sortBy);
  else next.delete('sort_by');

  if (merged.sortOrder !== DEFAULT_STATE.sortOrder) next.set('sort_order', merged.sortOrder);
  else next.delete('sort_order');

  return next;
}

export function buildSyncLogsApiQuery(state: SyncLogsQueryState): string {
  const params = new URLSearchParams();
  params.set('page', String(state.page));
  params.set('limit', String(state.limit));
  params.set('sort_by', state.sortBy);
  params.set('sort_order', state.sortOrder);
  if (state.startDate) params.set('start_date', state.startDate);
  if (state.endDate) params.set('end_date', state.endDate);
  return params.toString();
}

/** Filter/sort params only — used by full-dataset PDF export (no pagination). */
export function buildSyncLogsExportQuery(state: SyncLogsQueryState): string {
  const params = new URLSearchParams();
  params.set('sort_by', state.sortBy);
  params.set('sort_order', state.sortOrder);
  if (state.startDate) params.set('start_date', state.startDate);
  if (state.endDate) params.set('end_date', state.endDate);
  return params.toString();
}

export function totalPages(totalCount: number, limit: number): number {
  if (totalCount <= 0) return 1;
  return Math.max(1, Math.ceil(totalCount / limit));
}

/* ---- Exception Report (mirrors Sync Logs URL helpers) ---- */

export const EXCEPTION_LOGS_LIMITS = [25, 50, 100] as const;
export type ExceptionLogsLimit = (typeof EXCEPTION_LOGS_LIMITS)[number];

export const EXCEPTION_LOGS_SORT_FIELDS = [
  'attempt_timestamp',
  'severity',
  'source',
  'category',
  'triggered_by_user',
  'status',
  'message',
] as const;

export type ExceptionLogsSortField = (typeof EXCEPTION_LOGS_SORT_FIELDS)[number];

export type ExceptionLogsQueryState = {
  page: number;
  limit: ExceptionLogsLimit;
  startDate: string;
  endDate: string;
  sortBy: ExceptionLogsSortField;
  sortOrder: SortOrder;
};

const EXCEPTION_DEFAULT_STATE: ExceptionLogsQueryState = {
  page: 1,
  limit: 25,
  startDate: '',
  endDate: '',
  sortBy: 'attempt_timestamp',
  sortOrder: 'desc',
};

const EXCEPTION_LOGS_LIMIT_STORAGE_KEY = 'nexus.reports.exceptionLogs.limit';

function readStoredExceptionLogsLimit(): ExceptionLogsLimit | null {
  if (typeof window === 'undefined') return null;
  try {
    const parsed = Number(window.localStorage.getItem(EXCEPTION_LOGS_LIMIT_STORAGE_KEY));
    if (parsed === 25 || parsed === 50 || parsed === 100) return parsed;
  } catch {
    // Ignore private mode / blocked storage.
  }
  return null;
}

function storeExceptionLogsLimit(limit: ExceptionLogsLimit): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(EXCEPTION_LOGS_LIMIT_STORAGE_KEY, String(limit));
  } catch {
    // Ignore private mode / blocked storage.
  }
}

function parseExceptionLimit(value: string | null): ExceptionLogsLimit {
  if (value !== null && value !== '') {
    const parsed = Number(value);
    if (parsed === 50 || parsed === 100) return parsed;
    return 25;
  }
  return readStoredExceptionLogsLimit() ?? EXCEPTION_DEFAULT_STATE.limit;
}

function parseExceptionSortBy(value: string | null): ExceptionLogsSortField {
  if (value && (EXCEPTION_LOGS_SORT_FIELDS as readonly string[]).includes(value)) {
    return value as ExceptionLogsSortField;
  }
  return EXCEPTION_DEFAULT_STATE.sortBy;
}

export function readExceptionLogsQuery(params: URLSearchParams): ExceptionLogsQueryState {
  const limitParam = params.get('limit');
  const limit = parseExceptionLimit(limitParam);
  if (limitParam !== null && limitParam !== '') {
    storeExceptionLogsLimit(limit);
  }

  return {
    page: parsePage(params.get('page')),
    limit,
    startDate: params.get('start_date') || '',
    endDate: params.get('end_date') || '',
    sortBy: parseExceptionSortBy(params.get('sort_by')),
    sortOrder: parseSortOrder(params.get('sort_order')),
  };
}

export function writeExceptionLogsQuery(
  current: URLSearchParams,
  patch: Partial<ExceptionLogsQueryState>
): URLSearchParams {
  const next = new URLSearchParams(current);
  const merged: ExceptionLogsQueryState = { ...readExceptionLogsQuery(current), ...patch };

  storeExceptionLogsLimit(merged.limit);

  if (merged.page > 1) next.set('page', String(merged.page));
  else next.delete('page');

  if (merged.limit !== EXCEPTION_DEFAULT_STATE.limit) next.set('limit', String(merged.limit));
  else next.delete('limit');

  if (merged.startDate) next.set('start_date', merged.startDate);
  else next.delete('start_date');

  if (merged.endDate) next.set('end_date', merged.endDate);
  else next.delete('end_date');

  if (merged.sortBy !== EXCEPTION_DEFAULT_STATE.sortBy) next.set('sort_by', merged.sortBy);
  else next.delete('sort_by');

  if (merged.sortOrder !== EXCEPTION_DEFAULT_STATE.sortOrder) next.set('sort_order', merged.sortOrder);
  else next.delete('sort_order');

  return next;
}

export function buildExceptionLogsApiQuery(state: ExceptionLogsQueryState): string {
  const params = new URLSearchParams();
  params.set('page', String(state.page));
  params.set('limit', String(state.limit));
  params.set('sort_by', state.sortBy);
  params.set('sort_order', state.sortOrder);
  if (state.startDate) params.set('start_date', state.startDate);
  if (state.endDate) params.set('end_date', state.endDate);
  return params.toString();
}

export function buildExceptionLogsExportQuery(state: ExceptionLogsQueryState): string {
  const params = new URLSearchParams();
  params.set('sort_by', state.sortBy);
  params.set('sort_order', state.sortOrder);
  if (state.startDate) params.set('start_date', state.startDate);
  if (state.endDate) params.set('end_date', state.endDate);
  return params.toString();
}
