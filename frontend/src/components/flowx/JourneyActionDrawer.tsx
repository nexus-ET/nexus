import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { CheckCircle2, Clock3, Loader2, X } from 'lucide-react';
import {
  FLOWX_KANBAN_COLUMNS,
  slaChipClass,
  slaLabel,
  type FlowxIntakeBooking,
  type FlowxKanbanStatus,
  type FlowxTask,
} from '../../types/flowx';
import { lifecycleLabel } from '../../utils/flowxHierarchy';
import {
  intakeDelayDisplay,
  intakeSessionStateFromBooking,
  isIntakeSessionTask,
} from '../../utils/flowxIntakeSession';
import { subprocessSteps } from '../../utils/flowxSubprocessSteps';

type JourneyActionDrawerProps = {
  open: boolean;
  task: FlowxTask | null;
  code?: string | null;
  processLabel?: string;
  subProcessLabel?: string;
  bookingStatusLabel?: string | null;
  intakeBooking?: FlowxIntakeBooking | null;
  pending?: boolean;
  checklistSaving?: boolean;
  onClose: () => void;
  onAdvance: (status: FlowxKanbanStatus) => void;
  onViewIntakeSession?: () => void;
  /** Persist checklist ticks / confirmation to flowx_tasks.checklist_state. */
  onChecklistChange?: (payload: {
    checked: boolean[];
    confirmed_complete: boolean;
    steps: string[];
  }) => void | Promise<void>;
};

function formatDue(iso?: string | null) {
  if (!iso) return 'No due date';
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function checkedMapFromTask(
  task: FlowxTask,
  steps: string[]
): { checked: Record<number, boolean>; confirmedComplete: boolean } {
  const saved = task.checklist_state;
  const savedChecked = Array.isArray(saved?.checked) ? saved.checked : [];
  const map: Record<number, boolean> = {};
  steps.forEach((_, idx) => {
    map[idx] = Boolean(savedChecked[idx]);
  });
  const allDone = steps.length > 0 && steps.every((_, idx) => map[idx]);
  const confirmedComplete =
    Boolean(saved?.confirmed_complete) && allDone
      ? true
      : task.kanban_status === 'approved';
  return { checked: map, confirmedComplete };
}

export default function JourneyActionDrawer({
  open,
  task,
  code,
  processLabel,
  subProcessLabel,
  bookingStatusLabel,
  intakeBooking,
  pending,
  checklistSaving,
  onClose,
  onAdvance,
  onViewIntakeSession,
  onChecklistChange,
}: JourneyActionDrawerProps) {
  const steps = useMemo(
    () => (task ? subprocessSteps(task.title, task.action_steps) : []),
    [task]
  );

  const [checked, setChecked] = useState<Record<number, boolean>>({});
  const [confirmedComplete, setConfirmedComplete] = useState(false);
  const hydrateKeyRef = useRef<string | null>(null);

  useEffect(() => {
    if (!open || !task) return;
    const key = `${task.id}:${task.updated_at || ''}:${steps.join('|')}`;
    // Re-hydrate when opening a different task, or when server state arrives for this task.
    if (hydrateKeyRef.current === key) return;
    hydrateKeyRef.current = key;
    const hydrated = checkedMapFromTask(task, steps);
    setChecked(hydrated.checked);
    setConfirmedComplete(hydrated.confirmedComplete);
  }, [open, task, steps]);

  useEffect(() => {
    if (!open) {
      hydrateKeyRef.current = null;
      return;
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [open, onClose]);

  const nextStatuses = useMemo(() => {
    if (!task) return [] as FlowxKanbanStatus[];
    const order: FlowxKanbanStatus[] = [
      'todo',
      'in_progress',
      'in_review',
      'approved',
      'blocked',
    ];
    return order.filter(s => s !== task.kanban_status);
  }, [task]);

  const allChecked = steps.length > 0 && steps.every((_, idx) => Boolean(checked[idx]));
  const checkedCount = steps.filter((_, idx) => checked[idx]).length;

  const persist = (
    nextChecked: Record<number, boolean>,
    nextConfirmed: boolean
  ) => {
    if (!onChecklistChange || !task) return;
    const checkedList = steps.map((_, idx) => Boolean(nextChecked[idx]));
    void onChecklistChange({
      checked: checkedList,
      confirmed_complete: nextConfirmed && checkedList.every(Boolean),
      steps,
    });
  };

  const toggleStep = (idx: number) => {
    setChecked(prev => {
      const next = { ...prev, [idx]: !prev[idx] };
      const stillAll = steps.every((_, i) => Boolean(next[i]));
      const nextConfirmed = stillAll ? confirmedComplete : false;
      if (!stillAll) setConfirmedComplete(false);
      persist(next, nextConfirmed);
      return next;
    });
  };

  const checkAll = () => {
    const next: Record<number, boolean> = {};
    steps.forEach((_, idx) => {
      next[idx] = true;
    });
    setChecked(next);
    persist(next, confirmedComplete);
  };

  const setConfirmation = (value: boolean) => {
    if (value && !allChecked) return;
    setConfirmedComplete(value);
    persist(checked, value);
  };

  if (!open || !task || typeof document === 'undefined') return null;

  const isIntakeSession = isIntakeSessionTask(task);
  const intakeState = isIntakeSession
    ? intakeSessionStateFromBooking(intakeBooking, task)
    : null;
  const delayDisplay = isIntakeSession ? intakeDelayDisplay(intakeBooking, task) : null;
  const statusLabel = intakeState
    ? `${lifecycleLabel(intakeState.lifecycle)} · ${intakeState.progress}%`
    : FLOWX_KANBAN_COLUMNS.find(c => c.key === task.kanban_status)?.label || task.kanban_status;

  const canConfirm = allChecked && !confirmedComplete;
  const canApprove =
    !isIntakeSession &&
    task.kanban_status !== 'approved' &&
    confirmedComplete;

  return createPortal(
    <div
      className="fixed inset-0 z-[280] flex justify-end bg-black/40"
      onMouseDown={onClose}
      role="presentation"
    >
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="Task action drawer"
        className="flex h-dvh max-h-dvh w-full max-w-md flex-col overflow-hidden border-l border-border-subtle bg-card shadow-2xl"
        onMouseDown={e => e.stopPropagation()}
      >
        <div className="flex shrink-0 items-start justify-between gap-3 border-b border-border-subtle bg-surface-bg px-4 py-3">
          <div className="min-w-0">
            <p className="text-[10px] font-bold uppercase tracking-wide text-text-muted">
              Action drawer · Tier 4
            </p>
            {code ? (
              <p className="mt-0.5 text-xs font-bold tabular-nums text-text-muted">{code}</p>
            ) : null}
            <h3 className="text-lg font-bold leading-snug text-text-main">{task.title}</h3>
            <p className="mt-0.5 text-xs text-text-muted">
              {[processLabel, subProcessLabel].filter(Boolean).join(' · ')}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-border-subtle p-1.5 text-text-muted hover:bg-card hover:text-text-main"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 pt-4 pb-28 custom-scrollbar">
          <div className="space-y-4">
            <div className="flex flex-wrap gap-2">
              <span className="rounded-md border border-border-subtle bg-surface-bg px-2 py-0.5 text-xs font-semibold text-text-main">
                {statusLabel}
              </span>
              {delayDisplay ? (
                <span className="rounded-md border border-red-300 bg-red-50 px-2 py-0.5 text-xs font-semibold text-red-800">
                  {delayDisplay}
                </span>
              ) : null}
              <span
                className={`rounded-md border px-2 py-0.5 text-xs font-semibold ${slaChipClass(
                  task.sla_status
                )}`}
              >
                {intakeState?.lifecycle === 'delayed' || task.sla_status === 'breached'
                  ? 'Delayed'
                  : slaLabel(task.sla_status)}
              </span>
              {task.is_optional ? (
                <span className="rounded-md border border-amber-300 bg-amber-50 px-2 py-0.5 text-xs font-semibold text-amber-900">
                  Optional
                </span>
              ) : (
                <span className="rounded-md border border-border-subtle bg-surface-bg px-2 py-0.5 text-xs font-semibold text-text-muted">
                  Required
                </span>
              )}
              {checklistSaving ? (
                <span className="inline-flex items-center gap-1 rounded-md border border-border-subtle bg-surface-bg px-2 py-0.5 text-[10px] font-semibold text-text-muted">
                  <Loader2 size={11} className="animate-spin" /> Saving…
                </span>
              ) : null}
            </div>

            <div className="rounded-xl border border-border-subtle bg-surface-bg/70 px-3 py-2.5">
              <p className="inline-flex items-center gap-1.5 text-xs font-semibold text-text-muted">
                <Clock3 size={13} /> SLA due
              </p>
              <p className="mt-0.5 text-sm font-semibold text-text-main">
                {formatDue(task.sla_due_at)}
              </p>
            </div>

            {task.description ? (
              <div>
                <p className="text-xs font-bold uppercase tracking-wide text-text-muted">Notes</p>
                <p className="mt-1 text-sm leading-6 text-text-main">{task.description}</p>
              </div>
            ) : null}

            <div>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="text-xs font-bold uppercase tracking-wide text-text-muted">
                    Activity checklist
                  </p>
                  <p className="mt-0.5 text-[11px] text-text-muted">
                    Check each step — progress is saved automatically
                    {steps.length > 0 ? ` · ${checkedCount}/${steps.length}` : ''}
                  </p>
                </div>
                {steps.length > 0 && !allChecked ? (
                  <button
                    type="button"
                    onClick={checkAll}
                    className="rounded-lg border border-border-subtle px-2 py-1 text-[10px] font-bold uppercase tracking-wide text-text-muted hover:text-text-main"
                  >
                    Check all
                  </button>
                ) : null}
              </div>

              <ul className="mt-2 space-y-1.5">
                {steps.map((step, idx) => {
                  const id = `flowx-step-${task.id}-${idx}`;
                  const isOn = Boolean(checked[idx]);
                  return (
                    <li key={id}>
                      <label
                        htmlFor={id}
                        className={`flex cursor-pointer items-start gap-3 rounded-lg border px-3 py-2.5 transition ${
                          isOn
                            ? 'border-emerald-400 bg-emerald-50/80'
                            : 'border-border-subtle bg-card hover:bg-surface-bg/60'
                        }`}
                      >
                        <input
                          id={id}
                          type="checkbox"
                          checked={isOn}
                          onChange={() => toggleStep(idx)}
                          className="mt-0.5 h-4 w-4 shrink-0 rounded border-border-subtle text-accent focus:ring-accent"
                        />
                        <span className="min-w-0 flex-1">
                          <span className="block text-[10px] font-bold uppercase tracking-wide text-text-muted">
                            Step {idx + 1}
                          </span>
                          <span
                            className={`mt-0.5 block text-sm leading-snug ${
                              isOn ? 'font-semibold text-emerald-950' : 'text-text-main'
                            }`}
                          >
                            {step}
                          </span>
                        </span>
                      </label>
                    </li>
                  );
                })}
              </ul>

              <div className="mt-3 rounded-xl border border-border-subtle bg-surface-bg/60 px-3 py-3">
                <label
                  className={`flex items-start gap-3 ${
                    allChecked ? 'cursor-pointer' : 'cursor-not-allowed opacity-60'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={confirmedComplete}
                    disabled={!allChecked && !confirmedComplete}
                    onChange={e => setConfirmation(e.target.checked)}
                    className="mt-0.5 h-4 w-4 shrink-0 rounded border-border-subtle text-accent focus:ring-accent disabled:opacity-50"
                  />
                  <span>
                    <span className="block text-sm font-semibold text-text-main">
                      Confirm all activities are complete
                    </span>
                    <span className="mt-0.5 block text-[11px] text-text-muted">
                      {allChecked
                        ? 'Saved to this journey task when checked.'
                        : 'Check every step above before confirming.'}
                    </span>
                  </span>
                </label>
              </div>
            </div>
          </div>
        </div>

        <div className="shrink-0 space-y-2 border-t border-border-subtle bg-card px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
          {isIntakeSession ? (
            <div className="space-y-2">
              {bookingStatusLabel ? (
                <p
                  className={`text-sm font-bold ${
                    intakeState?.lifecycle === 'delayed' ? 'text-red-700' : 'text-accent'
                  }`}
                >
                  {bookingStatusLabel}
                </p>
              ) : null}
              {delayDisplay ? (
                <p className="text-sm font-bold text-red-700">{delayDisplay}</p>
              ) : null}
              <p className="rounded-xl border border-border-subtle bg-surface-bg/80 px-3 py-2.5 text-sm text-text-muted">
                {intakeState?.isOverdue
                  ? 'This counselling slot has passed without a Finished update in My Bookings, so Intake Session is Delayed at 0%. Open the session and update the status to clear the delay.'
                  : 'Intake Session is confirmed from My Bookings. Open the session panel to review what was discussed and change the booking status'}
                {!intakeState?.isOverdue &&
                  (intakeState
                    ? ` (${lifecycleLabel(intakeState.lifecycle)} · ${intakeState.progress}%)`
                    : typeof task.progress_percentage === 'number'
                      ? ` (${Math.round(task.progress_percentage)}%)`
                      : '')}
                {!intakeState?.isOverdue ? '.' : ''}
              </p>
              {onViewIntakeSession ? (
                <button
                  type="button"
                  onClick={() => {
                    onClose();
                    onViewIntakeSession();
                  }}
                  className="inline-flex w-full items-center justify-center rounded-xl bg-accent px-3 py-2.5 text-sm font-semibold text-white"
                >
                  View Session
                </button>
              ) : null}
            </div>
          ) : (
            <>
              {canConfirm ? (
                <button
                  type="button"
                  onClick={() => setConfirmation(true)}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-emerald-500 bg-emerald-50 px-3 py-2.5 text-sm font-semibold text-emerald-900"
                >
                  <CheckCircle2 size={15} />
                  Confirm all activities complete
                </button>
              ) : null}
              {task.kanban_status !== 'approved' ? (
                <button
                  type="button"
                  disabled={pending || !canApprove}
                  onClick={() => onAdvance('approved')}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-accent px-3 py-2.5 text-sm font-semibold text-white disabled:opacity-50"
                  title={
                    canApprove
                      ? undefined
                      : 'Confirm all checklist activities before approving'
                  }
                >
                  <CheckCircle2 size={15} />
                  Approve &amp; Advance
                </button>
              ) : (
                <p className="rounded-xl border border-emerald-300 bg-emerald-50 px-3 py-2 text-center text-sm font-semibold text-emerald-900">
                  Sub-process approved
                </p>
              )}
              {!canApprove && task.kanban_status !== 'approved' ? (
                <p className="text-center text-[11px] text-text-muted">
                  Check every step and confirm completion to enable Approve &amp; Advance.
                </p>
              ) : null}
              <div className="flex flex-wrap gap-2">
                {nextStatuses
                  .filter(s => s !== 'approved')
                  .map(status => (
                    <button
                      key={status}
                      type="button"
                      disabled={pending}
                      onClick={() => onAdvance(status)}
                      className="rounded-lg border border-border-subtle px-2.5 py-1.5 text-xs font-semibold capitalize text-text-muted hover:text-text-main disabled:opacity-50"
                    >
                      Mark {status.replace(/_/g, ' ')}
                    </button>
                  ))}
              </div>
            </>
          )}
        </div>
      </aside>
    </div>,
    document.body
  );
}
