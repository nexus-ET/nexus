const HEADER_CLASS = 'w-px whitespace-nowrap px-3 py-3 font-semibold';
const CELL_CLASS =
  'w-px max-w-[9.5rem] truncate whitespace-nowrap px-3 py-3 font-mono text-xs tabular-nums text-text-muted';

function formatFrameworkId(value: string | number | null | undefined): string {
  if (value == null || value === '') return '—';
  return String(value);
}

function formatFrameworkIdList(
  values?: Array<string | number | null | undefined> | null
): string {
  const parts = (values ?? [])
    .filter((item): item is string | number => item != null && item !== '')
    .map(String);
  return parts.length ? [...new Set(parts)].join(', ') : '—';
}

export function FrameworkIdHeader({ label = 'ID' }: { label?: string }) {
  return <th className={HEADER_CLASS}>{label}</th>;
}

export function FrameworkIdCell({
  value,
  values,
}: {
  value?: string | number | null;
  values?: Array<string | number | null | undefined> | null;
}) {
  const text = values ? formatFrameworkIdList(values) : formatFrameworkId(value);
  return (
    <td className={CELL_CLASS} title={text === '—' ? undefined : text}>
      {text}
    </td>
  );
}

export function FrameworkIdField({
  label = 'ID',
  value,
  placeholder = 'Assigned after save',
}: {
  label?: string;
  value?: string | number | null;
  placeholder?: string;
}) {
  const assigned = value != null && value !== '';
  return (
    <label className="block space-y-1 text-sm">
      <span className="font-medium text-text-main">{label}</span>
      <input
        type="text"
        readOnly
        value={assigned ? String(value) : ''}
        placeholder={placeholder}
        className="w-full cursor-default rounded-xl border border-border-subtle bg-surface-bg/70 px-3 py-2 font-mono text-sm text-text-muted outline-none"
      />
    </label>
  );
}

export function FrameworkHierarchyId({
  label = 'ID',
  value,
}: {
  label?: string;
  value: string | number;
}) {
  const text = String(value);
  const compact = text.length > 12 ? `${text.slice(0, 8)}…` : text;
  return (
    <span
      className="shrink-0 font-mono text-[10px] tabular-nums text-text-muted"
      title={`${label} ${text}`}
    >
      {label} {compact}
    </span>
  );
}
