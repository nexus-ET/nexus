import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, X } from 'lucide-react';

import MajorColorSwatch from './MajorColorSwatch';

export interface SearchableSelectOption {
  value: string;
  label: string;
  color?: string | null;
}

interface SearchableSelectProps {
  id?: string;
  label?: string;
  value: string;
  options: SearchableSelectOption[];
  onChange: (value: string) => void;
  placeholder?: string;
  required?: boolean;
  disabled?: boolean;
  emptyMessage?: string;
  hint?: string;
  onOpen?: () => void;
}

const SearchableSelect: React.FC<SearchableSelectProps> = ({
  id,
  label,
  value,
  options,
  onChange,
  placeholder = 'Search...',
  required = false,
  disabled = false,
  emptyMessage = 'No matches found.',
  hint,
  onOpen,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');

  const selectedOption = useMemo(
    () => options.find(option => option.value === value),
    [options, value]
  );
  const selectedLabel = selectedOption?.label || '';

  const filteredOptions = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return options;
    return options.filter(
      option =>
        option.label.toLowerCase().includes(needle) ||
        option.value.toLowerCase().includes(needle)
    );
  }, [options, search]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    if (!open) {
      setSearch('');
    }
  }, [open]);

  return (
    <label className={`block min-w-0 max-w-full space-y-1 text-sm ${open ? 'relative z-50' : 'relative z-0'}`}>
      {label ? (
        <span className="block truncate text-sm font-bold text-text-main">
          {label}
          {required ? <span className="text-alert"> *</span> : null}
        </span>
      ) : null}
      <div ref={containerRef} className={`relative min-w-0 ${open ? 'z-50' : 'z-0'}`}>
        <button
          id={id}
          type="button"
          disabled={disabled}
          onClick={() => {
            onOpen?.();
            if (!disabled) setOpen(previous => !previous);
          }}
          className="flex w-full min-w-0 items-center justify-between gap-1 overflow-hidden rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-left text-sm text-text-main outline-none transition-colors hover:border-accent/40 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <span className={`flex min-w-0 items-center gap-2 ${selectedLabel ? '' : 'text-text-muted'}`}>
            {selectedOption?.color ? (
              <MajorColorSwatch color={selectedOption.color} label={selectedLabel} size="sm" />
            ) : null}
            <span className="truncate">{selectedLabel || placeholder}</span>
          </span>
          <ChevronDown size={16} className="shrink-0 text-text-muted" />
        </button>
        {value && !disabled ? (
          <button
            type="button"
            onClick={() => onChange('')}
            className="absolute right-8 top-1/2 -translate-y-1/2 rounded p-0.5 text-text-muted hover:text-text-main"
            aria-label={label ? `Clear ${label}` : 'Clear selection'}
          >
            <X size={14} />
          </button>
        ) : null}
        {open ? (
          <div className="absolute left-0 z-50 mt-1 w-max min-w-full max-w-[min(16rem,calc(100vw-2rem))] overflow-hidden rounded-xl border border-border-subtle bg-card shadow-lg">
            <div className="border-b border-border-subtle p-2">
              <input
                type="text"
                value={search}
                onChange={event => setSearch(event.target.value)}
                placeholder={placeholder}
                autoFocus
                className="w-full rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
              />
            </div>
            <ul className="max-h-80 overflow-y-auto py-1">
              {filteredOptions.length === 0 ? (
                <li className="px-3 py-2 text-xs text-text-muted">{emptyMessage}</li>
              ) : (
                filteredOptions.map(option => (
                  <li key={option.value}>
                    <button
                      type="button"
                      onClick={() => {
                        onChange(option.value);
                        setOpen(false);
                      }}
                      className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors hover:bg-surface-bg ${
                        option.value === value ? 'bg-accent/10 font-semibold text-accent' : 'text-text-main'
                      }`}
                    >
                      {option.color ? (
                        <MajorColorSwatch color={option.color} label={option.label} size="sm" />
                      ) : null}
                      <span className="truncate">{option.label}</span>
                    </button>
                  </li>
                ))
              )}
            </ul>
          </div>
        ) : null}
      </div>
      {hint ? <span className="text-xs text-text-muted">{hint}</span> : null}
    </label>
  );
};

export default SearchableSelect;
