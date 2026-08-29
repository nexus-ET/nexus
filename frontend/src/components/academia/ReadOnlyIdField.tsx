interface ReadOnlyIdFieldProps {
  label?: string;
  value: number | string | null | undefined;
  className?: string;
  /** Match SelectField label/input spacing (wizard profile rows). */
  aligned?: boolean;
}

export const formatEntityId = (value: number | string | null | undefined): string => {
  if (value === null || value === undefined || value === '') return '—';
  return String(value);
};

/** Compact muted ID for tables — matches Academic Framework list treatment. */
export const entityIdCellClass = 'tabular-nums text-text-muted';

const readOnlyInputClass =
  'w-full rounded-xl border border-border-subtle px-3 py-2 text-sm tabular-nums text-text-main outline-none';

const ReadOnlyIdField: React.FC<ReadOnlyIdFieldProps> = ({
  label = 'ID',
  value,
  className = '',
  aligned = false,
}) => {
  const inputClass = `${readOnlyInputClass} ${aligned ? 'bg-surface-bg' : 'bg-card'}`;

  if (aligned) {
    return (
      <div className={`min-w-0 space-y-1.5 text-sm ${className}`}>
        <span className="block text-sm font-bold text-text-main">{label}</span>
        <input type="text" value={formatEntityId(value)} readOnly className={inputClass} />
      </div>
    );
  }

  return (
    <label className={`block space-y-1 text-sm ${className}`}>
      <span className="font-medium text-text-main">{label}</span>
      <input type="text" value={formatEntityId(value)} readOnly className={inputClass} />
    </label>
  );
};

export default ReadOnlyIdField;
