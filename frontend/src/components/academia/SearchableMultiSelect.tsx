import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { createPortal } from 'react-dom';
import { ChevronDown, X } from 'lucide-react';

export interface SearchableMultiSelectOption {
  value: string;
  label: string;
}

interface SearchableMultiSelectProps {
  id?: string;
  label?: string;
  values: string[];
  options: SearchableMultiSelectOption[];
  onChange: (values: string[]) => void;
  placeholder?: string;
  required?: boolean;
  disabled?: boolean;
  emptyMessage?: string;
  hint?: string;
  /** When set, shown on the closed control instead of listing every selected label. */
  selectedDisplay?: string;
  /** Maximum number of selections allowed. */
  maxSelections?: number;
  className?: string;
  compact?: boolean;
  /** Prefer opening the menu above the control (useful near modal footers). */
  preferDropUp?: boolean;
}

const MENU_MAX_HEIGHT = 280;

function computeMenuStyle(
  trigger: HTMLElement,
  options: { compact: boolean; preferDropUp: boolean }
): CSSProperties {
  const { compact, preferDropUp } = options;
  const rect = trigger.getBoundingClientRect();
  const spaceBelow = window.innerHeight - rect.bottom;
  const spaceAbove = rect.top;
  const preferUp = preferDropUp || spaceBelow < MENU_MAX_HEIGHT + 24;
  // Only open upward when there is enough room; otherwise open downward.
  const openUpward = preferUp && spaceAbove >= 160 && spaceAbove >= spaceBelow;
  const available = (openUpward ? spaceAbove : spaceBelow) - 16;
  const maxHeight = Math.min(MENU_MAX_HEIGHT, Math.max(160, available));
  const width = Math.max(rect.width, compact ? 240 : 280);
  const left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8));

  if (openUpward) {
    return {
      position: 'fixed',
      left,
      width,
      maxHeight,
      top: Math.max(8, rect.top - 6 - maxHeight),
      bottom: 'auto',
      zIndex: 4000,
    };
  }

  return {
    position: 'fixed',
    left,
    width,
    maxHeight,
    top: Math.min(rect.bottom + 6, window.innerHeight - maxHeight - 8),
    bottom: 'auto',
    zIndex: 4000,
  };
}

const SearchableMultiSelect: React.FC<SearchableMultiSelectProps> = ({
  id,
  label,
  values,
  options,
  onChange,
  placeholder = 'Select one or more...',
  required = false,
  disabled = false,
  emptyMessage = 'No matches found.',
  hint,
  selectedDisplay,
  maxSelections,
  className,
  compact = false,
  preferDropUp = false,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [menuStyle, setMenuStyle] = useState<CSSProperties>({});

  const selectedLabels = useMemo(() => {
    const labelByValue = new Map(options.map(option => [option.value, option.label]));
    return values
      .map(value => labelByValue.get(value))
      .filter((value): value is string => Boolean(value));
  }, [options, values]);

  const filteredOptions = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return options;
    return options.filter(
      option =>
        option.label.toLowerCase().includes(needle) ||
        option.value.toLowerCase().includes(needle)
    );
  }, [options, search]);

  const atMax =
    typeof maxSelections === 'number' && maxSelections > 0 && values.length >= maxSelections;

  const updateMenuPosition = useCallback(() => {
    const trigger = triggerRef.current;
    if (!trigger) return;
    setMenuStyle(computeMenuStyle(trigger, { compact, preferDropUp }));
  }, [compact, preferDropUp]);

  const openMenu = () => {
    const trigger = triggerRef.current;
    if (!trigger) {
      setOpen(true);
      return;
    }
    // Keep the control visible, then open above when near the bottom of the viewport/modal.
    trigger.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    setMenuStyle(computeMenuStyle(trigger, { compact, preferDropUp }));
    setOpen(true);
  };

  useLayoutEffect(() => {
    if (!open) return;
    updateMenuPosition();
    const onReposition = () => updateMenuPosition();
    window.addEventListener('resize', onReposition);
    window.addEventListener('scroll', onReposition, true);
    return () => {
      window.removeEventListener('resize', onReposition);
      window.removeEventListener('scroll', onReposition, true);
    };
  }, [open, updateMenuPosition, filteredOptions.length]);

  useEffect(() => {
    if (!open) return;

    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      if (containerRef.current?.contains(target)) return;
      if (menuRef.current?.contains(target)) return;
      setOpen(false);
    };
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    const handleFocusOutside = (event: FocusEvent) => {
      const target = event.target as Node | null;
      if (!target) return;
      if (containerRef.current?.contains(target)) return;
      if (menuRef.current?.contains(target)) return;
      setOpen(false);
    };

    // Capture phase so parents that stopPropagation (e.g. session drawers) still close the menu.
    const timer = window.setTimeout(() => {
      document.addEventListener('mousedown', handleClickOutside, true);
      document.addEventListener('focusin', handleFocusOutside, true);
    }, 0);
    document.addEventListener('keydown', handleEscape);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener('mousedown', handleClickOutside, true);
      document.removeEventListener('focusin', handleFocusOutside, true);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [open]);

  useEffect(() => {
    if (!open) setSearch('');
  }, [open]);

  const toggleValue = (value: string) => {
    if (values.includes(value)) {
      onChange(values.filter(item => item !== value));
      return;
    }
    if (atMax) return;
    onChange([...values, value]);
  };

  const clearAll = () => onChange([]);

  const closedDisplay =
    values.length === 0
      ? placeholder
      : selectedDisplay ?? (selectedLabels.length ? selectedLabels.join(', ') : placeholder);

  const listMaxHeight =
    typeof menuStyle.maxHeight === 'number' ? Math.max(80, menuStyle.maxHeight - 92) : 180;

  const menu = open
    ? createPortal(
        <div
          ref={menuRef}
          role="listbox"
          aria-multiselectable
          className={
            compact
              ? 'offline-leads-multiselect__menu offline-leads-multiselect__menu--portal'
              : 'rounded-xl border border-border-subtle bg-card shadow-xl'
          }
          style={menuStyle}
        >
          <div className={compact ? 'offline-leads-multiselect__search' : 'border-b border-border-subtle p-2'}>
            <input
              type="text"
              value={search}
              onChange={event => setSearch(event.target.value)}
              placeholder="Search..."
              className={
                compact
                  ? undefined
                  : 'w-full rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent'
              }
              autoFocus
            />
          </div>
          <div
            className={
              compact
                ? 'offline-leads-multiselect__meta'
                : 'flex items-center justify-between border-b border-border-subtle px-3 py-2 text-xs'
            }
          >
            <span className="text-text-muted">
              {values.length}
              {typeof maxSelections === 'number' ? ` / ${maxSelections}` : ''} selected
            </span>
            {values.length ? (
              <button
                type="button"
                onClick={clearAll}
                className="inline-flex items-center gap-1 font-semibold text-text-muted hover:text-text-main"
              >
                <X size={12} />
                Clear
              </button>
            ) : null}
          </div>
          <ul
            className={compact ? 'offline-leads-multiselect__list' : 'overflow-y-auto py-1'}
            style={{ maxHeight: listMaxHeight }}
          >
            {filteredOptions.length === 0 ? (
              <li className="px-3 py-2 text-sm text-text-muted">{emptyMessage}</li>
            ) : (
              filteredOptions.map(option => {
                const checked = values.includes(option.value);
                const blocked = atMax && !checked;
                return (
                  <li key={option.value}>
                    <button
                      type="button"
                      disabled={blocked}
                      onClick={() => toggleValue(option.value)}
                      className={
                        compact
                          ? `offline-leads-multiselect__option${checked ? ' is-selected' : ''}${blocked ? ' is-disabled' : ''}`
                          : `flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-surface-bg ${
                              checked ? 'bg-accent/10 text-text-main' : 'text-text-main'
                            } ${blocked ? 'opacity-40' : ''}`
                      }
                    >
                      <input
                        type="checkbox"
                        readOnly
                        checked={checked}
                        disabled={blocked}
                        className="rounded border-border-subtle"
                      />
                      {option.label}
                    </button>
                  </li>
                );
              })
            )}
          </ul>
        </div>,
        document.body
      )
    : null;

  return (
    <div
      ref={containerRef}
      className={`${compact ? 'offline-leads-multiselect' : 'block space-y-1 text-sm'} ${className || ''}`.trim()}
    >
      {label && !compact ? (
        <span className="text-base font-bold text-text-main">
          {label}
          {required ? <span className="text-alert"> *</span> : null}
        </span>
      ) : null}
      <div className="relative">
        <button
          ref={triggerRef}
          id={id}
          type="button"
          disabled={disabled}
          aria-expanded={open}
          onClick={() => {
            if (disabled) return;
            if (open) setOpen(false);
            else openMenu();
          }}
          className={
            compact
              ? 'offline-leads-multiselect__trigger'
              : 'flex w-full items-center justify-between rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-left text-sm outline-none focus:border-accent disabled:opacity-50'
          }
        >
          <span
            className={
              values.length
                ? compact
                  ? undefined
                  : 'text-text-main'
                : compact
                  ? 'is-placeholder'
                  : 'text-text-muted'
            }
          >
            {closedDisplay}
          </span>
          <ChevronDown size={16} className="shrink-0 text-text-muted" />
        </button>
      </div>
      {hint ? (
        <p className={compact ? 'offline-leads-multiselect__hint' : 'text-xs text-text-muted'}>{hint}</p>
      ) : null}
      {menu}
    </div>
  );
};

export default SearchableMultiSelect;
