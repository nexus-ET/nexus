import { Loader2, X } from 'lucide-react';

interface InlineExpandPanelProps {
  title: string;
  subtitle?: string;
  onClose: () => void;
  loading?: boolean;
  loadingLabel?: string;
  error?: string | null;
  success?: string | null;
  children: React.ReactNode;
  footer?: React.ReactNode;
}

const InlineExpandPanel: React.FC<InlineExpandPanelProps> = ({
  title,
  subtitle,
  onClose,
  loading = false,
  loadingLabel = 'Loading details...',
  error,
  success,
  children,
  footer,
}) => (
  <div className="rounded-xl border border-accent/20 bg-surface-bg/60 p-4 shadow-inner">
    <div className="mb-4 flex items-start justify-between gap-3">
      <div>
        {subtitle ? (
          <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">{subtitle}</p>
        ) : null}
        <h4 className="text-base font-bold text-text-main">{title}</h4>
      </div>
      <button
        type="button"
        onClick={onClose}
        className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-text-muted hover:bg-card"
        aria-label="Close panel"
      >
        <X size={14} />
        Close
      </button>
    </div>

    {error ? <p className="mb-3 text-sm text-alert">{error}</p> : null}
    {success ? <p className="mb-3 text-sm font-semibold text-emerald-700">{success}</p> : null}

    {loading ? (
      <div className="flex items-center gap-2 py-8 text-sm text-text-muted">
        <Loader2 size={16} className="animate-spin" />
        {loadingLabel}
      </div>
    ) : (
      <>
        <div className="space-y-4">{children}</div>
        {footer ? <div className="mt-4 border-t border-border-subtle pt-4">{footer}</div> : null}
      </>
    )}
  </div>
);

export default InlineExpandPanel;
