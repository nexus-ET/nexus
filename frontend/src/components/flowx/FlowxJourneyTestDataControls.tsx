import { useEffect, useState } from 'react';
import { Database, RotateCcw } from 'lucide-react';
import { useConfirmation } from '../../context/ConfirmationContext';
import { useFlowxJourneyTestReset, useFlowxJourneyTestSeed } from '../../hooks/useFlowx';

const DEFAULT_LEAD = 27;

interface FlowxJourneyTestDataControlsProps {
  /** Prefill lead id (e.g. on student hub). Editable unless locked. */
  leadId?: number;
  lockLeadId?: boolean;
  className?: string;
}

/**
 * Admin control to seed / wipe US·CA·GB demo applications for a lead.
 */
const FlowxJourneyTestDataControls: React.FC<FlowxJourneyTestDataControlsProps> = ({
  leadId: presetLead,
  lockLeadId = false,
  className = '',
}) => {
  const [leadId, setLeadId] = useState(String(presetLead ?? DEFAULT_LEAD));
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (presetLead != null) setLeadId(String(presetLead));
  }, [presetLead]);

  const openConfirm = useConfirmation();
  const seedMutation = useFlowxJourneyTestSeed();
  const resetMutation = useFlowxJourneyTestReset();
  const busy = seedMutation.isPending || resetMutation.isPending;
  const resolvedLead = Number(leadId);

  const runSeed = async () => {
    setMessage(null);
    setError(null);
    if (!Number.isFinite(resolvedLead) || resolvedLead <= 0) {
      setError('Enter a valid lead ID');
      return;
    }
    const ok = await openConfirm({
      title: 'Seed demo applications?',
      message: `Seed 6 demo applications (US / CA / GB) for lead #${resolvedLead}?\n\nExisting applications for this lead will be replaced.`,
      confirmLabel: 'Seed',
      variant: 'warning',
    });
    if (!ok) return;
    try {
      const data = await seedMutation.mutateAsync(resolvedLead);
      setMessage(`Seeded ${data.total} applications for lead #${data.lead_id}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Seed failed');
    }
  };

  const runReset = async () => {
    setMessage(null);
    setError(null);
    if (!Number.isFinite(resolvedLead) || resolvedLead <= 0) {
      setError('Enter a valid lead ID');
      return;
    }
    const ok = await openConfirm({
      title: 'Reset demo data?',
      message: `Reset demo data for lead #${resolvedLead}?\n\nDeletes this lead’s FlowX applications and FXTEST academia institutions.`,
      confirmLabel: 'Reset',
      variant: 'danger',
    });
    if (!ok) return;
    try {
      const data = await resetMutation.mutateAsync(resolvedLead);
      setMessage(
        `Reset complete — removed ${data.enrollments_deleted} application(s) and ${data.academia?.institutions ?? 0} test institution(s).`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reset failed');
    }
  };

  return (
    <div
      className={`rounded-xl border border-dashed border-border-subtle bg-surface-bg/50 px-3 py-2 ${className}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">
          Journey test data
        </span>
        <input
          type="number"
          min={1}
          value={leadId}
          disabled={lockLeadId || busy}
          onChange={e => setLeadId(e.target.value)}
          className="w-20 rounded-md border border-border-subtle bg-card px-2 py-1 text-xs disabled:opacity-60"
          title="Lead ID"
          aria-label="Lead ID for test data"
        />
        <button
          type="button"
          disabled={busy}
          onClick={() => void runSeed()}
          className="inline-flex items-center gap-1 rounded-lg border border-accent/30 bg-accent/10 px-2.5 py-1 text-xs font-semibold text-text-main hover:bg-accent/20 disabled:opacity-50"
        >
          <Database size={12} />
          {seedMutation.isPending ? 'Seeding…' : 'Add demo data'}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void runReset()}
          className="inline-flex items-center gap-1 rounded-lg border border-border-subtle bg-card px-2.5 py-1 text-xs font-semibold text-text-muted hover:text-text-main disabled:opacity-50"
        >
          <RotateCcw size={12} />
          {resetMutation.isPending ? 'Resetting…' : 'Reset demo data'}
        </button>
      </div>
      {message ? <p className="mt-1 text-[11px] text-emerald-700">{message}</p> : null}
      {error ? <p className="mt-1 text-[11px] text-red-700">{error}</p> : null}
    </div>
  );
};

export default FlowxJourneyTestDataControls;
