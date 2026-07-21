import { useId } from 'react';

const fieldClass =
  'w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent';

interface CharCountFieldBaseProps {
  label: string;
  maxLength: number;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  hint?: string;
  required?: boolean;
  id?: string;
}

interface CharCountInputProps extends CharCountFieldBaseProps {
  type?: 'text' | 'url';
}

interface CharCountTextareaProps extends CharCountFieldBaseProps {
  rows?: number;
  mono?: boolean;
}

const FieldMeta: React.FC<{
  hint?: string;
  count: number;
  maxLength: number;
}> = ({ hint, count, maxLength }) => (
  <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-text-muted">
    {hint ? <span>{hint}</span> : <span />}
    <span className={count > maxLength ? 'text-alert' : undefined}>
      {count} / {maxLength} characters
    </span>
  </div>
);

const FieldLabel: React.FC<{
  htmlFor: string;
  label: string;
  maxLength: number;
  required?: boolean;
}> = ({ htmlFor, label, maxLength, required }) => (
  <label htmlFor={htmlFor} className="block text-sm font-bold text-text-main">
    {label}
    {required ? ' *' : ''}
    <span className="ml-1 font-normal text-text-muted">(max {maxLength})</span>
  </label>
);

export const CharCountInput: React.FC<CharCountInputProps> = ({
  label,
  maxLength,
  value,
  onChange,
  placeholder,
  hint,
  required,
  type = 'text',
  id,
}) => {
  const autoId = useId();
  const fieldId = id || autoId;
  const count = value.length;

  return (
    <div className="space-y-1.5 text-sm">
      <FieldLabel htmlFor={fieldId} label={label} maxLength={maxLength} required={required} />
      <input
        id={fieldId}
        type={type}
        maxLength={maxLength}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        className={fieldClass}
      />
      <FieldMeta hint={hint} count={count} maxLength={maxLength} />
    </div>
  );
};

export const CharCountTextarea: React.FC<CharCountTextareaProps> = ({
  label,
  maxLength,
  value,
  onChange,
  placeholder,
  hint,
  required,
  rows = 3,
  mono = false,
  id,
}) => {
  const autoId = useId();
  const fieldId = id || autoId;
  const count = value.length;

  return (
    <div className="space-y-1.5 text-sm">
      <FieldLabel htmlFor={fieldId} label={label} maxLength={maxLength} required={required} />
      <textarea
        id={fieldId}
        maxLength={maxLength}
        rows={rows}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        className={`${fieldClass}${mono ? ' font-mono text-xs' : ''}`}
      />
      <FieldMeta hint={hint} count={count} maxLength={maxLength} />
    </div>
  );
};

export const FieldHint: React.FC<{ hint: string }> = ({ hint }) => (
  <p className="text-xs text-text-muted">{hint}</p>
);
