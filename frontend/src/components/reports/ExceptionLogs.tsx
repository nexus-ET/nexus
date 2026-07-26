import React, { useEffect, useId, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import DatePicker from 'react-datepicker';
import 'react-datepicker/dist/react-datepicker.css';
import {
  AlertTriangle,
  CalendarRange,
  ChevronLeft,
  ChevronRight,
  FileDown,
  Loader2,
  X,
} from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { type ExceptionLogRecord, useExceptionLogs } from '../../hooks/useExceptionLogs';
import {
  readExceptionLogsQuery,
  EXCEPTION_LOGS_LIMITS,
  type ExceptionLogsLimit,
  type ExceptionLogsSortField,
  totalPages,
  buildExceptionLogsExportQuery,
  writeExceptionLogsQuery,
} from '../../utils/reportsUrl';
import ReportTable, { type ReportColumn } from './ReportTable';
import { apiFetch, apiFetchBlob } from '../../utils/api';
import { useBusinessTimezone } from '../../context/BusinessTimezoneContext';

const toIsoDate = (value: Date | null): string | undefined => {
  if (!value) return undefined;
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const parseIsoDate = (value: string): Date | null => {
  if (!value) return null;
  const parsed = new Date(`${value}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
};

const formatSourceLabel = (source: string): string => {
  const normalized = source.trim().toLowerCase();
  if (normalized === 'meta_lead_sync') return 'Meta Sync';
  if (normalized === 'api_client') return 'Browser';
  if (normalized === 'backend') return 'Backend';
  if (normalized === 'scheduler') return 'Scheduler';
  if (normalized === 'webhook') return 'Webhook';
  if (normalized === 'proxy_timeout') return 'Proxy/Timeout';
  return source;
};

const statusClassName = (status: string): string => {
  const normalized = status.trim().toUpperCase();
  if (normalized === 'RESOLVED') return 'text-emerald-700 bg-emerald-50 border-emerald-200';
  if (normalized === 'OPEN') return 'text-red-700 bg-red-50 border-red-200';
  if (normalized === 'IN_PROGRESS' || normalized === 'ACKNOWLEDGED') {
    return 'text-amber-700 bg-amber-50 border-amber-200';
  }
  return 'text-text-muted bg-surface-bg border-border-subtle';
};

const severityClassName = (severity: string): string => {
  const normalized = severity.trim().toUpperCase();
  if (normalized === 'EXCEPTION' || normalized === 'ERROR') {
    return 'text-red-700 bg-red-50 border-red-200';
  }
  if (normalized === 'WARNING') return 'text-amber-800 bg-amber-50 border-amber-200';
  if (normalized === 'OMISSION') return 'text-slate-700 bg-slate-50 border-slate-200';
  return 'text-text-muted bg-surface-bg border-border-subtle';
};

const ExceptionMessageModal: React.FC<{
  record: ExceptionLogRecord | null;
  onClose: () => void;
  onStatusChange: (record: ExceptionLogRecord) => void;
  formatDateTime: (value: string | Date | null | undefined) => string;
}> = ({ record, onClose, onStatusChange, formatDateTime }) => {
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);
  const [savingStatus, setSavingStatus] = useState<string | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [resolutionComment, setResolutionComment] = useState('');

  useEffect(() => {
    if (!record) return;
    setResolutionComment(record.resolution_comment || '');
    setStatusError(null);
    closeRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [record, onClose]);

  if (!record || typeof document === 'undefined') return null;

  const handleStatusChange = async (status: 'OPEN' | 'IN_PROGRESS' | 'RESOLVED') => {
    const trimmed = resolutionComment.trim();
    if (status === 'RESOLVED' && !trimmed) {
      setStatusError('Add a resolution comment describing how this issue was fixed.');
      return;
    }
    try {
      setSavingStatus(status);
      setStatusError(null);
      const updated = (await apiFetch(`reports/exception-logs/${record.id}/status`, {
        method: 'PATCH',
        body: JSON.stringify({
          status,
          resolution_comment: trimmed || null,
        }),
      })) as ExceptionLogRecord;
      onStatusChange(updated);
      setResolutionComment(updated.resolution_comment || '');
    } catch (error: unknown) {
      setStatusError(error instanceof Error ? error.message : 'Failed to update exception status.');
    } finally {
      setSavingStatus(null);
    }
  };

  const handleSaveResolutionComment = async () => {
    const trimmed = resolutionComment.trim();
    if (!trimmed) {
      setStatusError('Resolution comment cannot be empty.');
      return;
    }
    try {
      setSavingStatus('SAVE_COMMENT');
      setStatusError(null);
      const updated = (await apiFetch(`reports/exception-logs/${record.id}/status`, {
        method: 'PATCH',
        body: JSON.stringify({
          status: record.status === 'RESOLVED' ? 'RESOLVED' : record.status,
          resolution_comment: trimmed,
        }),
      })) as ExceptionLogRecord;
      onStatusChange(updated);
      setResolutionComment(updated.resolution_comment || '');
    } catch (error: unknown) {
      setStatusError(error instanceof Error ? error.message : 'Failed to save resolution comment.');
    } finally {
      setSavingStatus(null);
    }
  };

  const commentDirty = resolutionComment.trim() !== (record.resolution_comment || '').trim();

  return createPortal(
    <div className="fixed inset-0 z-[80] flex items-center justify-center p-4">
      <button
        type="button"
        className="absolute inset-0 bg-black/40"
        aria-label="Close exception details"
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="relative z-10 flex max-h-[85vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-border-subtle bg-card shadow-xl"
      >
        <div className="flex items-start justify-between gap-3 border-b border-border-subtle bg-surface-bg px-5 py-4">
          <div className="min-w-0">
            <h2 id={titleId} className="text-base font-semibold text-text-main">
              Exception #{record.id}
            </h2>
            <p className="mt-1 text-xs text-text-muted">
              {formatDateTime(record.attempt_timestamp)} · {formatSourceLabel(record.source)} ·{' '}
              {record.category}
            </p>
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-text-muted hover:bg-card hover:text-text-main"
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          <div className="flex flex-wrap gap-2">
            <span
              className={`inline-flex rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide ${severityClassName(record.severity)}`}
            >
              {record.severity}
            </span>
            <span
              className={`inline-flex rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide ${statusClassName(record.status)}`}
            >
              {record.status}
            </span>
            {record.exception_type ? (
              <span className="inline-flex rounded-full border border-border-subtle bg-surface-bg px-2.5 py-1 text-[11px] font-medium text-text-muted">
                {record.exception_type}
              </span>
            ) : null}
          </div>

          <div className="rounded-xl border border-border-subtle bg-surface-bg px-3 py-3">
            <h3 className="text-[11px] font-bold uppercase tracking-wide text-text-muted mb-2">
              Fix status
            </h3>
            <div className="flex flex-wrap gap-2">
              {([
                ['OPEN', 'Open'],
                ['IN_PROGRESS', 'In Progress'],
                ['RESOLVED', 'Resolved'],
              ] as const).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  disabled={savingStatus !== null || record.status === value}
                  onClick={() => void handleStatusChange(value)}
                  className={`rounded-lg border px-3 py-1.5 text-xs font-semibold disabled:cursor-default ${
                    record.status === value
                      ? statusClassName(value)
                      : 'border-border-subtle bg-card text-text-muted hover:text-text-main'
                  }`}
                >
                  {savingStatus === value ? 'Updating…' : label}
                </button>
              ))}
            </div>
            {record.resolved_at ? (
              <p className="mt-2 text-xs text-text-muted">
                Resolved {formatDateTime(record.resolved_at)}
              </p>
            ) : null}
            {statusError ? <p className="mt-2 text-xs text-red-700">{statusError}</p> : null}
          </div>

          <div>
            <h3 className="text-[11px] font-bold uppercase tracking-wide text-text-muted mb-1.5">
              Resolution comment
            </h3>
            <p className="mb-2 text-xs text-text-muted">
              Describe how this issue was fixed so other admins know what changed. Cursor fixes,
              server recovery, and page-refresh clears fill this automatically when they resolve
              the issue.
            </p>
            <textarea
              value={resolutionComment}
              onChange={event => setResolutionComment(event.target.value)}
              rows={4}
              maxLength={4000}
              placeholder="e.g. Switched Meta page-token lookup off /me/accounts to avoid app-level rate limit #4; Sync Now succeeds again."
              className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm text-text-main placeholder:text-text-muted/70 focus:outline-none focus:ring-2 focus:ring-accent/30"
            />
            <div className="mt-2 flex items-center justify-between gap-3">
              <span className="text-[11px] text-text-muted">
                {resolutionComment.trim().length}/4000 · required to mark Resolved
              </span>
              {commentDirty && resolutionComment.trim() ? (
                <button
                  type="button"
                  disabled={savingStatus !== null}
                  onClick={() => void handleSaveResolutionComment()}
                  className="rounded-lg border border-border-subtle bg-card px-3 py-1.5 text-xs font-semibold text-text-main hover:bg-surface-bg disabled:opacity-50"
                >
                  {savingStatus === 'SAVE_COMMENT' ? 'Saving…' : 'Save comment'}
                </button>
              ) : null}
            </div>
          </div>

          <div>
            <h3 className="text-[11px] font-bold uppercase tracking-wide text-text-muted mb-1.5">
              Message
            </h3>
            <pre className="whitespace-pre-wrap break-words rounded-xl border border-border-subtle bg-surface-bg px-3 py-3 text-sm text-text-main font-sans leading-relaxed">
              {record.message || '—'}
            </pre>
          </div>

          {record.details?.length ? (
            <div>
              <h3 className="text-[11px] font-bold uppercase tracking-wide text-text-muted mb-1.5">
                Details
              </h3>
              <ul className="space-y-2">
                {record.details.map((item, index) => (
                  <li
                    key={`${record.id}-detail-${index}`}
                    className="whitespace-pre-wrap break-words rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm text-text-main"
                  >
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
            <div>
              <dt className="text-[11px] font-bold uppercase tracking-wide text-text-muted">Triggered by</dt>
              <dd className="mt-0.5 text-text-main">{record.triggered_by_user || '—'}</dd>
            </div>
            <div>
              <dt className="text-[11px] font-bold uppercase tracking-wide text-text-muted">Page</dt>
              <dd className="mt-0.5 text-text-main break-all">{record.page_path || '—'}</dd>
            </div>
            <div>
              <dt className="text-[11px] font-bold uppercase tracking-wide text-text-muted">Related</dt>
              <dd className="mt-0.5 text-text-main break-all">
                {record.related_resource || record.related_id
                  ? `${record.related_resource || 'resource'}${record.related_id ? `: ${record.related_id}` : ''}`
                  : '—'}
              </dd>
            </div>
          </dl>
        </div>
      </div>
    </div>,
    document.body
  );
};

const buildExceptionLogColumns = (
  formatDateTime: (value: string | Date | null | undefined) => string,
  onViewMessage: (row: ExceptionLogRecord) => void
): ReportColumn<ExceptionLogRecord>[] => [
  {
    id: 'attempt_timestamp',
    header: 'Occurred',
    sortable: true,
    pdfValue: row => formatDateTime(row.attempt_timestamp),
    render: row => <span className="whitespace-nowrap">{formatDateTime(row.attempt_timestamp)}</span>,
  },
  {
    id: 'severity',
    header: 'Severity',
    sortable: true,
    pdfValue: row => row.severity,
    render: row => (
      <span
        className={`inline-flex rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide ${severityClassName(row.severity)}`}
      >
        {row.severity}
      </span>
    ),
  },
  {
    id: 'source',
    header: 'Source',
    sortable: true,
    pdfValue: row => formatSourceLabel(row.source),
    render: row => <span className="text-sm">{formatSourceLabel(row.source)}</span>,
  },
  {
    id: 'triggered_by_user',
    header: 'Triggered By',
    sortable: true,
    pdfValue: row => row.triggered_by_user,
    render: row => <span className="text-sm text-text-muted">{row.triggered_by_user}</span>,
  },
  {
    id: 'status',
    header: 'Status',
    sortable: true,
    pdfValue: row => row.status,
    render: row => (
      <span
        className={`inline-flex rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide ${statusClassName(row.status)}`}
      >
        {row.status}
      </span>
    ),
  },
  {
    id: 'category',
    header: 'Category',
    sortable: true,
    pdfValue: row => row.category,
    render: row => <span className="text-sm font-medium">{row.category}</span>,
  },
  {
    id: 'related_id',
    header: 'Related',
    sortable: false,
    pdfValue: row => row.related_id || '—',
    render: row => (
      <span className="tabular-nums text-text-muted" title={row.related_resource || undefined}>
        {row.related_id || '—'}
      </span>
    ),
  },
  {
    id: 'message',
    header: 'Message',
    sortable: true,
    pdfValue: row => row.message || '—',
    cellClassName: 'max-w-md',
    render: row => (
      <div className="max-w-md">
        <p className="text-sm text-text-muted whitespace-pre-wrap break-words">{row.message || '—'}</p>
        {row.resolution_comment ? (
          <p className="mt-1.5 text-xs text-emerald-800 whitespace-pre-wrap break-words">
            <span className="font-semibold">Resolution:</span> {row.resolution_comment}
          </p>
        ) : null}
        <button
          type="button"
          onClick={() => onViewMessage(row)}
          className="mt-1 text-[11px] font-semibold text-accent hover:underline"
        >
          View full message
          {row.details?.length
            ? ` (+${row.details.length} detail${row.details.length === 1 ? '' : 's'})`
            : ''}
        </button>
      </div>
    ),
  },
];

const ExceptionLogs: React.FC<{
  refreshRef?: React.MutableRefObject<(() => void) | null>;
}> = ({ refreshRef }) => {
  const { formatDateTime } = useBusinessTimezone();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryState = useMemo(() => readExceptionLogsQuery(searchParams), [searchParams]);
  const [selectedException, setSelectedException] = useState<ExceptionLogRecord | null>(null);

  useEffect(() => {
    if (searchParams.has('limit')) return;
    if (queryState.limit === 25) return;
    setSearchParams(writeExceptionLogsQuery(searchParams, { limit: queryState.limit }), {
      replace: true,
    });
  }, [queryState.limit, searchParams, setSearchParams]);

  const [draftStartDate, setDraftStartDate] = useState<Date | null>(() =>
    parseIsoDate(queryState.startDate)
  );
  const [draftEndDate, setDraftEndDate] = useState<Date | null>(() =>
    parseIsoDate(queryState.endDate)
  );
  const [accessDenied, setAccessDenied] = useState(false);
  const [exportingPdf, setExportingPdf] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const { data, isLoading, isFetching, error, refetch } = useExceptionLogs(queryState);

  const handleStatusChange = (updated: ExceptionLogRecord) => {
    setSelectedException(updated);
    void refetch();
  };

  useEffect(() => {
    if (!refreshRef) return;
    refreshRef.current = () => {
      void refetch();
    };
    return () => {
      refreshRef.current = null;
    };
  }, [refreshRef, refetch]);

  useEffect(() => {
    setDraftStartDate(parseIsoDate(queryState.startDate));
    setDraftEndDate(parseIsoDate(queryState.endDate));
  }, [queryState.startDate, queryState.endDate]);

  useEffect(() => {
    if (!error) {
      setAccessDenied(false);
      return;
    }
    const message = error instanceof Error ? error.message : 'Failed to load exception logs.';
    if (message.toLowerCase().includes('super admin') || message.toLowerCase().includes('access denied')) {
      setAccessDenied(true);
    }
  }, [error]);

  const columns = useMemo(
    () => buildExceptionLogColumns(formatDateTime, setSelectedException),
    [formatDateTime]
  );
  const logs = data?.logs ?? [];
  const totalCount = data?.total_count ?? 0;
  const page = queryState.page;
  const limit = queryState.limit;
  const pages = totalPages(totalCount, limit);

  const updateQuery = (patch: Parameters<typeof writeExceptionLogsQuery>[1]) => {
    setSearchParams(writeExceptionLogsQuery(searchParams, patch), { replace: true });
  };

  const handleApplyFilters = () => {
    updateQuery({
      startDate: toIsoDate(draftStartDate) || '',
      endDate: toIsoDate(draftEndDate) || '',
      page: 1,
    });
  };

  const handleSort = (columnId: string) => {
    const sortBy = columnId as ExceptionLogsSortField;
    const nextOrder =
      queryState.sortBy === sortBy && queryState.sortOrder === 'desc' ? 'asc' : 'desc';
    updateQuery({ sortBy, sortOrder: nextOrder, page: 1 });
  };

  const handleLimitChange = (value: string) => {
    const parsed = Number(value) as ExceptionLogsLimit;
    if (!EXCEPTION_LOGS_LIMITS.includes(parsed)) return;
    updateQuery({ limit: parsed, page: 1 });
  };

  const handleExportPdf = async () => {
    setExportError(null);
    setExportingPdf(true);
    try {
      const qs = buildExceptionLogsExportQuery(queryState);
      const blob = await apiFetchBlob(`reports/export/exception-logs?${qs}`, {
        timeoutMs: 5 * 60_000,
      });
      const filename = `exception-logs-${new Date().toISOString().slice(0, 10)}.pdf`;
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (err: unknown) {
      setExportError(err instanceof Error ? err.message : 'Failed to export PDF.');
    } finally {
      setExportingPdf(false);
    }
  };

  const errorMessage =
    error instanceof Error
      ? /not found/i.test(error.message)
        ? (() => {
            const host = typeof window !== 'undefined' ? window.location.hostname : '';
            const isLocalDev = /^(localhost|127\.0\.0\.1)$/i.test(host);
            return isLocalDev
              ? 'Reports API route not found. Restart the NEXUS backend so new report endpoints are loaded (dev: port 8002).'
              : 'Reports API route not found. Redeploy/restart the NEXUS backend so the latest report endpoints are available.';
          })()
        : error.message
      : null;

  if (accessDenied) {
    return (
      <div className="rounded-2xl border border-amber-200 bg-amber-50 px-6 py-8 text-sm text-amber-900">
        You do not have access to view the Exception Report.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex items-center gap-2 text-text-main">
            <AlertTriangle size={20} className="text-accent" />
            <h1 className="text-2xl font-bold tracking-tight">Exception Report</h1>
          </div>
          <p className="mt-1 text-sm text-text-muted max-w-3xl">
            Read-only trail of errors, exceptions, timeouts, and omissions across Nexus. This page never
            retries failed work — it surfaces what went wrong so ops can follow up.
          </p>
        </div>

        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-[11px] font-semibold uppercase tracking-wide text-text-muted mb-1.5">
              Start Date
            </label>
            <DatePicker
              selected={draftStartDate}
              onChange={date => setDraftStartDate(date)}
              selectsStart
              startDate={draftStartDate}
              endDate={draftEndDate}
              placeholderText="Any"
              className="w-40 rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm text-text-main focus:outline-none focus:border-accent focus:ring-4 focus:ring-accent/10"
            />
          </div>
          <div>
            <label className="block text-[11px] font-semibold uppercase tracking-wide text-text-muted mb-1.5">
              End Date
            </label>
            <DatePicker
              selected={draftEndDate}
              onChange={date => setDraftEndDate(date)}
              selectsEnd
              startDate={draftStartDate}
              endDate={draftEndDate}
              minDate={draftStartDate ?? undefined}
              placeholderText="Any"
              className="w-40 rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm text-text-main focus:outline-none focus:border-accent focus:ring-4 focus:ring-accent/10"
            />
          </div>
          <button
            type="button"
            onClick={handleApplyFilters}
            disabled={isLoading}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-accent text-text-dark-bg text-sm font-semibold hover:opacity-90 disabled:opacity-50"
          >
            {isLoading ? <Loader2 size={16} className="animate-spin" /> : null}
            Apply
          </button>
          <button
            type="button"
            onClick={() => void refetch()}
            disabled={isFetching}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-border-subtle bg-card text-sm font-semibold hover:bg-surface-bg disabled:opacity-50"
          >
            {isFetching ? <Loader2 size={16} className="animate-spin" /> : null}
            Refresh
          </button>
          <button
            type="button"
            onClick={() => void handleExportPdf()}
            disabled={isLoading || exportingPdf || totalCount === 0}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-border-subtle bg-card text-sm font-semibold hover:bg-surface-bg disabled:opacity-50"
          >
            {exportingPdf ? <Loader2 size={16} className="animate-spin" /> : <FileDown size={16} />}
            {exportingPdf ? 'Generating PDF…' : 'Download PDF'}
          </button>
        </div>
      </div>

      <div className="rounded-xl border border-border-subtle bg-surface-bg/60 px-4 py-3 flex items-center gap-2 text-xs text-text-muted">
        <CalendarRange size={14} className="text-accent" />
        {totalCount.toLocaleString()} matching record{totalCount === 1 ? '' : 's'}
        {totalCount > 0 ? ' · Download PDF exports the full filtered dataset' : ''}
        {isFetching && !isLoading ? ' · updating…' : ''}
      </div>

      {errorMessage && !accessDenied ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {errorMessage}
        </div>
      ) : null}

      {exportError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {exportError}
        </div>
      ) : null}

      <ReportTable
        title="Exceptions & Omissions"
        columns={columns}
        rows={logs}
        loading={isLoading}
        getRowKey={row => row.id}
        sortBy={queryState.sortBy}
        sortOrder={queryState.sortOrder}
        onSort={handleSort}
        emptyMessage="No exceptions found for the selected filters. Failures from Meta sync, API timeouts, and backend errors will appear here."
      />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between rounded-2xl border border-border-subtle bg-card px-4 py-3">
        <div className="flex items-center gap-2 text-sm text-text-muted">
          <label htmlFor="exception-logs-limit" className="font-medium text-text-main">
            Rows per page
          </label>
          <select
            id="exception-logs-limit"
            value={limit}
            onChange={event => handleLimitChange(event.target.value)}
            className="rounded-lg border border-border-subtle bg-surface-bg px-2.5 py-1.5 text-sm text-text-main focus:outline-none focus:border-accent"
          >
            {EXCEPTION_LOGS_LIMITS.map(option => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-sm text-text-muted tabular-nums">
            Page {page} of {pages}
          </span>
          <button
            type="button"
            onClick={() => updateQuery({ page: Math.max(1, page - 1) })}
            disabled={page <= 1 || isLoading}
            className="inline-flex items-center gap-1 rounded-lg border border-border-subtle px-3 py-1.5 text-sm font-medium hover:bg-surface-bg disabled:opacity-50"
          >
            <ChevronLeft size={16} />
            Previous
          </button>
          <button
            type="button"
            onClick={() => updateQuery({ page: Math.min(pages, page + 1) })}
            disabled={page >= pages || isLoading}
            className="inline-flex items-center gap-1 rounded-lg border border-border-subtle px-3 py-1.5 text-sm font-medium hover:bg-surface-bg disabled:opacity-50"
          >
            Next
            <ChevronRight size={16} />
          </button>
        </div>
      </div>

      <ExceptionMessageModal
        record={selectedException}
        onClose={() => setSelectedException(null)}
        onStatusChange={handleStatusChange}
        formatDateTime={formatDateTime}
      />
    </div>
  );
};

export default ExceptionLogs;
