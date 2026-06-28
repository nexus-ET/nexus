import React, { useEffect, useMemo, useState } from 'react';
import DatePicker from 'react-datepicker';
import 'react-datepicker/dist/react-datepicker.css';
import { CalendarRange, ChevronLeft, ChevronRight, CloudDownload, FileDown, Loader2 } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { type SyncLogRecord, useSyncLogs } from '../../hooks/useSyncLogs';
import { useReportsSyncSchedule } from '../../hooks/useReportsSyncSchedule';
import {
  readSyncLogsQuery,
  SYNC_LOGS_LIMITS,
  type SyncLogsLimit,
  type SyncLogsSortField,
  totalPages,
  buildSyncLogsExportQuery,
  writeSyncLogsQuery,
} from '../../utils/reportsUrl';
import ReportTable, { type ReportColumn } from './ReportTable';
import IngestionQualityPanel from './IngestionQualityPanel';
import { apiFetchBlob } from '../../utils/api';
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

const formatSyncMode = (mode: string): string => {
  const normalized = mode.trim().toUpperCase();
  if (normalized === 'AUTOMATED') return 'Scheduled';
  if (normalized === 'MANUAL') return 'Manual';
  return mode;
};

const formatSourceLabel = (source: string): string => {
  const normalized = source.trim().toLowerCase();
  if (normalized === 'scheduled') return 'Scheduler';
  if (normalized === 'manual_api') return 'Settings';
  if (normalized === 'webhook') return 'Webhook';
  if (normalized === 'backfill') return 'Backfill';
  return source;
};

const statusClassName = (status: string): string => {
  const normalized = status.trim().toUpperCase();
  if (normalized === 'SUCCESS') return 'text-emerald-700 bg-emerald-50 border-emerald-200';
  if (normalized === 'FAILED') return 'text-red-700 bg-red-50 border-red-200';
  if (normalized === 'IN_PROGRESS') return 'text-amber-700 bg-amber-50 border-amber-200';
  if (normalized === 'WARNING') return 'text-amber-800 bg-amber-50 border-amber-200';
  return 'text-text-muted bg-surface-bg border-border-subtle';
};

const buildSyncLogColumns = (
  formatDateTime: (value: string | Date | null | undefined) => string
): ReportColumn<SyncLogRecord>[] => [
  {
    id: 'attempt_timestamp',
    header: 'Attempted',
    sortable: true,
    pdfValue: row => formatDateTime(row.attempt_timestamp),
    render: row => <span className="whitespace-nowrap">{formatDateTime(row.attempt_timestamp)}</span>,
  },
  {
    id: 'sync_mode',
    header: 'Mode',
    sortable: true,
    pdfValue: row => formatSyncMode(row.sync_mode),
    render: row => <span className="text-sm font-medium">{formatSyncMode(row.sync_mode)}</span>,
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
    id: 'leads_created',
    header: 'New Leads',
    sortable: true,
    pdfValue: row => String(row.leads_created),
    render: row => <span className="font-semibold tabular-nums">{row.leads_created}</span>,
  },
  {
    id: 'leads_seen',
    header: 'Seen',
    sortable: true,
    pdfValue: row => String(row.leads_seen),
    render: row => <span className="tabular-nums text-text-muted">{row.leads_seen}</span>,
  },
  {
    id: 'message',
    header: 'Message',
    sortable: true,
    pdfValue: row => row.message || '—',
    render: row => (
      <span className="text-sm text-text-muted max-w-md inline-block truncate" title={row.message || undefined}>
        {row.message || '—'}
      </span>
    ),
  },
];

const SyncLogs: React.FC = () => {
  const { formatDateTime } = useBusinessTimezone();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryState = useMemo(() => readSyncLogsQuery(searchParams), [searchParams]);

  // Keep URL in sync with stored rows-per-page when landing on /reports without query params.
  useEffect(() => {
    if (searchParams.has('limit')) return;
    if (queryState.limit === 25) return;
    setSearchParams(writeSyncLogsQuery(searchParams, { limit: queryState.limit }), { replace: true });
  }, [queryState.limit, searchParams, setSearchParams]);

  const [draftStartDate, setDraftStartDate] = useState<Date | null>(() => parseIsoDate(queryState.startDate));
  const [draftEndDate, setDraftEndDate] = useState<Date | null>(() => parseIsoDate(queryState.endDate));
  const [accessDenied, setAccessDenied] = useState(false);
  const [exportingPdf, setExportingPdf] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const { data, isLoading, isFetching, error, refetch } = useSyncLogs(queryState);
  const { data: schedule } = useReportsSyncSchedule();

  useEffect(() => {
    setDraftStartDate(parseIsoDate(queryState.startDate));
    setDraftEndDate(parseIsoDate(queryState.endDate));
  }, [queryState.startDate, queryState.endDate]);

  useEffect(() => {
    if (!error) {
      setAccessDenied(false);
      return;
    }
    const message = error instanceof Error ? error.message : 'Failed to load sync logs.';
    if (message.toLowerCase().includes('super admin') || message.toLowerCase().includes('access denied')) {
      setAccessDenied(true);
    }
  }, [error]);

  const columns = useMemo(() => buildSyncLogColumns(formatDateTime), [formatDateTime]);
  const logs = data?.logs ?? [];
  const totalCount = data?.total_count ?? 0;
  const page = queryState.page;
  const limit = queryState.limit;
  const pages = totalPages(totalCount, limit);

  const updateQuery = (patch: Parameters<typeof writeSyncLogsQuery>[1]) => {
    setSearchParams(writeSyncLogsQuery(searchParams, patch), { replace: true });
  };

  const handleApplyFilters = () => {
    updateQuery({
      startDate: toIsoDate(draftStartDate) || '',
      endDate: toIsoDate(draftEndDate) || '',
      page: 1,
    });
  };

  const handleSort = (columnId: string) => {
    const sortBy = columnId as SyncLogsSortField;
    const nextOrder =
      queryState.sortBy === sortBy && queryState.sortOrder === 'desc' ? 'asc' : 'desc';
    updateQuery({ sortBy, sortOrder: nextOrder, page: 1 });
  };

  const handleLimitChange = (value: string) => {
    const parsed = Number(value) as SyncLogsLimit;
    if (!SYNC_LOGS_LIMITS.includes(parsed)) return;
    updateQuery({ limit: parsed, page: 1 });
  };

  const handleExportPdf = async () => {
    setExportError(null);
    setExportingPdf(true);
    try {
      const qs = buildSyncLogsExportQuery(queryState);
      const blob = await apiFetchBlob(`reports/export/sync-logs?${qs}`, {
        timeoutMs: 5 * 60_000,
      });
      const filename = `sync-logs-${new Date().toISOString().slice(0, 10)}.pdf`;
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
        ? 'Reports API is unavailable. Restart the NEXUS backend on port 8002 (see vite.config.js proxy).'
        : error.message
      : null;

  if (accessDenied) {
    return (
      <div className="rounded-2xl border border-amber-200 bg-amber-50 px-6 py-8 text-sm text-amber-900">
        You do not have access to view sync logs on the Reports page.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex items-center gap-2 text-text-main">
            <CloudDownload size={20} className="text-accent" />
            <h1 className="text-2xl font-bold tracking-tight">Meta Lead Sync Logs</h1>
          </div>
          <p className="mt-1 text-sm text-text-muted max-w-3xl">
            Read-only audit trail of Meta lead sync attempts. Sync is controlled on the Dashboard (manual or
            automated) — this page never runs ingestion.
          </p>
          {schedule?.help_text ? (
            <p className="mt-2 text-xs text-text-muted max-w-3xl rounded-lg border border-border-subtle bg-surface-bg/80 px-3 py-2">
              {schedule.help_text}
            </p>
          ) : null}
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
        {schedule?.mode === 'automated' && schedule.next_scheduled_run_at
          ? ` · Next automated sync (Dashboard): ${formatDateTime(schedule.next_scheduled_run_at)}`
          : schedule?.mode === 'manual'
            ? ' · Manual mode (Settings) — use Sync Now to ingest leads'
            : ''}
        {isFetching && !isLoading ? ' · updating…' : ''}
      </div>

      {errorMessage && !accessDenied ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{errorMessage}</div>
      ) : null}

      {exportError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{exportError}</div>
      ) : null}

      <IngestionQualityPanel startDate={queryState.startDate} endDate={queryState.endDate} />

      <ReportTable
        title="Sync Attempts"
        columns={columns}
        rows={logs}
        loading={isLoading}
        getRowKey={row => row.id}
        sortBy={queryState.sortBy}
        sortOrder={queryState.sortOrder}
        onSort={handleSort}
        emptyMessage="No sync logs found for the selected filters. Run a sync from Settings or wait for the next scheduled run."
      />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between rounded-2xl border border-border-subtle bg-card px-4 py-3">
        <div className="flex items-center gap-2 text-sm text-text-muted">
          <label htmlFor="sync-logs-limit" className="font-medium text-text-main">
            Rows per page
          </label>
          <select
            id="sync-logs-limit"
            value={limit}
            onChange={event => handleLimitChange(event.target.value)}
            className="rounded-lg border border-border-subtle bg-surface-bg px-2.5 py-1.5 text-sm text-text-main focus:outline-none focus:border-accent"
          >
            {SYNC_LOGS_LIMITS.map(option => (
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
    </div>
  );
};

export default SyncLogs;
