import { useId } from 'react';
import { FieldHint } from './CharCountField';

const fieldClass =
  'w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent';

interface SelectOption {
  value: string;
  label: string;
}

interface SelectFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  placeholder?: string;
  hint?: string;
  required?: boolean;
}

const SelectField: React.FC<SelectFieldProps> = ({
  label,
  value,
  onChange,
  options,
  placeholder = 'Select...',
  hint,
  required,
}) => {
  const fieldId = useId();

  return (
    <div className="space-y-1.5 text-sm">
      <label htmlFor={fieldId} className="block text-sm font-bold text-text-main">
        {label}
        {required ? ' *' : ''}
      </label>
      <select
        id={fieldId}
        value={value}
        onChange={e => onChange(e.target.value)}
        className={fieldClass}
      >
        <option value="">{placeholder}</option>
        {options.map(option => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {hint ? <FieldHint hint={hint} /> : null}
    </div>
  );
};

export default SelectField;
