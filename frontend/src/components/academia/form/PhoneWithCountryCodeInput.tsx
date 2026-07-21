import { useMemo, useState } from 'react';

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
}

const fieldClass = (hasError: boolean) =>
  `w-full rounded-xl border bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent ${
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

  return (
    <div className="space-y-1 text-sm md:col-span-2">
      <span className={wizardLabelClass}>
        {label}
        {required ? ' *' : ''}
      </span>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <select
          value={countryIso2}
          onChange={event => {
            const localValue = isFocused ? draftLocal : parsed.localNumber;
            commitPhone(event.target.value, localValue);
          }}
          className={`w-full shrink-0 rounded-xl border bg-surface-bg px-1.5 py-2 text-sm outline-none focus:border-accent sm:w-[5.25rem] ${
            error ? 'border-alert ring-1 ring-alert/20' : 'border-border-subtle'
          }`}
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
          type="tel"
          inputMode="text"
          autoComplete="tel-national"
          autoCapitalize="characters"
          spellCheck={false}
          value={displayLocalNumber}
          onFocus={() => {
            setIsFocused(true);
            setDraftLocal(parsed.localNumber);
          }}
          onBlur={() => {
            commitPhone(countryIso2, draftLocal);
            setIsFocused(false);
          }}
          onChange={event => {
            setDraftLocal(sanitizePhoneLocalDraft(event.target.value));
          }}
          placeholder={placeholder}
          className={`${fieldClass(Boolean(error))} min-w-0 flex-1`}
        />
      </div>
      {hint ? <p className="text-xs text-text-muted">{hint}</p> : null}
      <WizardFieldError message={error} />
    </div>
  );
};

export default PhoneWithCountryCodeInput;
