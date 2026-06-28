import { Link } from 'react-router-dom';
import { ArrowUpRight, HelpCircle } from 'lucide-react';

export interface PendingAdvisorQuestion {
  audit_id: number;
  lead_id: number;
  student_name: string;
  question: string;
  ai_reply?: string;
  ai_model?: string;
  confidence_score?: number | null;
  escalated: boolean;
  created_at?: string | null;
  link_path?: string;
}

interface PendingAdvisorQuestionsPanelProps {
  items: PendingAdvisorQuestion[];
  loading: boolean;
  formatDateTime: (value: string, options?: Intl.DateTimeFormatOptions) => string;
}

function confidenceLabel(score: number | null | undefined): string {
  if (score === null || score === undefined || Number.isNaN(score)) return '—';
  return `${Math.round(score * 100)}%`;
}

const PendingAdvisorQuestionsPanel: React.FC<PendingAdvisorQuestionsPanelProps> = ({
  items,
  loading,
  formatDateTime,
}) => {
  return (
    <div className="bg-card border border-border-subtle rounded-2xl shadow-sm overflow-hidden">
      <div className="px-6 py-4 border-b border-border-subtle bg-surface-bg/30 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <HelpCircle size={18} className="text-accent" />
          <div>
            <h4 className="text-sm font-bold text-text-main">Questions for Admissions Officers</h4>
            <p className="text-[11px] text-text-muted mt-0.5">
              Escalated by AI when confidence was too low or the question needs a human specialist.
            </p>
          </div>
        </div>
        <Link
          to="/handoffs"
          className="inline-flex items-center gap-1 text-[11px] font-semibold text-accent hover:opacity-80"
        >
          Open Handoffs
          <ArrowUpRight size={14} />
        </Link>
      </div>

      <div className="divide-y divide-border-subtle/50 max-h-[420px] overflow-y-auto custom-scrollbar">
        {loading && items.length === 0 ? (
          <div className="px-6 py-10 text-center text-xs text-text-muted italic">Loading pending questions...</div>
        ) : items.length === 0 ? (
          <div className="px-6 py-10 text-center text-xs text-text-muted">
            No escalated questions waiting for an admissions officer right now.
          </div>
        ) : (
          items.map(item => (
            <div key={item.audit_id} className="px-6 py-4 hover:bg-surface-bg/30 transition-colors">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm font-bold text-text-main">{item.student_name || `Lead #${item.lead_id}`}</p>
                    <span className="text-[10px] font-semibold text-text-muted">Lead #{item.lead_id}</span>
                    {item.confidence_score !== null && item.confidence_score !== undefined && (
                      <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-800 border border-amber-500/20">
                        AI confidence {confidenceLabel(item.confidence_score)}
                      </span>
                    )}
                  </div>
                  <p className="mt-2 text-sm text-text-main leading-relaxed">{item.question || '—'}</p>
                  {item.created_at && (
                    <p className="mt-2 text-[10px] text-text-muted">
                      Escalated {formatDateTime(item.created_at, { hour: '2-digit', minute: '2-digit', month: 'short', day: 'numeric' })}
                    </p>
                  )}
                </div>
                <Link
                  to={item.link_path || '/handoffs'}
                  className="shrink-0 inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-border-subtle text-[10px] font-bold text-text-main hover:bg-surface-bg transition-colors"
                >
                  Answer
                  <ArrowUpRight size={12} />
                </Link>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default PendingAdvisorQuestionsPanel;
