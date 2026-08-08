import React from 'react';
import type { AspirationOptionDef } from '../../config/aspirations.config';

const baseCardClass =
  'rounded-lg border px-3 py-2.5 text-sm text-left cursor-pointer transition-colors whitespace-normal';

type ColumnCount = 1 | 2 | 3 | 4 | 5 | 6 | 'fit';

const COLUMN_CLASS: Record<Exclude<ColumnCount, 'fit'>, string> = {
  1: 'grid-cols-1',
  2: 'grid-cols-1 sm:grid-cols-2',
  3: 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3',
  4: 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-4',
  5: 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-5',
  6: 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-6',
};

interface OptionCardGroupProps {
  name: string;
  options: AspirationOptionDef[];
  value: string | null | undefined;
  onChange: (next: string) => void;
  /** Fixed responsive columns, or `fit` to place every option on one row. */
  columns?: ColumnCount;
  hasError?: boolean;
  multi?: boolean;
  selectedValues?: string[];
  onToggle?: (value: string, checked: boolean) => void;
}

export function OptionCardGroup({
  name,
  options,
  value,
  onChange,
  columns = 2,
  hasError = false,
  multi = false,
  selectedValues = [],
  onToggle,
}: OptionCardGroupProps) {
  return (
    <div
      className={
        columns === 'fit'
          ? 'flex flex-nowrap gap-2 overflow-x-auto'
          : `grid gap-2 ${COLUMN_CLASS[columns]}`
      }
      role="group"
      aria-label={name}
      aria-multiselectable={multi || undefined}
    >
      {options.map(option => {
        const checked = multi
          ? selectedValues.includes(option.value)
          : value === option.value;
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={checked}
            onClick={() => {
              if (multi && onToggle) {
                onToggle(option.value, !checked);
              } else if (checked) {
                onChange('');
              } else {
                onChange(option.value);
              }
            }}
            className={`${baseCardClass} ${
              columns === 'fit'
                ? option.cardClassName
                  ? `min-w-0 ${option.cardClassName}`
                  : 'min-w-0 flex-1'
                : option.cardClassName || ''
            } ${
              checked
                ? 'border-primary bg-primary text-white'
                : hasError
                  ? 'border-red-300 ring-1 ring-red-100 bg-surface-bg/50 text-text-main hover:bg-surface-bg'
                  : 'border-border-subtle bg-surface-bg/50 text-text-main hover:bg-surface-bg'
            }`}
          >
            <span className="min-w-0 block">
              <span className="font-semibold block leading-snug whitespace-normal break-words">
                {option.title || option.label}
              </span>
              {option.description ? (
                <span
                  className={`block text-sm mt-0.5 leading-snug ${
                    option.descriptionNowrap
                      ? 'whitespace-nowrap'
                      : 'whitespace-normal break-words'
                  } ${checked ? 'text-white/90' : 'text-text-muted'}`}
                >
                  {option.description}
                </span>
              ) : null}
            </span>
          </button>
        );
      })}
    </div>
  );
}

interface PillToggleGridProps {
  options: AspirationOptionDef[];
  selected: string[];
  onToggle: (value: string, checked: boolean) => void;
  hasError?: boolean;
  renderSelectedExtra?: (value: string) => React.ReactNode;
}

export function PillToggleGrid({
  options,
  selected,
  onToggle,
  hasError = false,
  renderSelectedExtra,
}: PillToggleGridProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map(option => {
        const active = selected.includes(option.value);
        return (
          <div key={option.value} className="flex flex-col gap-1">
            <button
              type="button"
              onClick={() => onToggle(option.value, !active)}
              className={`rounded-full border px-3 py-1.5 text-sm font-medium transition-colors ${
                active
                  ? 'border-primary bg-primary text-white'
                  : hasError
                    ? 'border-red-300 text-text-main bg-surface-bg'
                    : 'border-border-subtle text-text-main bg-surface-bg hover:bg-surface-bg/80'
              }`}
            >
              {option.label}
            </button>
            {active && renderSelectedExtra ? renderSelectedExtra(option.value) : null}
          </div>
        );
      })}
    </div>
  );
}

interface AspirationBlockProps {
  code?: string;
  title: string;
  children: React.ReactNode;
  complete?: boolean;
}

export function AspirationBlock({ code, title, children, complete }: AspirationBlockProps) {
  return (
    <div className="space-y-3">
      <div className="flex items-start justify-between gap-3">
        <h5 className="text-sm font-bold text-text-main">
          {code ? <span className="text-text-muted font-semibold mr-1.5">{code}</span> : null}
          {title}
        </h5>
        {complete != null ? (
          <span
            className={`shrink-0 text-xs font-semibold px-2 py-0.5 rounded-full ${
              complete
                ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                : 'bg-amber-50 text-amber-800 border border-amber-200'
            }`}
          >
            {complete ? 'Complete' : 'Pending'}
          </span>
        ) : null}
      </div>
      {children}
    </div>
  );
}

interface AspirationSectionShellProps {
  title: string;
  description?: string;
  progressLabel: string;
  children: React.ReactNode;
}

export function AspirationSectionShell({
  title,
  description,
  progressLabel,
  children,
}: AspirationSectionShellProps) {
  return (
    <section className="rounded-xl border border-border-subtle bg-white p-4 space-y-5 shadow-sm">
      <header className="flex flex-wrap items-start justify-between gap-2 border-b border-border-subtle pb-3">
        <div>
          <h4 className="text-base font-bold text-text-main">{title}</h4>
          {description ? (
            <p className="text-sm text-text-muted mt-0.5">{description}</p>
          ) : null}
        </div>
        <span className="text-xs font-semibold text-text-muted bg-surface-bg border border-border-subtle rounded-full px-2.5 py-1">
          {progressLabel}
        </span>
      </header>
      {children}
    </section>
  );
}

export const fieldLabelClass = 'block text-sm font-semibold text-text-main mb-1';
export const textInputClass =
  'w-full max-w-md rounded-md border border-border-subtle bg-surface-bg px-3 py-2 text-sm text-text-main placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/30';
export const selectClass =
  'w-full max-w-lg rounded-md border border-border-subtle bg-surface-bg px-3 py-2 text-sm text-text-main focus:outline-none focus:ring-2 focus:ring-primary/30';
