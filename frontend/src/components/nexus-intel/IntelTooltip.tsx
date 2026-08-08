import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { ExternalLink } from 'lucide-react';
import { useIntelPreferences, useIntelTooltip } from '../../hooks/useNexusIntel';

interface IntelTooltipProps {
  termSlug: string;
  children: ReactNode;
  className?: string;
}

const POPOVER_WIDTH = 288;
const POPOVER_ESTIMATE_HEIGHT = 200;
const CLOSE_DELAY_MS = 120;

const IntelTooltip: React.FC<IntelTooltipProps> = ({ termSlug, children, className }) => {
  const [open, setOpen] = useState(false);
  const [style, setStyle] = useState<CSSProperties | null>(null);
  const triggerRef = useRef<HTMLSpanElement>(null);
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const prefs = useIntelPreferences();
  const tipsEnabled = prefs.data?.enable_contextual_tips !== false;
  const tooltipQuery = useIntelTooltip(termSlug, open && tipsEnabled);
  const tip = tooltipQuery.data;

  const clearCloseTimer = useCallback(() => {
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  }, []);

  const scheduleClose = useCallback(() => {
    clearCloseTimer();
    closeTimerRef.current = setTimeout(() => setOpen(false), CLOSE_DELAY_MS);
  }, [clearCloseTimer]);

  const openNow = useCallback(() => {
    clearCloseTimer();
    setOpen(true);
  }, [clearCloseTimer]);

  const updatePosition = useCallback(() => {
    const trigger = triggerRef.current;
    if (!trigger) return;
    const rect = trigger.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom;
    const spaceAbove = rect.top;
    const openUpward =
      spaceBelow < POPOVER_ESTIMATE_HEIGHT + 16 && spaceAbove > spaceBelow;
    const left = Math.max(8, Math.min(rect.left, window.innerWidth - POPOVER_WIDTH - 8));

    if (openUpward) {
      setStyle({
        position: 'fixed',
        left,
        width: POPOVER_WIDTH,
        bottom: Math.max(8, window.innerHeight - rect.top + 8),
        top: 'auto',
        zIndex: 5000,
      });
      return;
    }

    setStyle({
      position: 'fixed',
      left,
      width: POPOVER_WIDTH,
      top: Math.min(rect.bottom + 8, window.innerHeight - 24),
      bottom: 'auto',
      zIndex: 5000,
    });
  }, []);

  useLayoutEffect(() => {
    if (!open) {
      setStyle(null);
      return;
    }
    updatePosition();
  }, [open, tip, tooltipQuery.isLoading, updatePosition]);

  useEffect(() => {
    if (!open) return;
    const onReposition = () => updatePosition();
    window.addEventListener('scroll', onReposition, true);
    window.addEventListener('resize', onReposition);
    return () => {
      window.removeEventListener('scroll', onReposition, true);
      window.removeEventListener('resize', onReposition);
    };
  }, [open, updatePosition]);

  useEffect(() => () => clearCloseTimer(), [clearCloseTimer]);

  if (!tipsEnabled) {
    return <span className={className}>{children}</span>;
  }

  return (
    <>
      <span
        ref={triggerRef}
        className={`inline-flex ${className || ''}`}
        onMouseEnter={openNow}
        onMouseLeave={scheduleClose}
        onFocus={openNow}
        onBlur={scheduleClose}
      >
        <button
          type="button"
          className="border-b border-dotted border-accent/60 text-left font-semibold text-text-main"
        >
          {children}
        </button>
      </span>
      {open && style
        ? createPortal(
            <div
              role="tooltip"
              className="rounded-xl border border-border-subtle bg-card p-3 text-left shadow-xl"
              style={style}
              onMouseEnter={openNow}
              onMouseLeave={scheduleClose}
            >
              {tooltipQuery.isLoading ? (
                <span className="text-xs text-text-muted">Loading definition…</span>
              ) : tip ? (
                <div className="space-y-2">
                  <p className="text-sm font-bold text-text-main">{tip.term_name}</p>
                  <p className="text-xs text-text-muted">{tip.short_definition}</p>
                  <div className="flex flex-wrap gap-2 text-[11px] text-text-muted">
                    <span className="rounded-full bg-surface-bg px-2 py-0.5">{tip.country_code}</span>
                    <span className="rounded-full bg-surface-bg px-2 py-0.5">{tip.category}</span>
                  </div>
                  {tip.last_verified_at ? (
                    <p className="text-[11px] text-text-muted">
                      Verified {new Date(tip.last_verified_at).toLocaleDateString()}
                    </p>
                  ) : null}
                  {tip.official_source_url ? (
                    <a
                      href={tip.official_source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-[11px] font-semibold text-accent"
                    >
                      Official source <ExternalLink size={11} />
                    </a>
                  ) : null}
                </div>
              ) : (
                <span className="text-xs text-text-muted">Definition unavailable.</span>
              )}
            </div>,
            document.body
          )
        : null}
    </>
  );
};

export default IntelTooltip;
