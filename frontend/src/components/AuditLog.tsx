import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
  Eye,
  Loader2,
  Search,
  X,
} from 'lucide-react';
import { apiFetch } from '../utils/api';
import { useDebouncedValue } from '../hooks/useDebouncedValue';

export type AuditStatusFilter = 'all' | 'escalated' | 'ai_active';
export type AuditSortField = 'created_at' | 'confidence_score';
export type AuditSortOrder = 'asc' | 'desc';

export interface ConversationAuditItem {
  id: number;
  lead_id: number;
  student_message: string;
  ai_reply: string;
  ai_model: string;
  confidence_score: number | null;
  escalated: boolean;
  created_at: string;
}

export interface ConversationAuditCandidate {
  lead_id: number;
  student_name: string | null;
  turn_count: number;
  latest_student_message: string;
  latest_ai_reply: string;
  latest_ai_model: string;
  latest_confidence_score: number | null;
  latest_escalated: boolean;
  has_escalated: boolean;
  last_activity_at: string;
}

interface ConversationAuditCandidateResponse {
  items: ConversationAuditCandidate[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

interface ConversationAuditTurnsResponse {
  items: ConversationAuditItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

const PAGE_SIZE = 20;

function confidenceBadgeClass(score: number | null): string {
  if (score === null || Number.isNaN(score)) {
    return 'bg-surface-bg text-text-muted border-border-subtle';
  }
  if (score >= 0.8) {
    return 'bg-emerald-500/15 text-emerald-700 border-emerald-500/30';
  }
  if (score >= 0.6) {
    return 'bg-amber-500/15 text-amber-800 border-amber-500/30';
  }
  return 'bg-red-500/15 text-red-700 border-red-500/30';
}

function formatConfidence(score: number | null): string {
  if (score === null || Number.isNaN(score)) return '—';
  return `${Math.round(score * 100)}%`;
}

function formatTimestamp(value: string): string {
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function SortHeader({
  label,
  field,
  activeField,
  order,
  onSort,
}: {
  label: string;
  field: AuditSortField;
  activeField: AuditSortField;
  order: AuditSortOrder;
  onSort: (field: AuditSortField) => void;
}) {
  const isActive = activeField === field;
  const Icon = !isActive ? ArrowUpDown : order === 'asc' ? ArrowUp : ArrowDown;

  return (
    <button
      type="button"
      onClick={() => onSort(field)}
      className="inline-flex items-center gap-1 text-[10px] font-black uppercase tracking-widest text-text-muted hover:text-text-main"
    >
      {label}
      <Icon size={12} className={isActive ? 'text-accent' : 'opacity-50'} />
    </button>
  );
}

interface AuditConversationModalProps {
  candidate: ConversationAuditCandidate;
  onClose: () => void;
}

const AuditConversationModal: React.FC<AuditConversationModalProps> = ({ candidate, onClose }) => {
  const [turns, setTurns] = useState<ConversationAuditItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);

    apiFetch(`audit/conversations/candidates/${candidate.lead_id}/turns?page_size=200`)
      .then(response => {
        if (!active) return;
        const payload = response as ConversationAuditTurnsResponse;
        setTurns(payload.items ?? []);
      })
      .catch(err => {
        if (!active) return;
        setError(err instanceof Error ? err.message : 'Failed to load conversation turns.');
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [candidate.lead_id]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  const displayName = candidate.student_name?.trim() || `Lead #${candidate.lead_id}`;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="bg-card border border-border-subtle rounded-2xl shadow-xl w-full max-w-5xl max-h-[90vh] flex flex-col"
        role="dialog"
        aria-modal="true"
        aria-labelledby="audit-conversation-title"
        onClick={event => event.stopPropagation()}
      >
        <div className="px-6 py-4 border-b border-border-subtle flex items-start justify-between gap-4">
          <div>
            <h3 id="audit-conversation-title" className="text-lg font-bold text-text-main">
              {displayName}
            </h3>
            <p className="text-xs text-text-muted mt-1">
              Lead #{candidate.lead_id} · {candidate.turn_count} AI turn{candidate.turn_count === 1 ? '' : 's'}
              {candidate.has_escalated ? ' · includes escalated turns' : ''}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-lg border border-border-subtle text-text-muted hover:text-text-main hover:bg-surface-bg"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto custom-scrollbar px-6 py-4 space-y-4">
          {loading ? (
            <div className="py-16 text-center text-sm text-text-muted inline-flex items-center gap-2 justify-center w-full">
              <Loader2 size={16} className="animate-spin" />
              Loading conversation...
            </div>
          ) : error ? (
            <div className="p-3 bg-alert/10 border border-alert/20 rounded-xl text-xs text-alert">{error}</div>
          ) : turns.length === 0 ? (
            <p className="text-sm text-text-muted text-center py-12">No audit turns recorded for this candidate.</p>
          ) : (
            turns.map((turn, index) => (
              <div key={turn.id} className="border border-border-subtle rounded-xl overflow-hidden">
                <div className="px-4 py-2 bg-surface-bg/40 border-b border-border-subtle flex flex-wrap items-center justify-between gap-2">
                  <span className="text-[11px] font-bold text-text-main">Turn {index + 1}</span>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-[10px] text-text-muted">{formatTimestamp(turn.created_at)}</span>
                    <span className="text-[10px] text-text-muted">{turn.ai_model || '—'}</span>
                    <span
                      className={`inline-flex items-center px-2 py-0.5 rounded-full border text-[10px] font-semibold ${confidenceBadgeClass(turn.confidence_score)}`}
                    >
                      {formatConfidence(turn.confidence_score)}
                    </span>
                    <span
                      className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                        turn.escalated
                          ? 'bg-red-500/10 text-red-700 border border-red-500/20'
                          : 'bg-emerald-500/10 text-emerald-700 border border-emerald-500/20'
                      }`}
                    >
                      {turn.escalated ? 'Escalated' : 'AI Active'}
                    </span>
                  </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-border-subtle">
                  <div className="p-4">
                    <p className="text-[10px] font-black uppercase tracking-widest text-text-muted mb-2">
                      Student asked
                    </p>
                    <p className="text-sm text-text-main leading-relaxed whitespace-pre-wrap">
                      {turn.student_message || '—'}
                    </p>
                  </div>
                  <div className="p-4 bg-surface-bg/20">
                    <p className="text-[10px] font-black uppercase tracking-widest text-text-muted mb-2">
                      AI replied
                    </p>
                    <p className="text-sm text-text-main leading-relaxed whitespace-pre-wrap">
                      {turn.ai_reply || '—'}
                    </p>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};

const AuditLog: React.FC = () => {
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState<AuditStatusFilter>('all');
  const [modelFilter, setModelFilter] = useState('all');
  const [sortBy, setSortBy] = useState<AuditSortField>('created_at');
  const [order, setOrder] = useState<AuditSortOrder>('desc');
  const [page, setPage] = useState(1);
  const [models, setModels] = useState<string[]>([]);
  const [data, setData] = useState<ConversationAuditCandidateResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedCandidate, setSelectedCandidate] = useState<ConversationAuditCandidate | null>(null);

  const debouncedSearch = useDebouncedValue(search, 350);

  const queryString = useMemo(() => {
    const params = new URLSearchParams();
    params.set('page', String(page));
    params.set('page_size', String(PAGE_SIZE));
    if (debouncedSearch.trim()) params.set('search', debouncedSearch.trim());
    if (status !== 'all') params.set('status', status);
    if (modelFilter !== 'all') params.set('model', modelFilter);
    params.set('sort_by', sortBy);
    params.set('order', order);
    return params.toString();
  }, [page, debouncedSearch, status, modelFilter, sortBy, order]);

  const loadModels = useCallback(async () => {
    try {
      const response = (await apiFetch('audit/conversations/models')) as { models?: string[] };
      setModels(Array.isArray(response.models) ? response.models : []);
    } catch {
      setModels([]);
    }
  }, []);

  const loadAudits = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const response = (await apiFetch(`audit/conversations/candidates?${queryString}`)) as ConversationAuditCandidateResponse;
      setData(response);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load conversation audit logs.');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [queryString]);

  useEffect(() => {
    loadModels();
  }, [loadModels]);

  useEffect(() => {
    loadAudits();
  }, [loadAudits]);

  useEffect(() => {
    setPage(1);
  }, [debouncedSearch, status, modelFilter, sortBy, order]);

  const handleSort = (field: AuditSortField) => {
    if (sortBy === field) {
      setOrder(prev => (prev === 'asc' ? 'desc' : 'asc'));
      return;
    }
    setSortBy(field);
    setOrder('desc');
  };

  const totalPages = data?.total_pages ?? 1;
  const currentPage = data?.page ?? page;

  const pageNumbers = useMemo(() => {
    const pages: number[] = [];
    const start = Math.max(1, currentPage - 2);
    const end = Math.min(totalPages, currentPage + 2);
    for (let i = start; i <= end; i += 1) pages.push(i);
    return pages;
  }, [currentPage, totalPages]);

  return (
    <>
      <div className="bg-card border border-border-subtle rounded-2xl shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-border-subtle bg-surface-bg/30 space-y-4">
          <div>
            <h3 className="text-sm font-bold text-text-main">Audit Dashboard</h3>
            <p className="text-[11px] text-text-muted mt-1">
              One row per candidate — open a conversation to review every question and AI reply side by side.
            </p>
          </div>

          <div className="flex flex-col lg:flex-row gap-3">
            <label className="relative flex-1">
              <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
              <input
                type="search"
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search candidate name, student message, or AI reply..."
                className="w-full pl-9 pr-3 py-2 bg-surface-bg border border-border-subtle rounded-xl text-sm text-text-main focus:outline-none focus:border-accent focus:ring-4 focus:ring-accent/10"
              />
            </label>

            <select
              value={status}
              onChange={e => setStatus(e.target.value as AuditStatusFilter)}
              className="px-3 py-2 bg-surface-bg border border-border-subtle rounded-xl text-sm text-text-main focus:outline-none focus:border-accent"
            >
              <option value="all">All statuses</option>
              <option value="escalated">Escalated</option>
              <option value="ai_active">AI Active</option>
            </select>

            <select
              value={modelFilter}
              onChange={e => setModelFilter(e.target.value)}
              className="px-3 py-2 bg-surface-bg border border-border-subtle rounded-xl text-sm text-text-main focus:outline-none focus:border-accent min-w-[180px]"
            >
              <option value="all">All models</option>
              {models.map(model => (
                <option key={model} value={model}>
                  {model}
                </option>
              ))}
            </select>
          </div>
        </div>

        {error && (
          <div className="mx-6 mt-4 p-3 bg-alert/10 border border-alert/20 rounded-xl text-xs text-alert">
            {error}
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-border-subtle bg-surface-bg/20">
                <th className="px-6 py-3 text-[10px] font-black uppercase tracking-widest text-text-muted">
                  Candidate
                </th>
                <th className="px-6 py-3">
                  <SortHeader
                    label="Last activity"
                    field="created_at"
                    activeField={sortBy}
                    order={order}
                    onSort={handleSort}
                  />
                </th>
                <th className="px-6 py-3 text-[10px] font-black uppercase tracking-widest text-text-muted">
                  Latest question
                </th>
                <th className="px-6 py-3 text-[10px] font-black uppercase tracking-widest text-text-muted">
                  Turns
                </th>
                <th className="px-6 py-3 text-[10px] font-black uppercase tracking-widest text-text-muted">
                  Model
                </th>
                <th className="px-6 py-3">
                  <SortHeader
                    label="Confidence"
                    field="confidence_score"
                    activeField={sortBy}
                    order={order}
                    onSort={handleSort}
                  />
                </th>
                <th className="px-6 py-3 text-[10px] font-black uppercase tracking-widest text-text-muted">
                  Status
                </th>
                <th className="px-6 py-3 text-[10px] font-black uppercase tracking-widest text-text-muted">
                  Action
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle/50">
              {loading ? (
                <tr>
                  <td colSpan={8} className="px-6 py-16 text-center text-sm text-text-muted">
                    <span className="inline-flex items-center gap-2">
                      <Loader2 size={16} className="animate-spin" />
                      Loading audit logs...
                    </span>
                  </td>
                </tr>
              ) : !data?.items.length ? (
                <tr>
                  <td colSpan={8} className="px-6 py-16 text-center text-sm text-text-muted">
                    No conversation audit records found.
                  </td>
                </tr>
              ) : (
                data.items.map(item => (
                  <tr key={item.lead_id} className="hover:bg-surface-bg/30 align-top">
                    <td className="px-6 py-4">
                      <p className="text-sm font-bold text-text-main">
                        {item.student_name?.trim() || `Lead #${item.lead_id}`}
                      </p>
                      <p className="text-[10px] text-text-muted mt-0.5">Lead #{item.lead_id}</p>
                    </td>
                    <td className="px-6 py-4 text-xs text-text-muted whitespace-nowrap">
                      {formatTimestamp(item.last_activity_at)}
                    </td>
                    <td className="px-6 py-4 text-sm text-text-main max-w-xs">
                      <p className="line-clamp-2">{item.latest_student_message || '—'}</p>
                    </td>
                    <td className="px-6 py-4 text-sm font-semibold text-text-main">{item.turn_count}</td>
                    <td className="px-6 py-4 text-xs text-text-muted whitespace-nowrap">
                      {item.latest_ai_model || '—'}
                    </td>
                    <td className="px-6 py-4">
                      <span
                        className={`inline-flex items-center px-2 py-1 rounded-full border text-[11px] font-semibold ${confidenceBadgeClass(item.latest_confidence_score)}`}
                      >
                        {formatConfidence(item.latest_confidence_score)}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <span
                        className={`inline-flex items-center px-2 py-1 rounded-full text-[11px] font-semibold ${
                          item.has_escalated
                            ? 'bg-red-500/10 text-red-700 border border-red-500/20'
                            : 'bg-emerald-500/10 text-emerald-700 border border-emerald-500/20'
                        }`}
                      >
                        {item.has_escalated ? 'Escalated' : 'AI Active'}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <button
                        type="button"
                        onClick={() => setSelectedCandidate(item)}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border-subtle text-[11px] font-bold text-text-main hover:bg-surface-bg transition-colors"
                      >
                        <Eye size={14} />
                        View
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <div className="px-6 py-4 border-t border-border-subtle bg-surface-bg/20 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <p className="text-xs text-text-muted">
            {data ? `${data.total} candidate${data.total === 1 ? '' : 's'}` : '—'} · Page {currentPage} of {totalPages}
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setPage(prev => Math.max(1, prev - 1))}
              disabled={currentPage <= 1 || loading}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-border-subtle text-xs font-semibold text-text-muted hover:text-text-main disabled:opacity-40"
            >
              <ChevronLeft size={14} />
              Previous
            </button>
            {pageNumbers.map(pageNumber => (
              <button
                key={pageNumber}
                type="button"
                onClick={() => setPage(pageNumber)}
                disabled={loading}
                className={`min-w-8 px-2 py-1.5 rounded-lg text-xs font-semibold border ${
                  pageNumber === currentPage
                    ? 'bg-accent text-text-dark-bg border-accent'
                    : 'border-border-subtle text-text-muted hover:text-text-main'
                }`}
              >
                {pageNumber}
              </button>
            ))}
            <button
              type="button"
              onClick={() => setPage(prev => Math.min(totalPages, prev + 1))}
              disabled={currentPage >= totalPages || loading}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-border-subtle text-xs font-semibold text-text-muted hover:text-text-main disabled:opacity-40"
            >
              Next
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      </div>

      {selectedCandidate && (
        <AuditConversationModal candidate={selectedCandidate} onClose={() => setSelectedCandidate(null)} />
      )}
    </>
  );
};

export default AuditLog;
