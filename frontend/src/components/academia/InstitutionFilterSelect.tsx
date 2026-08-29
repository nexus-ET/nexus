import SearchableMultiSelect from './SearchableMultiSelect';
import SearchableSelect, { type SearchableSelectOption } from './SearchableSelect';
import { shouldUseMultiSelect } from '../../utils/filterParams';

interface InstitutionFilterSelectProps {
  label: string;
  singleValue: string;
  multiValues: string[];
  options: SearchableSelectOption[];
  onSingleChange: (value: string) => void;
  onMultiChange: (values: string[]) => void;
  placeholder?: string;
  allLabel?: string;
  disabled?: boolean;
  onOpen?: () => void;
  emptyMessage?: string;
}

const InstitutionFilterSelect: React.FC<InstitutionFilterSelectProps> = ({
  label,
  singleValue,
  multiValues,
  options,
  onSingleChange,
  onMultiChange,
  placeholder,
  allLabel,
  disabled = false,
  onOpen,
  emptyMessage,
}) => {
  const realOptions = options.filter(option => option.value !== '');
  const useMulti = shouldUseMultiSelect(realOptions);
  const resolvedPlaceholder = placeholder || allLabel || `All ${label.toLowerCase()}`;

  if (useMulti) {
    return (
      <SearchableMultiSelect
        label={label}
        values={multiValues}
        options={realOptions}
        onChange={onMultiChange}
        placeholder={resolvedPlaceholder}
        selectedDisplay={
          multiValues.length ? `${multiValues.length} selected` : resolvedPlaceholder
        }
        disabled={disabled}
        emptyMessage={emptyMessage}
        onOpen={onOpen}
      />
    );
  }

  return (
    <SearchableSelect
      label={label}
      value={singleValue}
      options={[{ value: '', label: allLabel || resolvedPlaceholder }, ...realOptions]}
      onChange={onSingleChange}
      placeholder={resolvedPlaceholder}
      disabled={disabled}
      emptyMessage={emptyMessage}
      onOpen={onOpen}
    />
  );
};

export default InstitutionFilterSelect;
