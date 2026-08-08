import { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import ConfirmationModal from '../ConfirmationModal';
import type { FlowxTaskTemplate } from '../../types/flowx';

export type SubprocessMode = 'required' | 'optional' | 'dropped';

type OverrideAction = 'waive' | 'make_optional' | 'force_required' | 'clear';

type SubprocessModeControlProps = {
  brick: Pick<
    FlowxTaskTemplate,
    'id' | 'title' | 'is_active' | 'is_optional' | 'override_action'
  >;
  disabled?: boolean;
  pending?: boolean;
  onApply: (payload: { template_id: string; action: OverrideAction; reason: string }) => Promise<unknown>;
  /** Compact chip for unlinked drawer; full button on board. */
  compact?: boolean;
};

const MODE_META: Record<
  SubprocessMode,
  { label: string; chipClass: string; buttonClass: string; hoverHint: string }
> = {
  required: {
    label: 'Required',
    chipClass: 'bg-surface-bg text-text-main border-border-subtle',
    buttonClass:
      'border-border-subtle bg-surface-bg text-text-main hover:bg-card',
    hoverHint: 'Click to change process mode (Optional or Drop)',
  },
  optional: {
    label: 'Optional',
    chipClass: 'bg-amber-100 text-amber-900 border-amber-300',
    buttonClass: 'border-amber-300 bg-amber-50 text-amber-900 hover:bg-amber-100',
    hoverHint: 'Click to change process mode (Required or Drop)',
  },
  dropped: {
    label: 'Dropped',
    chipClass: 'bg-red-100 text-red-800 border-red-300',
    buttonClass: 'border-red-300 bg-red-50 text-red-900 hover:bg-red-100',
    hoverHint: 'Click to set Required or Optional — stays on this country board',
  },
};

export function subprocessModeFromBrick(
  brick: Pick<FlowxTaskTemplate, 'is_active' | 'is_optional' | 'override_action'>
): SubprocessMode {
  if (brick.override_action === 'waive') return 'dropped';
  if (brick.is_optional || brick.override_action === 'make_optional') return 'optional';
  return 'required';
}

function actionForMode(mode: SubprocessMode): { action: OverrideAction; reason: string } {
  if (mode === 'optional') {
    return { action: 'make_optional', reason: 'Marked optional for this country' };
  }
  if (mode === 'dropped') {
    return { action: 'waive', reason: 'Dropped for this country' };
  }
  return { action: 'clear', reason: 'Set required for this country' };
}

const OTHER_MODES: Record<SubprocessMode, SubprocessMode[]> = {
  required: ['optional', 'dropped'],
  optional: ['required', 'dropped'],
  dropped: ['required', 'optional'],
};

/** Country-scoped Required / Optional / Drop control with popover + confirmations. */
export default function SubprocessModeControl({
  brick,
  disabled,
  pending,
  onApply,
  compact,
}: SubprocessModeControlProps) {
  const mode = subprocessModeFromBrick(brick);
  const meta = MODE_META[mode];
  const [open, setOpen] = useState(false);
  const [confirmMode, setConfirmMode] = useState<SubprocessMode | null>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const panelId = useId();

  const placePanel = () => {
    const el = btnRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const width = 176;
    const left = Math.min(
      Math.max(8, rect.left),
      Math.max(8, window.innerWidth - width - 8)
    );
    setPos({ top: rect.bottom + 6, left });
  };

  useEffect(() => {
    if (!open) return;
    placePanel();
    const onDoc = (e: MouseEvent) => {
      const t = e.target as Node;
      if (btnRef.current?.contains(t) || panelRef.current?.contains(t)) return;
      setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    const onReposition = () => placePanel();
    document.addEventListener('mousedown', onDoc);
    window.addEventListener('keydown', onKey);
    window.addEventListener('scroll', onReposition, true);
    window.addEventListener('resize', onReposition);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('scroll', onReposition, true);
      window.removeEventListener('resize', onReposition);
    };
  }, [open]);

  const requestMode = (next: SubprocessMode) => {
    if (next === mode || pending) return;
    setOpen(false);
    // Warn when leaving Required → Optional, or when Dropping.
    if (next === 'dropped' || (mode === 'required' && next === 'optional')) {
      setConfirmMode(next);
      return;
    }
    void onApply({ template_id: brick.id, ...actionForMode(next) });
  };

  const confirmCopy =
    confirmMode === 'dropped'
      ? {
          title: `Drop “${brick.title}”?`,
          message: (
            <p>
              It stays visible on this country workflow so you can switch it back to Required or
              Optional anytime. New student journeys for this country will not include this
              sub-process at all.
            </p>
          ),
          confirmLabel: 'Drop for journeys',
          variant: 'danger' as const,
        }
      : {
          title: `Make “${brick.title}” optional?`,
          message: (
            <p>
              It stays on this country board and on student journeys, but counselors will not be
              forced to complete it. Track progress ignores optional steps. You can switch it back
              to Required anytime.
            </p>
          ),
          confirmLabel: 'Make optional',
          variant: 'warning' as const,
        };

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        title={meta.hoverHint}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        disabled={disabled || pending}
        onClick={e => {
          e.stopPropagation();
          setOpen(v => !v);
        }}
        className={
          compact
            ? `rounded-md border px-2 py-1 text-[11px] font-bold ${meta.chipClass} disabled:opacity-50`
            : `rounded-md border px-2 py-1 text-xs font-semibold ${meta.buttonClass} disabled:opacity-50`
        }
      >
        {meta.label}
      </button>

      {open && pos
        ? createPortal(
            <div
              ref={panelRef}
              id={panelId}
              role="menu"
              aria-label="Change process mode"
              style={{ position: 'fixed', top: pos.top, left: pos.left, zIndex: 90 }}
              className="w-44 overflow-hidden rounded-xl border border-border-subtle bg-card shadow-lg"
              onClick={e => e.stopPropagation()}
            >
              <p className="border-b border-border-subtle px-2.5 py-1.5 text-[10px] font-bold uppercase tracking-wide text-text-muted">
                Process mode
              </p>
              <div className="p-1">
                {OTHER_MODES[mode].map(next => {
                  const nextMeta = MODE_META[next];
                  return (
                    <button
                      key={next}
                      type="button"
                      role="menuitem"
                      onClick={() => requestMode(next)}
                      className={`flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left text-xs font-semibold transition hover:bg-surface-bg ${
                        next === 'dropped' ? 'text-red-700' : 'text-text-main'
                      }`}
                    >
                      <span>{nextMeta.label}</span>
                      <span
                        className={`rounded border px-1.5 py-0.5 text-[10px] font-bold ${nextMeta.chipClass}`}
                      >
                        {next === 'dropped' ? 'Remove' : 'Set'}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>,
            document.body
          )
        : null}

      <ConfirmationModal
        open={Boolean(confirmMode)}
        variant={confirmCopy.variant}
        title={confirmCopy.title}
        message={confirmCopy.message}
        confirmLabel={pending ? 'Updating…' : confirmCopy.confirmLabel}
        cancelLabel="Cancel"
        onCancel={() => {
          if (pending) return;
          setConfirmMode(null);
        }}
        onConfirm={() => {
          if (!confirmMode || pending) return;
          const next = confirmMode;
          setConfirmMode(null);
          void onApply({ template_id: brick.id, ...actionForMode(next) });
        }}
      />
    </>
  );
}
