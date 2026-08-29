import React, { useCallback, useEffect, useMemo, useState } from 'react';
import DatePicker from 'react-datepicker';
import 'react-datepicker/dist/react-datepicker.css';
import {
  ChevronLeft,
  ChevronRight,
  FileDown,
  Loader2,
  RefreshCw,
  ScrollText,
  Search,
} from 'lucide-react';
import { apiFetch, apiFetchBlob } from '../../utils/api';
import ReportTable, { type ReportColumn } from '../reports/ReportTable';
import { useBusinessTimezone } from '../../context/BusinessTimezoneContext';

export interface AuditLogRecord {
  id: number;
  user_id: number | null;
  user_email: string | null;
  user_name: string | null;
  action_type: string;
  target_resource: string;
  resource_id: string | null;
  details: Record<string, unknown> | null;
  ip_address: string | null;
  timestamp: string;
  session_id: string | null;
  sync_mode: string | null;
  user_agent: string | null;
  status: string;
}

interface AuditLogsResponse {
  logs: AuditLogRecord[];
  total_count: number;
  page: number;
  limit: number;
  total_pages: number;
}

interface AuditUserOption {
  id: number;
  email: string;
  label: string;
}

type SortField =
  | 'timestamp'
  | 'action_type'
  | 'target_resource'
  | 'user_id'
  | 'status'
  | 'sync_mode'
  | 'ip_address';
type SortOrder = 'asc' | 'desc';
type PageLimit = 25 | 50 | 100;

const LIMIT_OPTIONS: PageLimit[] = [25, 50, 100];

const toIsoDate = (value: Date | null): string | undefined => {
  if (!value) return undefined;
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const ACTION_TYPE_LABELS: Record<string, string> = {
  PAGE_VIEW: 'Page visit',
  UI_CLICK: 'Button / control click',
  UI_FIELD_CHANGE: 'Field change',
  API_READ: 'Data load',
  LOGIN_SUCCESS: 'Sign in',
  LOGIN_FAILURE: 'Failed sign in',
  LOGOUT: 'Sign out',
  CREATE: 'Create',
  UPDATE: 'Update',
  DELETE: 'Delete',
};

const formatActionType = (actionType: string): string =>
  ACTION_TYPE_LABELS[actionType] || actionType.replace(/_/g, ' ');

const formatDetails = (details: Record<string, unknown> | null): string => {
  if (!details || Object.keys(details).length === 0) return '—';

  const summary = typeof details.summary === 'string' ? details.summary.trim() : '';
  if (summary) {
    const parts = [summary];
    const page =
      (typeof details.page === 'string' && details.page) ||
      (typeof details.menu === 'string' && details.menu) ||
      '';
    if (page && !summary.includes(page)) {
      parts.push(`Page: ${page}`);
    }
    const action = typeof details.action === 'string' ? details.action : '';
    if (action && !summary.includes(action) && !summary.includes(action.replace(/^Loaded /, ''))) {
      parts.push(`Action: ${action}`);
    }
    const metadata = details.metadata as Record<string, unknown> | undefined;
    const triggerControl = metadata?.trigger_control;
    const triggerValue = metadata?.trigger_value;
    if (
      triggerControl &&
      triggerValue &&
      !summary.includes(String(triggerControl)) &&
      !summary.includes(String(triggerValue))
    ) {
      parts.push(`${triggerControl}: ${triggerValue}`);
    }
    return parts.join(' · ');
  }

  if (typeof details.username === 'string') {
    return `Auth event for ${details.username}`;
  }

  const method = (details.method || details.http_method) as string | undefined;
  const path = (details.path || details.api_endpoint) as string | undefined;
  const statusCode = details.status_code;
  const legacyParts: string[] = [];
  if (method && path) legacyParts.push(`${method} ${path}`);
  if (statusCode !== undefined && statusCode !== null) legacyParts.push(`HTTP ${statusCode}`);
  if (typeof details.message === 'string') legacyParts.push(details.message);
  if (legacyParts.length > 0) return legacyParts.join(' · ');

  try {
    const text = JSON.stringify(details);
    return text.length > 120 ? `${text.slice(0, 117)}...` : text;
  } catch {
    return '—';
  }
};

const statusClassName = (status: string): string => {
  const normalized = status.trim().toLowerCase();
  if (normalized === 'success') return 'text-emerald-700 bg-emerald-50 border-emerald-200';
  if (normalized === 'failed') return 'text-red-700 bg-red-50 border-red-200';
  return 'text-text-muted bg-surface-bg border-border-subtle';
};

const buildExportQuery = (params: {
  startDate?: string;
  endDate?: string;
  userId?: number | null;
  keyword?: string;
  sortBy: SortField;
  sortOrder: SortOrder;
}): string => {
  const search = new URLSearchParams();
  if (params.startDate) search.set('start_date', params.startDate);
  if (params.endDate) search.set('end_date', params.endDate);
  if (params.userId) search.set('user_id', String(params.userId));
  if (params.keyword?.trim()) search.set('keyword', params.keyword.trim());
  search.set('sort_by', params.sortBy);
  search.set('sort_order', params.sortOrder);
  const query = search.toString();
  return query ? `?${query}` : '';
};

const AuditLogViewer: React.FC = () => {
  const { formatAuditDateTime } = useBusinessTimezone();
  const [logs, setLogs] = useState<AuditLogRecord[]>([]);
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState<PageLimit>(25);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [sortBy, setSortBy] = useState<SortField>('timestamp');
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc');
  const [startDate, setStartDate] = useState<Date | null>(null);
  const [endDate, setEndDate] = useState<Date | null>(null);
  const [userId, setUserId] = useState<number | ''>('');
  const [keyword, setKeyword] = useState('');
  const [draftKeyword, setDraftKeyword] = useState('');
  const [users, setUsers] = useState<AuditUserOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadUsers = useCallback(async () => {
    try {
      const data = (await apiFetch('users')) as Array<{
        id: number;
        email: string;
        first_name?: string | null;
        last_name?: string | null;
      }>;
      setUsers(
        data.map(user => ({
          id: user.id,
          email: user.email,
          label:
            [user.first_name, user.last_name].filter(Boolean).join(' ').trim() || user.email,
        }))
      );
    } catch {
      setUsers([]);
    }
  }, []);

  const loadLogs = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const params = new URLSearchParams({
        page: String(page),
        limit: String(limit),
        sort_by: sortBy,
        sort_order: sortOrder,
      });
      const start = toIsoDate(startDate);
      const end = toIsoDate(endDate);
      if (start) params.set('start_date', start);
      if (end) params.set('end_date', end);
      if (userId) params.set('user_id', String(userId));
      if (keyword.trim()) params.set('keyword', keyword.trim());

      const data = (await apiFetch(`admin/audit-logs?${params.toString()}`)) as AuditLogsResponse;
      setLogs(Array.isArray(data.logs) ? data.logs : []);
      setTotalPages(data.total_pages || 1);
      setTotalCount(data.total_count || 0);
    } catch (err: unknown) {
      setLogs([]);
      setError(err instanceof Error ? err.message : 'Failed to load audit logs.');
    } finally {
      setLoading(false);
    }
  }, [page, limit, sortBy, sortOrder, startDate, endDate, userId, keyword]);

  useEffect(() => {
    void loadUsers();
  }, [loadUsers]);

  useEffect(() => {
    void loadLogs();
  }, [loadLogs]);

  const pageNumbers = useMemo(() => {
    const pages: number[] = [];
    const start = Math.max(1, page - 2);
    const end = Math.min(totalPages, page + 2);
    for (let i = start; i <= end; i += 1) pages.push(i);
    return pages;
  }, [page, totalPages]);

  const columns: ReportColumn<AuditLogRecord>[] = useMemo(
    () => [
      {
        id: 'timestamp',
        header: 'Timestamp',
        sortable: true,
        render: row => <span className="whitespace-nowrap">{formatAuditDateTime(row.timestamp)}</span>,
      },
      {
        id: 'user_id',
        header: 'User',
        sortable: true,
        render: row => (
          <div className="min-w-[140px]">
            <div className="font-medium text-text-main">{row.user_name || row.user_email || '—'}</div>
            {row.user_email ? <div className="text-[11px] text-text-muted">{row.user_email}</div> : null}
          </div>
        ),
      },
      {
        id: 'action_type',
        header: 'Action',
        sortable: true,
        render: row => <span className="text-xs font-medium">{formatActionType(row.action_type)}</span>,
      },
      {
        id: 'target_resource',
        header: 'Resource',
        sortable: true,
        render: row => <span>{row.target_resource}</span>,
      },
      {
        id: 'sync_mode',
        header: 'Mode',
        sortable: true,
        render: row => <span className="text-xs uppercase">{row.sync_mode || '—'}</span>,
      },
      {
        id: 'status',
        header: 'Status',
        sortable: true,
        render: row => (
          <span className={`inline-flex px-2 py-0.5 rounded-full border text-[10px] font-bold uppercase ${statusClassName(row.status)}`}>
            {row.status}
          </span>
        ),
      },
      {
        id: 'ip_address',
        header: 'IP',
        sortable: true,
        render: row => <span className="font-mono text-xs">{row.ip_address || '—'}</span>,
      },
      {
        id: 'details',
        header: 'Details',
        sortable: false,
        render: row => <span className="text-xs text-text-muted">{formatDetails(row.details)}</span>,
      },
    ],
    [formatAuditDateTime]
  );

  const handleSort = (field: string) => {
    const nextField = field as SortField;
    if (sortBy === nextField) {
      setSortOrder(prev => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortBy(nextField);
      setSortOrder('desc');
    }
    setPage(1);
  };

  const handleExportPdf = async () => {
    try {
      setExporting(true);
      const blob = await apiFetchBlob(
        `admin/audit-logs/export-pdf${buildExportQuery({
          startDate: toIsoDate(startDate),
          endDate: toIsoDate(endDate),
          userId: userId || null,
          keyword,
          sortBy,
          sortOrder,
        })}`
      );
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `audit-logs-${new Date().toISOString().slice(0, 10)}.pdf`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'PDF export failed.');
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex items-center gap-2 text-text-main">
            <ScrollText size={20} className="text-accent" />
            <h1 className="text-2xl font-bold tracking-tight">Audit Logs</h1>
          </div>
          <p className="mt-1 text-sm text-text-muted max-w-3xl">
            Full activity trail: page visits, button clicks, field changes, data loads, and server-side mutations.
            Super Admin access only.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void loadLogs()}
            disabled={loading}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-border-subtle bg-card text-sm hover:bg-surface-bg disabled:opacity-50"
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
          <button
            type="button"
            onClick={() => void handleExportPdf()}
            disabled={exporting || loading}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-accent text-text-dark-bg text-sm font-semibold hover:opacity-90 disabled:opacity-50"
          >
            {exporting ? <Loader2 size={16} className="animate-spin" /> : <FileDown size={16} />}
            Export to PDF
          </button>
        </div>
      </div>

      <div className="rounded-xl border border-border-subtle bg-card p-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-3">
        <div>
          <label className="block text-[11px] font-semibold uppercase tracking-wide text-text-muted mb-1.5">
            Start Date
          </label>
          <DatePicker
            selected={startDate}
            onChange={date => {
              setStartDate(date);
              setPage(1);
            }}
            selectsStart
            startDate={startDate}
            endDate={endDate}
            className="w-full rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm"
            placeholderText="From"
          />
        </div>
        <div>
          <label className="block text-[11px] font-semibold uppercase tracking-wide text-text-muted mb-1.5">
            End Date
          </label>
          <DatePicker
            selected={endDate}
            onChange={date => {
              setEndDate(date);
              setPage(1);
            }}
            selectsEnd
            startDate={startDate}
            endDate={endDate}
            minDate={startDate || undefined}
            className="w-full rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm"
            placeholderText="To"
          />
        </div>
        <div>
          <label className="block text-[11px] font-semibold uppercase tracking-wide text-text-muted mb-1.5">
            User
          </label>
          <select
            value={userId}
            onChange={event => {
              setUserId(event.target.value ? Number(event.target.value) : '');
              setPage(1);
            }}
            className="w-full rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm"
          >
            <option value="">All users</option>
            {users.map(user => (
              <option key={user.id} value={user.id}>
                {user.label}
              </option>
            ))}
          </select>
        </div>
        <div className="md:col-span-2 xl:col-span-2">
          <label className="block text-[11px] font-semibold uppercase tracking-wide text-text-muted mb-1.5">
            Keyword
          </label>
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
              <input
                value={draftKeyword}
                onChange={event => setDraftKeyword(event.target.value)}
                onKeyDown={event => {
                  if (event.key === 'Enter') {
                    setKeyword(draftKeyword);
                    setPage(1);
                  }
                }}
                placeholder="Action, resource, IP, email..."
                className="w-full pl-9 pr-3 py-2 rounded-lg border border-border-subtle bg-surface-bg text-sm"
              />
            </div>
            <button
              type="button"
              onClick={() => {
                setKeyword(draftKeyword);
                setPage(1);
              }}
              className="px-3 py-2 rounded-lg border border-border-subtle bg-card text-sm font-semibold hover:bg-surface-bg"
            >
              Search
            </button>
          </div>
        </div>
      </div>

      {error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      ) : null}

      <ReportTable
        columns={columns}
        rows={logs}
        loading={loading}
        sortBy={sortBy}
        sortOrder={sortOrder}
        onSort={handleSort}
        getRowKey={row => row.id}
        emptyMessage="No audit log entries match the current filters."
      />

      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <p className="text-xs text-text-muted">
          Showing page {page} of {totalPages} · {totalCount.toLocaleString()} total entries
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={limit}
            onChange={event => {
              setLimit(Number(event.target.value) as PageLimit);
              setPage(1);
            }}
            className="rounded-lg border border-border-subtle bg-card px-2 py-1.5 text-xs"
          >
            {LIMIT_OPTIONS.map(option => (
              <option key={option} value={option}>
                {option} / page
              </option>
            ))}
          </select>
          <button
            type="button"
            disabled={page <= 1 || loading}
            onClick={() => setPage(prev => Math.max(1, prev - 1))}
            className="inline-flex items-center gap-1 rounded-lg border border-border-subtle px-2.5 py-1.5 text-xs font-semibold text-text-muted hover:text-text-main disabled:opacity-40"
            aria-label="Previous page"
          >
            <ChevronLeft size={16} />
            Previous
          </button>
          {pageNumbers.map(pageNumber => (
            <button
              key={pageNumber}
              type="button"
              disabled={loading}
              onClick={() => setPage(pageNumber)}
              className={`min-w-8 rounded-lg border px-2 py-1.5 text-xs font-semibold ${
                pageNumber === page
                  ? 'border-accent bg-accent text-text-dark-bg'
                  : 'border-border-subtle text-text-muted hover:text-text-main'
              }`}
            >
              {pageNumber}
            </button>
          ))}
          <button
            type="button"
            disabled={page >= totalPages || loading}
            onClick={() => setPage(prev => Math.min(totalPages, prev + 1))}
            className="inline-flex items-center gap-1 rounded-lg border border-border-subtle px-2.5 py-1.5 text-xs font-semibold text-text-muted hover:text-text-main disabled:opacity-40"
            aria-label="Next page"
          >
            Next
            <ChevronRight size={16} />
          </button>
        </div>
      </div>
    </div>
  );
};

export default AuditLogViewer;
