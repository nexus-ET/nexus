import React, { useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Loader2,
  RefreshCw,
  Save,
  Trash2,
  Wrench,
} from 'lucide-react';
import { type QuarantineRecord, useQuarantineMutations, useQuarantineRecords } from '../../hooks/useQuarantine';

const formatTimestamp = (value?: string | null): string => {
  if (!value) return '—';
  return new Date(value).toLocaleString();
};

const QuarantineDashboard: React.FC = () => {
  const [page, setPage] = useState(1);
  const [limit] = useState(25);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [editorValue, setEditorValue] = useState('');
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const { data, isLoading, isFetching, refetch } = useQuarantineRecords(page, limit);
  const { reprocessRecord, deleteRecord } = useQuarantineMutations();

  const records = data?.records ?? [];
  const totalPages = data?.total_pages ?? 1;

  const selected = useMemo(
    () => records.find(record => record.id === selectedId) ?? records[0] ?? null,
    [records, selectedId]
  );

  React.useEffect(() => {
    if (!selected) return;
    setSelectedId(selected.id);
    setEditorValue(JSON.stringify(selected.normalized_payload ?? {}, null, 2));
  }, [selected?.id]);

  const handleReprocess = async () => {
    if (!selected) return;
    setActionMessage(null);
    setActionError(null);
    try {
      const parsed = JSON.parse(editorValue) as Record<string, unknown>;
      const result = (await reprocessRecord.mutateAsync({
        id: selected.id,
        normalized_payload: parsed,
      })) as { success?: boolean; error_reason?: string; lead_id?: number };
      if (result.success) {
        setActionMessage(`Lead promoted successfully (lead_id=${result.lead_id ?? 'n/a'}).`);
      } else {
        setActionError(result.error_reason || 'Validation failed during reprocess.');
      }
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Reprocess failed.');
    }
  };

  const handleDelete = async () => {
    if (!selected) return;
    if (!window.confirm('Permanently delete this quarantined record?')) return;
    setActionMessage(null);
    setActionError(null);
    try {
      await deleteRecord.mutateAsync(selected.id);
      setActionMessage('Quarantine record deleted.');
      setSelectedId(null);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Delete failed.');
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex items-center gap-2 text-text-main">
            <AlertTriangle size={20} className="text-amber-500" />
            <h1 className="text-2xl font-bold tracking-tight">Lead Quarantine</h1>
          </div>
          <p className="mt-1 text-sm text-text-muted max-w-3xl">
            Review invalid Meta submissions, fix payload data, and reprocess into Prospects. Records retain
            sync mode and triggered-by metadata for audit.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void refetch()}
          disabled={isFetching}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-border-subtle bg-card text-sm font-semibold hover:bg-surface-bg disabled:opacity-50"
        >
          {isFetching ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
          Refresh
        </button>
      </div>

      {actionMessage ? (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800 flex items-center gap-2">
          <CheckCircle2 size={16} />
          {actionMessage}
        </div>
      ) : null}
      {actionError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{actionError}</div>
      ) : null}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="xl:col-span-1 rounded-2xl border border-border-subtle bg-card overflow-hidden">
          <div className="px-4 py-3 border-b border-border-subtle text-sm font-semibold text-text-main">
            Quarantined Leads ({data?.total_count ?? 0})
          </div>
          {isLoading ? (
            <div className="p-8 flex justify-center text-text-muted">
              <Loader2 size={20} className="animate-spin" />
            </div>
          ) : records.length === 0 ? (
            <div className="p-8 text-sm text-text-muted">No quarantined leads pending review.</div>
          ) : (
            <ul className="divide-y divide-border-subtle max-h-[560px] overflow-y-auto">
              {records.map((record: QuarantineRecord) => (
                <li key={record.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(record.id)}
                    className={`w-full text-left px-4 py-3 hover:bg-surface-bg ${
                      selected?.id === record.id ? 'bg-surface-bg/80' : ''
                    }`}
                  >
                    <div className="font-medium text-sm text-text-main truncate">
                      {String(record.normalized_payload.full_name || record.meta_leadgen_id)}
                    </div>
                    <div className="text-xs text-text-muted mt-1 truncate">{record.error_reason}</div>
                    <div className="text-[11px] text-text-muted mt-1">
                      {record.sync_mode} · {record.source} · {formatTimestamp(record.created_at)}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="flex items-center justify-between px-4 py-3 border-t border-border-subtle text-sm">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage(current => Math.max(1, current - 1))}
              className="inline-flex items-center gap-1 disabled:opacity-50"
            >
              <ChevronLeft size={16} />
              Prev
            </button>
            <span className="text-text-muted tabular-nums">
              Page {page} of {totalPages}
            </span>
            <button
              type="button"
              disabled={page >= totalPages}
              onClick={() => setPage(current => Math.min(totalPages, current + 1))}
              className="inline-flex items-center gap-1 disabled:opacity-50"
            >
              Next
              <ChevronRight size={16} />
            </button>
          </div>
        </div>

        <div className="xl:col-span-2 rounded-2xl border border-border-subtle bg-card p-5 space-y-4">
          {!selected ? (
            <div className="text-sm text-text-muted">Select a quarantined lead to inspect and reprocess.</div>
          ) : (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                <div>
                  <span className="text-text-muted">Leadgen ID</span>
                  <div className="font-mono text-xs mt-1">{selected.meta_leadgen_id}</div>
                </div>
                <div>
                  <span className="text-text-muted">Error</span>
                  <div className="mt-1">{selected.error_reason}</div>
                </div>
                <div>
                  <span className="text-text-muted">Sync mode</span>
                  <div className="mt-1">{selected.sync_mode}</div>
                </div>
                <div>
                  <span className="text-text-muted">Triggered by</span>
                  <div className="mt-1">{selected.triggered_by_user}</div>
                </div>
                <div>
                  <span className="text-text-muted">Source</span>
                  <div className="mt-1">{selected.source}</div>
                </div>
                <div>
                  <span className="text-text-muted">Received</span>
                  <div className="mt-1">{formatTimestamp(selected.created_at)}</div>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-text-main mb-2">
                  Edit normalized payload (JSON)
                </label>
                <textarea
                  value={editorValue}
                  onChange={event => setEditorValue(event.target.value)}
                  rows={16}
                  className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 font-mono text-xs text-text-main focus:outline-none focus:border-accent"
                />
              </div>

              <div className="flex flex-wrap gap-3">
                <button
                  type="button"
                  onClick={() => void handleReprocess()}
                  disabled={reprocessRecord.isPending}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-accent text-text-dark-bg text-sm font-semibold hover:opacity-90 disabled:opacity-50"
                >
                  {reprocessRecord.isPending ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <Wrench size={16} />
                  )}
                  Edit &amp; Reprocess
                </button>
                <button
                  type="button"
                  onClick={() => void handleDelete()}
                  disabled={deleteRecord.isPending}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-red-200 text-red-700 text-sm font-semibold hover:bg-red-50 disabled:opacity-50"
                >
                  {deleteRecord.isPending ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <Trash2 size={16} />
                  )}
                  Delete
                </button>
                <button
                  type="button"
                  onClick={() =>
                    setEditorValue(JSON.stringify(selected.original_payload ?? {}, null, 2))
                  }
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-border-subtle text-sm font-semibold hover:bg-surface-bg"
                >
                  <Save size={16} />
                  Reset to original
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default QuarantineDashboard;
