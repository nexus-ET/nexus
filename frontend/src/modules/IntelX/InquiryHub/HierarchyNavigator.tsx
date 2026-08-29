import { useEffect, useRef, useState } from 'react';
import { Check, ChevronDown, FolderTree } from 'lucide-react';
import type { InquiryNode } from './types';

interface Props {
  nodes: InquiryNode[];
  selectedProcesses: string[];
  selectedPaths: string[];
  onProcessesChange: (codes: string[]) => void;
  onPathsChange: (codes: string[]) => void;
}

interface Option {
  value: string;
  label: string;
  indented?: boolean;
}

function MultiSelectDropdown({
  label,
  allLabel,
  options,
  values,
  onChange,
}: {
  label: string;
  allLabel: string;
  options: Option[];
  values: string[];
  onChange: (values: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [open]);

  const summary =
    values.length === 0
      ? allLabel
      : values.length === 1
        ? options.find(option => option.value === values[0])?.label || '1 selected'
        : `${values.length} selected`;

  const toggle = (value: string) => {
    onChange(
      values.includes(value)
        ? values.filter(current => current !== value)
        : [...values, value]
    );
  };

  return (
    <div ref={containerRef} className="relative">
      <span className="block text-xs font-semibold uppercase tracking-wide text-text-muted">
        {label}
      </span>
      <button
        type="button"
        onClick={() => setOpen(value => !value)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="mt-1.5 flex w-full items-center justify-between gap-2 rounded-xl border border-border-subtle bg-card px-3 py-2.5 text-left text-sm text-text-main outline-none focus:border-accent focus:ring-2 focus:ring-accent/15"
      >
        <span className="truncate">{summary}</span>
        <ChevronDown size={15} className={`shrink-0 transition ${open ? 'rotate-180' : ''}`} />
      </button>
      {open ? (
        <div
          role="listbox"
          aria-multiselectable="true"
          className="absolute z-30 mt-1 max-h-72 w-full overflow-y-auto rounded-xl border border-border-subtle bg-card p-1.5 shadow-xl"
        >
          <button
            type="button"
            role="option"
            aria-selected={values.length === 0}
            onClick={() => onChange([])}
            className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm font-semibold text-text-main hover:bg-accent/10"
          >
            <span className={`flex h-4 w-4 items-center justify-center rounded border ${values.length === 0 ? 'border-accent bg-accent text-white' : 'border-border-subtle'}`}>
              {values.length === 0 ? <Check size={11} /> : null}
            </span>
            {allLabel}
          </button>
          {options.map(option => {
            const checked = values.includes(option.value);
            return (
              <button
                key={option.value}
                type="button"
                role="option"
                aria-selected={checked}
                onClick={() => toggle(option.value)}
                className={`flex w-full items-center gap-2 rounded-lg py-2 pr-2.5 text-left text-sm hover:bg-accent/10 ${option.indented ? 'pl-6' : 'pl-2.5'}`}
              >
                <span className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border ${checked ? 'border-accent bg-accent text-white' : 'border-border-subtle'}`}>
                  {checked ? <Check size={11} /> : null}
                </span>
                <span className="truncate text-text-main">{option.label}</span>
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

export default function HierarchyNavigator({
  nodes,
  selectedProcesses,
  selectedPaths,
  onProcessesChange,
  onPathsChange,
}: Props) {
  const visibleProcesses =
    selectedProcesses.length === 0
      ? nodes
      : nodes.filter(node => selectedProcesses.includes(node.code));
  const processOptions = nodes.map(node => ({
    value: node.code,
    label: `${node.code === 'OTHER' ? '' : `${node.code}. `}${node.name}`,
  }));
  const pathOptions = visibleProcesses.flatMap(process =>
    process.children.flatMap(subprocess => [
      {
        value: subprocess.code,
        label: `${subprocess.code} ${subprocess.name}`,
      },
      ...subprocess.children.map(nested => ({
        value: nested.code,
        label: `${nested.code} ${nested.name}`,
        indented: true,
      })),
    ])
  );

  return (
    <section className="rounded-2xl border border-border-subtle bg-card p-4 shadow-sm">
      <div className="mb-4 flex items-center gap-2">
        <span className="rounded-lg bg-accent/10 p-2 text-accent"><FolderTree size={18} /></span>
        <div>
          <h2 className="font-bold text-text-main">Process hierarchy</h2>
          <p className="text-xs text-text-muted">Select one, many, or all stages</p>
        </div>
      </div>

      <div className="space-y-3">
        <MultiSelectDropdown
          label="Process"
          allLabel="All processes"
          options={processOptions}
          values={selectedProcesses}
          onChange={values => {
            onProcessesChange(values);
            onPathsChange([]);
          }}
        />
        <MultiSelectDropdown
          label="Sub / nested process"
          allLabel="All sub-processes"
          options={pathOptions}
          values={selectedPaths}
          onChange={onPathsChange}
        />
      </div>

      <div className="mt-4 text-xs text-text-muted">
        {selectedProcesses.length === 0 ? 'All processes' : `${selectedProcesses.length} process${selectedProcesses.length === 1 ? '' : 'es'}`}
        {' · '}
        {selectedPaths.length === 0 ? 'All sub-processes' : `${selectedPaths.length} selected`}
      </div>
    </section>
  );
}
