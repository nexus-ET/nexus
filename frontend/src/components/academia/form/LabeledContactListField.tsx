import { Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';

import type { CountryRecord } from '../../../types/country';
import { FALLBACK_COUNTRIES } from '../../../types/country';
import type { ContactEntry } from '../../../schemas/contactEntry';
import {
  formatFullPhone,
  formatPhoneCountryLabel,
  normalizeLocalPhoneDigits,
  parseStoredPhone,
  sanitizePhoneLocalDraft,
  EMAIL_FORMAT_HINT,
  PHONE_LOCAL_PLACEHOLDER,
  PHONE_LOCAL_REQUIREMENTS,
} from '../../../utils/phoneCountry';
import WizardFieldError from '../wizard/form/WizardFieldError';
import { wizardLabelClass } from '../wizard/form/wizardFormStyles';

interface ContactTypeOption {
  value: string;
  label: string;
}

interface LabeledContactListFieldProps {
  label: string;
  items: ContactEntry[];
  typeOptions: readonly ContactTypeOption[];
  onChange: (items: ContactEntry[]) => void;
  valuePlaceholder: string;
  valueInputType?: 'text' | 'email' | 'tel' | 'url';
  addLabel: string;
  errors?: Array<string | undefined>;
  required?: boolean;
  disabled?: boolean;
  phoneCountries?: CountryRecord[];
  defaultPhoneCountryIso2?: string;
  fullWidth?: boolean;
  /** Override type select width (default fits short phone/email labels). */
  typeSelectWidthClass?: string;
  maxLength?: number;
}

const fieldClass = (hasError: boolean, disabled = false) =>
  `w-full rounded-xl border bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent ${
    hasError ? 'border-alert ring-1 ring-alert/20' : 'border-border-subtle'
  } ${disabled ? 'cursor-not-allowed opacity-70' : ''}`;

/** Compact selects for type + dial code — leave room for the number input. */
const compactSelectClass = (hasError: boolean, disabled = false, widthClass: string) =>
  `${widthClass} shrink-0 rounded-xl border bg-surface-bg px-1.5 py-2 text-sm outline-none focus:border-accent ${
    hasError ? 'border-alert ring-1 ring-alert/20' : 'border-border-subtle'
  } ${disabled ? 'cursor-not-allowed opacity-70' : ''}`;

const LabeledContactListField: React.FC<LabeledContactListFieldProps> = ({
  label,
  items,
  typeOptions,
  onChange,
  valuePlaceholder,
  valueInputType = 'text',
  addLabel,
  errors = [],
  required = false,
  disabled = false,
  phoneCountries,
  defaultPhoneCountryIso2 = '',
  fullWidth = true,
  typeSelectWidthClass = 'w-full sm:w-[6.75rem]',
  maxLength,
}) => {
  const countries = phoneCountries?.length ? phoneCountries : FALLBACK_COUNTRIES;
  const usePhoneCountryPicker = valueInputType === 'tel' && Boolean(phoneCountries?.length);
  const phonePlaceholder = valuePlaceholder || PHONE_LOCAL_PLACEHOLDER;
  const [focusedPhoneIndex, setFocusedPhoneIndex] = useState<number | null>(null);
  const [draftLocalByIndex, setDraftLocalByIndex] = useState<Record<number, string>>({});
  const rows =
    Array.isArray(items) && items.length > 0
      ? items
      : [{ type: typeOptions[0]?.value || 'Other', value: '' }];

  const updateItem = (index: number, patch: Partial<ContactEntry>) => {
    onChange(rows.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)));
  };

  const commitPhoneItem = (index: number, countryIso2: string, localNumber: string) => {
    const iso2 = countryIso2 || defaultPhoneCountryIso2;
    const normalizedLocal = normalizeLocalPhoneDigits(localNumber, iso2, countries);
    if (!normalizedLocal) {
      updateItem(index, { value: '' });
      return;
    }
    if (!iso2) {
      updateItem(index, { value: normalizedLocal });
      return;
    }
    updateItem(index, {
      value: formatFullPhone(iso2, normalizedLocal, countries),
    });
  };

  const removeItem = (index: number) => {
    if (rows.length <= 1) {
      onChange([{ type: rows[0]?.type || typeOptions[0]?.value || 'Other', value: '' }]);
      return;
    }
    onChange(rows.filter((_, itemIndex) => itemIndex !== index));
  };

  return (
    <div className={`space-y-1.5 text-sm ${fullWidth ? 'md:col-span-2 xl:col-span-3' : ''}`}>
      <span className={wizardLabelClass}>
        {label}
        {required ? ' *' : ''}
      </span>
      <div className="space-y-1.5">
        {rows.map((item, index) => {
          const parsedPhone = usePhoneCountryPicker
            ? parseStoredPhone(item.value, countries)
            : { countryIso2: '', localNumber: '' };
          const phoneCountryIso2 = parsedPhone.countryIso2 || defaultPhoneCountryIso2;
          const isFocused = focusedPhoneIndex === index;
          const displayLocalNumber = isFocused
            ? (draftLocalByIndex[index] ?? parsedPhone.localNumber)
            : parsedPhone.localNumber;

          return (
            <div key={`${item.type}-${index}`} className="space-y-0.5">
              <div className="flex flex-col gap-1.5 sm:flex-row sm:items-center">
                <select
                  value={item.type}
                  disabled={disabled}
                  onChange={event => updateItem(index, { type: event.target.value })}
                  className={compactSelectClass(Boolean(errors[index]), disabled, typeSelectWidthClass)}
                >
                  {typeOptions.map(option => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>

                {usePhoneCountryPicker ? (
                  <>
                    <select
                      value={phoneCountryIso2}
                      disabled={disabled}
                      onChange={event => {
                        const nextIso2 = event.target.value;
                        const localValue =
                          focusedPhoneIndex === index
                            ? (draftLocalByIndex[index] ?? parsedPhone.localNumber)
                            : parsedPhone.localNumber;
                        commitPhoneItem(index, nextIso2, localValue);
                      }}
                      className={compactSelectClass(Boolean(errors[index]), disabled, 'w-full sm:w-[5.25rem]')}
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
                      disabled={disabled}
                      onFocus={() => {
                        if (disabled) return;
                        setFocusedPhoneIndex(index);
                        setDraftLocalByIndex(prev => ({
                          ...prev,
                          [index]: parsedPhone.localNumber,
                        }));
                      }}
                      onBlur={() => {
                        const draft = draftLocalByIndex[index] ?? parsedPhone.localNumber;
                        commitPhoneItem(index, phoneCountryIso2, draft);
                        setFocusedPhoneIndex(current => (current === index ? null : current));
                        setDraftLocalByIndex(prev => {
                          const next = { ...prev };
                          delete next[index];
                          return next;
                        });
                      }}
                      onChange={event => {
                        const nextLocal = sanitizePhoneLocalDraft(event.target.value);
                        setDraftLocalByIndex(prev => ({ ...prev, [index]: nextLocal }));
                      }}
                      placeholder={phonePlaceholder}
                      className={`${fieldClass(Boolean(errors[index]), disabled)} min-w-0 flex-1`}
                    />
                  </>
                ) : (
                  <input
                    type={valueInputType}
                    value={item.value}
                    disabled={disabled}
                    maxLength={maxLength}
                    onChange={event => updateItem(index, { value: event.target.value })}
                    placeholder={valuePlaceholder}
                    className={`${fieldClass(Boolean(errors[index]), disabled)} min-w-0 flex-1`}
                  />
                )}

                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => removeItem(index)}
                  className="inline-flex items-center justify-center rounded-lg border border-border-subtle px-2.5 py-2 text-alert hover:bg-alert/10 disabled:opacity-40"
                  aria-label={`Remove ${label.toLowerCase()} row`}
                >
                  <Trash2 size={16} />
                </button>
              </div>
              <WizardFieldError message={errors[index]} />
            </div>
          );
        })}
      </div>
      {usePhoneCountryPicker ? (
        <p className="text-xs text-text-muted">{PHONE_LOCAL_REQUIREMENTS}</p>
      ) : null}
      {valueInputType === 'email' ? (
        <p className="text-xs text-text-muted">{EMAIL_FORMAT_HINT}</p>
      ) : null}
      {!disabled ? (
        <button
          type="button"
          onClick={() =>
            onChange([...rows, { type: typeOptions[0]?.value || 'Other', value: '' }])
          }
          className="inline-flex items-center gap-1 text-xs font-semibold text-accent"
        >
          <Plus size={14} />
          {addLabel}
        </button>
      ) : null}
    </div>
  );
};

export default LabeledContactListField;
