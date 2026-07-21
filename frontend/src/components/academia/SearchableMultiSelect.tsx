import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, X } from 'lucide-react';

export interface SearchableMultiSelectOption {
  value: string;
  label: string;
}

interface SearchableMultiSelectProps {
  id?: string;
  label: string;
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
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');

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

  const toggleValue = (value: string) => {
    if (values.includes(value)) {
      onChange(values.filter(item => item !== value));
      return;
    }
    onChange([...values, value]);
  };

  const clearAll = () => onChange([]);

  const closedDisplay =
    values.length === 0
      ? placeholder
      : selectedDisplay ?? (selectedLabels.length ? selectedLabels.join(', ') : placeholder);

  return (
    <label className="block space-y-1 text-sm">
      <span className="text-base font-bold text-text-main">
        {label}
        {required ? <span className="text-alert"> *</span> : null}
      </span>
      <div ref={containerRef} className="relative">
        <button
          id={id}
          type="button"
          disabled={disabled}
          onClick={() => !disabled && setOpen(previous => !previous)}
          className="flex w-full items-center justify-between rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-left text-sm outline-none focus:border-accent disabled:opacity-50"
        >
          <span className={values.length ? 'text-text-main' : 'text-text-muted'}>
            {closedDisplay}
          </span>
          <ChevronDown size={16} className="shrink-0 text-text-muted" />
        </button>

        {open ? (
          <div className="absolute z-[130] mt-1 w-full rounded-xl border border-border-subtle bg-card shadow-xl">
            <div className="border-b border-border-subtle p-2">
              <input
                type="text"
                value={search}
                onChange={event => setSearch(event.target.value)}
                placeholder="Search..."
                className="w-full rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
              />
            </div>
            <div className="flex items-center justify-between border-b border-border-subtle px-3 py-2 text-xs">
              <span className="text-text-muted">{values.length} selected</span>
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
            <ul className="max-h-56 overflow-y-auto py-1">
              {filteredOptions.length === 0 ? (
                <li className="px-3 py-2 text-sm text-text-muted">{emptyMessage}</li>
              ) : (
                filteredOptions.map(option => {
                  const checked = values.includes(option.value);
                  return (
                    <li key={option.value}>
                      <button
                        type="button"
                        onClick={() => toggleValue(option.value)}
                        className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-surface-bg ${
                          checked ? 'bg-accent/10 text-text-main' : 'text-text-main'
                        }`}
                      >
                        <input
                          type="checkbox"
                          readOnly
                          checked={checked}
                          className="rounded border-border-subtle"
                        />
                        {option.label}
                      </button>
                    </li>
                  );
                })
              )}
            </ul>
          </div>
        ) : null}
      </div>
      {hint ? <p className="text-xs text-text-muted">{hint}</p> : null}
    </label>
  );
};

export default SearchableMultiSelect;
