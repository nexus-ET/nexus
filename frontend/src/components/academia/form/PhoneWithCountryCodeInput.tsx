import { useMemo, useState, type ReactNode } from 'react';

import type { CountryRecord } from '../../../types/country';
import { FALLBACK_COUNTRIES } from '../../../types/country';
import {
  formatFullPhone,
  formatPhoneCountryLabel,
  normalizeLocalPhoneDigits,
  parseStoredPhone,
  sanitizePhoneLocalDraft,
  PHONE_LOCAL_PLACEHOLDER,
  PHONE_LOCAL_REQUIREMENTS,
} from '../../../utils/phoneCountry';
import WizardFieldError from '../wizard/form/WizardFieldError';
import { wizardLabelClass } from '../wizard/form/wizardFormStyles';

interface PhoneWithCountryCodeInputProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  countries?: CountryRecord[];
  defaultCountryIso2?: string;
  required?: boolean;
  error?: string;
  placeholder?: string;
  hint?: string;
  className?: string;
  /** Optional control rendered opposite the label (e.g. Active/Inactive). */
  headerRight?: ReactNode;
  id?: string;
  /** When true, omit the built-in label (caller renders label for row alignment). */
  hideLabel?: boolean;
  disabled?: boolean;
}

const controlClass = (hasError: boolean) =>
  `box-border h-10 w-full border bg-surface-bg text-sm leading-none outline-none focus:border-accent ${
    hasError ? 'border-alert ring-1 ring-alert/20' : 'border-border-subtle'
  }`;

const PhoneWithCountryCodeInput: React.FC<PhoneWithCountryCodeInputProps> = ({
  label,
  value,
  onChange,
  countries = FALLBACK_COUNTRIES,
  defaultCountryIso2 = '',
  required = false,
  error,
  placeholder = PHONE_LOCAL_PLACEHOLDER,
  hint = PHONE_LOCAL_REQUIREMENTS,
  className = 'space-y-1 text-sm md:col-span-2',
  headerRight,
  id,
  hideLabel = false,
  disabled = false,
}) => {
  const parsed = useMemo(() => parseStoredPhone(value, countries), [countries, value]);
  const countryIso2 = parsed.countryIso2 || defaultCountryIso2;
  const [isFocused, setIsFocused] = useState(false);
  const [draftLocal, setDraftLocal] = useState('');

  const displayLocalNumber = isFocused ? draftLocal : parsed.localNumber;

  const commitPhone = (nextIso2: string, nextLocal: string) => {
    const iso2 = nextIso2 || defaultCountryIso2;
    const normalizedLocal = normalizeLocalPhoneDigits(nextLocal, iso2, countries);
    if (!normalizedLocal) {
      onChange('');
      return;
    }
    if (!iso2) {
      onChange(normalizedLocal);
      return;
    }
    onChange(formatFullPhone(iso2, normalizedLocal, countries));
  };

  const showLabel = !hideLabel && Boolean(label);

  return (
    <div className={className}>
      {showLabel || headerRight ? (
        <div className="flex min-h-7 flex-wrap items-center justify-between gap-2">
          {showLabel ? (
            <label htmlFor={id || 'phone-local'} className={wizardLabelClass}>
              {label}
              {required ? ' *' : ''}
            </label>
          ) : (
            <span />
          )}
          {headerRight ? <div className="shrink-0">{headerRight}</div> : null}
        </div>
      ) : null}
      <div
        className={`${showLabel || headerRight ? 'mt-1.5' : ''} flex flex-col gap-2 sm:flex-row sm:items-stretch`}
      >        <select
          id={id ? `${id}-country` : undefined}
          name={id ? `${id}-country` : 'phone-country'}
          value={countryIso2}
          disabled={disabled}
          onChange={event => {
            const localValue = isFocused ? draftLocal : parsed.localNumber;
            commitPhone(event.target.value, localValue);
          }}
          className={`${controlClass(Boolean(error))} shrink-0 rounded-xl px-1.5 sm:w-[5.25rem] disabled:cursor-not-allowed disabled:opacity-70`}
          aria-label={`${label} country code`}
        >
          <option value="">Code</option>
          {countries.map(country => (
            <option key={country.iso2} value={country.iso2}>
              {formatPhoneCountryLabel(country)}
            </option>
          ))}
        </select>
        <input
          id={id || 'phone-local'}
          name={id || 'phone-local'}
          type="tel"
          inputMode="text"
          autoComplete="tel-national"
          autoCapitalize="characters"
          spellCheck={false}
          disabled={disabled}
          value={displayLocalNumber}
          onFocus={() => {
            if (disabled) return;
            setIsFocused(true);
            setDraftLocal(parsed.localNumber);
          }}
          onBlur={() => {
            if (disabled) return;
            commitPhone(countryIso2, draftLocal);
            setIsFocused(false);
          }}
          onChange={event => {
            setDraftLocal(sanitizePhoneLocalDraft(event.target.value));
          }}
          placeholder={placeholder}
          className={`${controlClass(Boolean(error))} min-w-0 flex-1 rounded-xl px-3 disabled:cursor-not-allowed disabled:opacity-70`}
        />
      </div>
      {hint ? <p className="mt-1 text-xs text-text-muted">{hint}</p> : null}
      <WizardFieldError message={error} />
    </div>
  );
};

export default PhoneWithCountryCodeInput;
