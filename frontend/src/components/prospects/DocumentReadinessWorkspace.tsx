import { FileStack } from 'lucide-react';
import ScanxDocumentPanel from './ScanxDocumentPanel';

type Props = {
  code: string;
  title: string;
  leadId: number | null;
  candidateName?: string | null;
  reviewOpen?: boolean;
  onReviewOpenChange?: (open: boolean) => void;
  onBindCloseReview?: (close: (() => void) | null) => void;
};

/** Document Readiness workspace hosting ScanX upload + split-view shell. */
export default function DocumentReadinessWorkspace({
  code,
  title,
  leadId,
  candidateName,
  reviewOpen = false,
  onReviewOpenChange,
  onBindCloseReview,
}: Props) {
  return (
    <section
      className={`rounded-xl border border-border-subtle bg-card shadow-[0_1px_0_rgba(50,47,134,0.04)] ${
        reviewOpen ? 'flex h-full min-h-0 flex-1 flex-col overflow-hidden' : ''
      }`}
    >
      <div className="flex shrink-0 flex-wrap items-end justify-between gap-3 border-b border-border-subtle bg-gradient-to-r from-accent/[0.06] via-surface-bg to-surface-bg px-4 py-3">
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-accent/70">
            Sub-Process {code}
          </p>
          <h3 className="mt-0.5 flex items-center gap-2 text-sm font-semibold text-text-main">
            <span className="inline-flex h-6 w-6 items-center justify-center rounded-md bg-accent/10 text-accent">
              <FileStack size={14} />
            </span>
            {title || 'Document Readiness'}
            <span className="rounded-md border border-border-subtle bg-surface-bg px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-accent">
              ScanX
            </span>
          </h3>
        </div>
      </div>
      <div
        className={
          reviewOpen
            ? 'flex min-h-0 flex-1 flex-col overflow-hidden p-3'
            : 'space-y-4 overflow-visible p-4'
        }
      >
        <ScanxDocumentPanel
          leadId={leadId}
          candidateName={candidateName}
          onReviewOpenChange={onReviewOpenChange}
          onBindCloseReview={onBindCloseReview}
        />
      </div>
    </section>
  );
}
