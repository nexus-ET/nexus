import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { createPortal } from 'react-dom';
import { ChevronDown, X } from 'lucide-react';

import MajorColorSwatch from './MajorColorSwatch';

export interface SearchableMultiSelectOption {
  value: string;
  label: string;
  color?: string | null;
  disabled?: boolean;
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
  onOpen?: () => void;
  /** When set, shown on the closed control instead of listing every selected label. */
  selectedDisplay?: string;
  /** Maximum number of selections allowed. */
  maxSelections?: number;
  className?: string;
  compact?: boolean;
  /** Prefer opening the menu above the control (useful near modal footers). */
  preferDropUp?: boolean;
}

const MENU_MAX_HEIGHT = 360;

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
  onOpen,
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
    const option = options.find(item => item.value === value);
    if (option?.disabled || atMax) return;
    onChange([...values, value]);
  };

  const clearAll = () => onChange([]);

  const closedDisplay =
    values.length === 0
      ? placeholder
      : selectedDisplay ?? (selectedLabels.length ? selectedLabels.join(', ') : placeholder);

  const listMaxHeight =
    typeof menuStyle.maxHeight === 'number' ? Math.max(140, menuStyle.maxHeight - 92) : 240;

  const menu = open
    ? createPortal(
        <div
          ref={menuRef}
          role="listbox"
          aria-multiselectable
          className={
            compact
              ? 'z-[140] flex flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-[0_12px_28px_rgba(15,23,42,0.14)] !fixed m-0 shadow-[0_16px_40px_rgba(15,23,42,0.22)]'
              : 'rounded-xl border border-border-subtle bg-card shadow-xl'
          }
          style={menuStyle}
        >
          <div className={compact ? 'shrink-0 border-b border-slate-200 p-2 [&_input]:w-full [&_input]:rounded-md [&_input]:border [&_input]:border-slate-300 [&_input]:px-2 [&_input]:py-1.5 [&_input]:text-[13px]' : 'border-b border-border-subtle p-2'}>
            <input
              id={id ? `${id}-search` : 'multiselect-search'}
              name={id ? `${id}-search` : 'multiselect-search'}
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
                ? 'flex shrink-0 items-center justify-between border-b border-slate-200 px-2.5 py-1.5 text-xs text-slate-500'
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
            className={compact ? 'm-0 min-h-0 flex-auto list-none overflow-y-auto py-1' : 'overflow-y-auto py-1'}
            style={{ maxHeight: listMaxHeight }}
          >
            {filteredOptions.length === 0 ? (
              <li className="px-3 py-2 text-sm text-text-muted">{emptyMessage}</li>
            ) : (
              filteredOptions.map(option => {
                const checked = values.includes(option.value);
                const blocked = (atMax && !checked) || Boolean(option.disabled && !checked);
                return (
                  <li key={option.value}>
                    <button
                      type="button"
                      disabled={blocked}
                      onClick={() => toggleValue(option.value)}
                      className={
                        compact
                          ? `flex w-full cursor-pointer items-center gap-2 border-0 bg-transparent px-2.5 py-2 text-left text-[13px] text-slate-900 hover:bg-slate-50 [&.is-disabled]:cursor-not-allowed [&.is-disabled]:opacity-45 [&.is-selected]:bg-blue-50${checked ? ' is-selected' : ''}${blocked ? ' is-disabled' : ''}`
                          : `flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-surface-bg ${
                              checked ? 'bg-accent/10 text-text-main' : 'text-text-main'
                            } ${blocked ? 'opacity-40' : ''}`
                      }
                    >
                      <input
                        type="checkbox"
                        id={id ? `${id}-opt-${option.value}` : `opt-${option.value}`}
                        name={id ? `${id}-opt-${option.value}` : `opt-${option.value}`}
                        readOnly
                        checked={checked}
                        disabled={blocked}
                        className="rounded border-border-subtle"
                        tabIndex={-1}
                        aria-hidden
                      />
                      {option.color ? (
                        <MajorColorSwatch color={option.color} label={option.label} size="sm" />
                      ) : null}
                      <span className="truncate">{option.label}</span>
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
      className={`${compact ? 'flex min-w-0 flex-col gap-0' : 'block space-y-1 text-sm'} ${className || ''}`.trim()}
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
            onOpen?.();
            if (open) setOpen(false);
            else openMenu();
          }}
          className={
            compact
              ? 'flex min-h-[38px] w-full cursor-pointer items-center justify-between gap-2 rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-left text-[13px] text-slate-900 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400 [&_.is-placeholder]:text-slate-400'
              : 'flex w-full items-center justify-between rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-left text-sm outline-none focus:border-accent disabled:opacity-50'
          }
        >
          <span
            className={
              values.length
                ? compact
                  ? undefined
                  : 'min-w-0 truncate text-text-main'
                : compact
                  ? 'is-placeholder'
                  : 'min-w-0 truncate text-text-muted'
            }
          >
            {closedDisplay}
          </span>
          <ChevronDown size={16} className="shrink-0 text-text-muted" />
        </button>
      </div>
      {hint ? (
        <p className={compact ? 'm-0 mt-1 text-xs text-slate-500' : 'text-xs text-text-muted'}>{hint}</p>
      ) : null}
      {menu}
    </div>
  );
};

export default SearchableMultiSelect;
