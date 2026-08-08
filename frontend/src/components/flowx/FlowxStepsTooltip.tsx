import {
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
  type MouseEvent as ReactMouseEvent,
} from 'react';
import { createPortal } from 'react-dom';

type FlowxStepsTooltipProps = {
  steps: string[];
  children: ReactNode;
  disabled?: boolean;
  /** Sequential ID shown in the tooltip header, e.g. "1" or "1.2". */
  code?: string;
  /** Process / sub-process display name. */
  name?: string;
  /** Kind label used with code, e.g. "Process" or "Sub-process". */
  kind?: 'Process' | 'Sub-process';
  heading?: string;
};

type PanelPos = { top: number; left: number; placeAbove: boolean };

/** Click-to-open panel listing short action steps (process / sub-process). */
export default function FlowxStepsTooltip({
  steps,
  children,
  disabled,
  code,
  name,
  kind = 'Process',
  heading = 'Steps to perform',
}: FlowxStepsTooltipProps) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<PanelPos | null>(null);
  const anchorRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const panelId = useId();

  const updatePos = () => {
    const el = anchorRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const panelH = Math.min(280, panelRef.current?.offsetHeight || 180);
    const gap = 8;
    const placeAbove = rect.bottom + gap + panelH > window.innerHeight && rect.top > panelH;
    const left = Math.min(
      Math.max(8, rect.left),
      Math.max(8, window.innerWidth - 256 - 8)
    );
    setPos({
      top: placeAbove ? rect.top - gap : rect.bottom + gap,
      left,
      placeAbove,
    });
  };

  useLayoutEffect(() => {
    if (!open) return;
    updatePos();
  }, [open, steps]);

  useEffect(() => {
    if (!open) return;
    const onScrollOrResize = () => updatePos();
    const onDocPointer = (e: MouseEvent) => {
      const t = e.target as Node;
      if (anchorRef.current?.contains(t) || panelRef.current?.contains(t)) return;
      setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('scroll', onScrollOrResize, true);
    window.addEventListener('resize', onScrollOrResize);
    document.addEventListener('mousedown', onDocPointer);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('scroll', onScrollOrResize, true);
      window.removeEventListener('resize', onScrollOrResize);
      document.removeEventListener('mousedown', onDocPointer);
      window.removeEventListener('keydown', onKey);
    };
  }, [open]);

  useEffect(() => {
    if (disabled) setOpen(false);
  }, [disabled]);

  // Keep wrapper DOM stable during drag — remounting mid-drag freezes HTML5 DnD.
  useEffect(() => {
    const close = () => setOpen(false);
    window.addEventListener('flowx-close-steps', close);
    return () => window.removeEventListener('flowx-close-steps', close);
  }, []);

  const toggleFromClick = (e: ReactMouseEvent) => {
    if (disabled) return;
    const target = e.target as HTMLElement | null;
    // Keep Edit / Nested / mode controls / form fields from toggling the steps panel.
    if (target?.closest('button, a, input, textarea, select, label, [role="button"], [role="menuitem"]')) {
      return;
    }
    setOpen(v => !v);
  };

  return (
    <div ref={anchorRef} className="relative">
      <div
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        onClick={toggleFromClick}
        className={disabled ? undefined : 'cursor-pointer'}
      >
        {children}
      </div>
      {open && pos
        ? createPortal(
            <div
              ref={panelRef}
              id={panelId}
              role="dialog"
              aria-label={name ? `Steps for ${name}` : heading}
              style={{
                position: 'fixed',
                top: pos.top,
                left: pos.left,
                transform: pos.placeAbove ? 'translateY(-100%)' : undefined,
                zIndex: 80,
              }}
              className="w-[16.5rem] rounded-xl border border-border-subtle bg-card p-3 shadow-lg"
              onClick={e => e.stopPropagation()}
            >
              {code || name ? (
                <div className="mb-2 border-b border-border-subtle pb-2">
                  {code ? (
                    <p className="text-[10px] font-bold uppercase tracking-wide text-text-muted">
                      {kind} {code}
                    </p>
                  ) : null}
                  {name ? (
                    <p className="mt-0.5 text-sm font-semibold leading-snug text-text-main">
                      {name}
                    </p>
                  ) : null}
                </div>
              ) : null}
              <p className="text-[10px] font-bold uppercase tracking-wide text-text-muted">
                {heading}
              </p>
              {steps.length === 0 ? (
                <p className="mt-1.5 text-xs text-text-muted">No steps listed.</p>
              ) : (
                <ol className="mt-1.5 space-y-1">
                  {steps.map((step, idx) => (
                    <li
                      key={`${idx}-${step}`}
                      className="flex gap-2 text-xs leading-snug text-text-main"
                    >
                      <span className="shrink-0 font-bold tabular-nums text-text-muted">
                        {idx + 1}.
                      </span>
                      <span>{step}</span>
                    </li>
                  ))}
                </ol>
              )}
              <p className="mt-2 text-[10px] text-text-muted">Click again or press Esc to close</p>
            </div>,
            document.body
          )
        : null}
    </div>
  );
}
