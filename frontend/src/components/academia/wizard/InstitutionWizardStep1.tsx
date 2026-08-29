import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';

import RichTextEditor from '../../ui/rich-text-editor';
import { WEB_LINK_TYPES } from '../../../constants/contactTypes';
import { primaryWebUrl } from '../../../schemas/contactEntry';
import { PHONE_LOCAL_PLACEHOLDER } from '../../../utils/phoneCountry';
import {
  useEmailContactTypeOptions,
  usePhoneContactTypeOptions,
} from '../../../hooks/useContactTypeOptions';
import {
  CURRENCY_OPTIONS,
  INSTITUTION_PROFILE_TEXT_FIELDS,
  institutionTypeSelectOptions,
  institutionToApiPayload,
  normalizeWizardInstitution,
  RANKING_TIER_OPTIONS,
  wizardInstitutionSchema,
  type WizardInstitutionFormValues,
} from '../../../schemas/wizard/step1-institution';
import { CharCountInput, FieldHint } from '../form/CharCountField';
import LabeledContactListField from '../form/LabeledContactListField';
import SelectField from '../form/SelectField';
import SearchableSelect from '../SearchableSelect';
import WizardFieldError from './form/WizardFieldError';
import type { WizardStepHandle } from './form/wizardStepRef';
import { useWizardListStepDefaultsSync, useWizardStepSnapshot } from './form/wizardDirtyTracking';
import { wizardAddressRowClass, wizardContactRowClass, wizardDenseGridClass, wizardInputClass, wizardLabelClass, wizardNamingFieldClass, wizardNamingRowClass, wizardProfileRowClass, wizardSectionClass, wizardSectionTitleClass, wizardStackClass } from './form/wizardFormStyles';
import type { InstitutionTypeRecord } from '../../../types/institutionTypes';
import { fetchInstitutionTypes } from '../../../types/institutionTypes';
import ReadOnlyIdField from '../ReadOnlyIdField';
import {
  geographyCountriesToPhoneCountries,
  resolveGeographyCountryIso2,
  type GeographyCountry,
} from '../../../types/geography';

interface GeographyOption {
  id: number;
  name: string;
}

interface InstitutionWizardStep1Props {
  defaultValues: WizardInstitutionFormValues;
  institutionId?: number | null;
  countries: GeographyCountry[];
  states: GeographyOption[];
  cities: GeographyOption[];
  onCountryChange: (countryId: number | null) => void;
  onStateChange: (stateId: number | null) => void;
}

const YesNoRadio: React.FC<{
  name: string;
  label: string;
  hint: string;
  value: boolean | null;
  onChange: (value: boolean | null) => void;
  error?: string;
}> = ({ name, label, hint, value, onChange, error }) => (
  <fieldset className={`space-y-1 text-sm ${error ? 'rounded-xl ring-1 ring-alert/20' : ''}`}>
    <legend className={wizardLabelClass}>{label}</legend>
    <div className="flex flex-wrap gap-3">
      <label className="inline-flex items-center gap-1.5">
        <input
          type="radio"
          name={name}
          checked={value === true}
          onChange={() => onChange(true)}
          className="accent-accent"
        />
        <span>Yes</span>
      </label>
      <label className="inline-flex items-center gap-1.5">
        <input
          type="radio"
          name={name}
          checked={value === false}
          onChange={() => onChange(false)}
          className="accent-accent"
        />
        <span>No</span>
      </label>
    </div>
    <FieldHint hint={hint} />
    <WizardFieldError message={error} />
  </fieldset>
);

const InstitutionWizardStep1 = forwardRef<
  WizardStepHandle<WizardInstitutionFormValues>,
  InstitutionWizardStep1Props
>(({ defaultValues, institutionId = null, countries, states, cities, onCountryChange, onStateChange }, ref) => {
  const [institutionTypes, setInstitutionTypes] = useState<InstitutionTypeRecord[]>([]);

  useEffect(() => {
    let cancelled = false;
    void fetchInstitutionTypes()
      .then(data => {
        if (!cancelled) setInstitutionTypes(data);
      })
      .catch(() => {
        if (!cancelled) setInstitutionTypes([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const institutionTypeOptions = useMemo(
    () => institutionTypeSelectOptions(institutionTypes),
    [institutionTypes]
  );

  const form = useForm<WizardInstitutionFormValues>({
    resolver: zodResolver(wizardInstitutionSchema),
    defaultValues: normalizeWizardInstitution(defaultValues),
    mode: 'onSubmit',
    shouldUnregister: false,
  });

  const {
    control,
    register,
    reset,
    getValues,
    trigger,
    watch,
    setValue,
    formState: { errors },
  } = form;

  const getSnapshot = useCallback(
    () => institutionToApiPayload(normalizeWizardInstitution(getValues())),
    [getValues]
  );
  const { markClean, isDirty } = useWizardStepSnapshot(getSnapshot);

  useWizardListStepDefaultsSync(
    defaultValues,
    () => reset(normalizeWizardInstitution(defaultValues)),
    markClean
  );

  const countryId = watch('country_id');

  const phoneCountries = useMemo(() => geographyCountriesToPhoneCountries(countries), [countries]);
  const phoneContactTypes = usePhoneContactTypeOptions();
  const emailContactTypes = useEmailContactTypeOptions();
  const defaultPhoneCountryIso2 = useMemo(
    () => resolveGeographyCountryIso2(countries, countryId),
    [countries, countryId]
  );

  useImperativeHandle(ref, () => ({
    validate: async () => trigger(),
    getValues: () => institutionToApiPayload(normalizeWizardInstitution(getValues())),
    getFormValues: () => {
      const live = getValues();
      return normalizeWizardInstitution({
        ...live,
        web_links: live.web_links,
        institution_web_url: primaryWebUrl(live.web_links || []),
      });
    },
    reset: values => {
      reset(normalizeWizardInstitution(values));
      markClean();
    },
    isDirty,
    markClean,
  }));

  const countryOptions = countries.map(c => ({ value: String(c.id), label: c.name }));
  const stateOptions = states.map(s => ({ value: String(s.id), label: s.name }));
  const cityOptions = cities.map(c => ({ value: String(c.id), label: c.name }));

  const phoneFieldErrors = (watch('phone_numbers') || []).map((_, index) => {
    const row = errors.phone_numbers?.[index] as
      | { value?: { message?: string }; type?: { message?: string } }
      | undefined;
    return (
      row?.value?.message ||
      row?.type?.message ||
      (index === 0 ? (errors.phone_numbers as { message?: string } | undefined)?.message : undefined)
    );
  });

  const faxFieldErrors = (watch('fax_numbers') || []).map((_, index) => {
    const row = errors.fax_numbers?.[index] as
      | { value?: { message?: string }; type?: { message?: string } }
      | undefined;
    return (
      row?.value?.message ||
      row?.type?.message ||
      (index === 0 ? (errors.fax_numbers as { message?: string } | undefined)?.message : undefined)
    );
  });

  const emailFieldErrors = (watch('email_addresses') || []).map((_, index) => {
    const row = errors.email_addresses?.[index] as
      | { value?: { message?: string }; type?: { message?: string } }
      | undefined;
    return (
      row?.value?.message ||
      row?.type?.message ||
      (index === 0
        ? (errors.email_addresses as { message?: string } | undefined)?.message
        : undefined)
    );
  });

  const webLinkFieldErrors = (watch('web_links') || []).map((_, index) => {
    const row = errors.web_links?.[index] as
      | { value?: { message?: string }; type?: { message?: string } }
      | undefined;
    return row?.value?.message || row?.type?.message;
  });

  return (
    <div className={wizardStackClass}>
      <section className={wizardSectionClass}>
        <h3 className={wizardSectionTitleClass}>Institution profile</h3>
        <div className={wizardDenseGridClass}>
          <div className={wizardProfileRowClass}>
            {institutionId ? (
              <ReadOnlyIdField aligned label="Institution ID" value={institutionId} />
            ) : null}
            <Controller
              control={control}
              name="institution_type_id"
              render={({ field, fieldState }) => (
                <div>
                  <SelectField
                    label="Institution type"
                    required
                    value={field.value ? String(field.value) : ''}
                    onChange={value => field.onChange(value ? Number(value) : 0)}
                    placeholder="Select institution type..."
                    options={institutionTypeOptions}
                  />
                  <WizardFieldError message={fieldState.error?.message} />
                </div>
              )}
            />

            <Controller
              control={control}
              name="ranking_tier_global"
              render={({ field }) => (
                <SelectField
                  label="Ranking tier (global)"
                  value={field.value || ''}
                  onChange={field.onChange}
                  placeholder="Select ranking tier..."
                  options={[...RANKING_TIER_OPTIONS]}
                />
              )}
            />

            <Controller
              control={control}
              name="currency_type"
              render={({ field }) => (
                <SelectField
                  label="Currency type"
                  value={field.value || 'USD'}
                  onChange={field.onChange}
                  placeholder="Select currency..."
                  options={[...CURRENCY_OPTIONS]}
                />
              )}
            />

            <Controller
              control={control}
              name="company_affiliated"
              render={({ field, fieldState }) => (
                <YesNoRadio
                  name="company_affiliated"
                  label="Company affiliated"
                  hint="Example: Yes (if corporate-backed)"
                  value={field.value ?? null}
                  onChange={field.onChange}
                  error={fieldState.error?.message}
                />
              )}
            />
            <Controller
              control={control}
              name="ad_promotion_flag"
              render={({ field, fieldState }) => (
                <YesNoRadio
                  name="ad_promotion_flag"
                  label="AD promotion flag"
                  hint="Example: No (unless in paid campaigns)"
                  value={field.value ?? null}
                  onChange={field.onChange}
                  error={fieldState.error?.message}
                />
              )}
            />
          </div>

          <div className={wizardNamingRowClass}>
            <div className={wizardNamingFieldClass}>
              <CharCountInput
                label="Institution short name / code"
                maxLength={50}
                showMaxInLabel={false}
                value={watch('code') || ''}
                onChange={value => form.setValue('code', value || null)}
                placeholder="e.g. MIT"
                hint="Example: UCLA"
              />
            </div>

            <div className={wizardNamingFieldClass}>
              <label className={wizardLabelClass}>Institution long name *</label>
              <input
                {...register('name')}
                className={wizardInputClass(Boolean(errors.name))}
                placeholder="e.g. Massachusetts Institute of Technology"
              />
              <WizardFieldError message={errors.name?.message} />
            </div>

            <div className={wizardNamingFieldClass}>
              <CharCountInput
                label="Dean's name"
                maxLength={255}
                value={watch('dean_name') || ''}
                onChange={value => form.setValue('dean_name', value || null)}
                placeholder="e.g. Dr. Jane Smith"
                hint="Optional — primary dean or academic lead"
              />
            </div>

            <div className={wizardNamingFieldClass}>
              <CharCountInput
                label="Students count"
                maxLength={250}
                value={watch('students_count') || ''}
                onChange={value => form.setValue('students_count', value || null)}
                placeholder="e.g. 18,500 undergraduate and 9,200 graduate students"
                hint="Example: 25,000 total enrolled students"
              />
            </div>
          </div>

          <div className="col-span-full grid grid-cols-1 gap-x-3 gap-y-2.5 md:grid-cols-2">
            <Controller
              control={control}
              name="short_description"
              render={({ field, fieldState }) => (
                <RichTextEditor
                  label="Institution short description"
                  content={field.value || ''}
                  onChange={field.onChange}
                  maxLength={2500}
                  placeholder="Brief overview for listings and search cards."
                  hint="Example: A leading public research university on the US West Coast."
                  error={fieldState.error?.message}
                />
              )}
            />

            <Controller
              control={control}
              name="accreditation_details"
              render={({ field, fieldState }) => (
                <RichTextEditor
                  label="Accreditation details"
                  content={field.value || ''}
                  onChange={field.onChange}
                  maxLength={2500}
                  placeholder="e.g. WASC Senior College and University Commission (WSCUC)"
                  hint="Example: Accredited by the Higher Learning Commission (HLC)."
                  error={fieldState.error?.message}
                />
              )}
            />
          </div>
        </div>
      </section>

      <section className={wizardSectionClass}>
        <h3 className={wizardSectionTitleClass}>Rankings, brochure &amp; expenses</h3>
        <div className={wizardDenseGridClass}>
          {[
            INSTITUTION_PROFILE_TEXT_FIELDS.slice(0, 6),
            INSTITUTION_PROFILE_TEXT_FIELDS.slice(6, 12),
          ].map((row, rowIndex) => (
            <div key={rowIndex} className={wizardProfileRowClass}>
              {row.map(field => (
                <CharCountInput
                  key={field.key}
                  label={field.label}
                  maxLength={2000}
                  type={'type' in field ? field.type : 'text'}
                  value={watch(field.key) || ''}
                  onChange={value => form.setValue(field.key, value || null)}
                  placeholder={field.placeholder}
                  hint={'hint' in field ? field.hint : undefined}
                />
              ))}
            </div>
          ))}
        </div>
      </section>

      <section className={wizardSectionClass}>
        <h3 className={wizardSectionTitleClass}>Location &amp; contact</h3>
        <div className={wizardDenseGridClass}>
          <div className={wizardAddressRowClass}>
            <div className="md:min-w-0 md:flex-[1.75]">
              <CharCountInput
                label="Address"
                maxLength={200}
                value={watch('address') || ''}
                onChange={value => setValue('address', value || null)}
                placeholder="Street address, building, or main campus location"
              />
              <WizardFieldError message={errors.address?.message} />
            </div>

            <Controller
              control={control}
              name="country_id"
              render={({ field, fieldState }) => (
                <div className="md:min-w-0 md:flex-1">
                  <SearchableSelect
                    label="Country"
                    value={field.value ? String(field.value) : ''}
                    options={countryOptions}
                    onChange={value => {
                      const nextCountryId = value ? Number(value) : 0;
                      field.onChange(nextCountryId);
                      onCountryChange(nextCountryId || null);
                      form.setValue('state_id', 0);
                      form.setValue('city_id', 0);
                    }}
                    placeholder="Search countries, e.g. United States"
                    hint="Example: United States"
                    required
                  />
                  <WizardFieldError message={fieldState.error?.message} />
                </div>
              )}
            />

            <Controller
              control={control}
              name="state_id"
              render={({ field, fieldState }) => (
                <div className="md:min-w-0 md:flex-1">
                  <SearchableSelect
                    label="State"
                    value={field.value ? String(field.value) : ''}
                    options={stateOptions}
                    onChange={value => {
                      const nextStateId = value ? Number(value) : 0;
                      field.onChange(nextStateId);
                      onStateChange(nextStateId || null);
                      form.setValue('city_id', 0);
                    }}
                    placeholder="Search states, e.g. California"
                    disabled={!countryId}
                    hint="Example: California"
                    required
                  />
                  <WizardFieldError message={fieldState.error?.message} />
                </div>
              )}
            />

            <Controller
              control={control}
              name="city_id"
              render={({ field, fieldState }) => (
                <div className="md:min-w-0 md:flex-1">
                  <SearchableSelect
                    label="City"
                    value={field.value ? String(field.value) : ''}
                    options={cityOptions}
                    onChange={value => field.onChange(value ? Number(value) : 0)}
                    placeholder="Search cities, e.g. Boston"
                    disabled={!countryId}
                    hint="Example: Boston"
                    required
                  />
                  <WizardFieldError message={fieldState.error?.message} />
                </div>
              )}
            />

            <div className="md:min-w-0 md:flex-1">
              <CharCountInput
                label="Zipcode"
                maxLength={10}
                value={watch('zipcode') || ''}
                onChange={value => form.setValue('zipcode', value || null)}
                placeholder="e.g. 02139"
                hint="Example: 94305"
              />
            </div>
          </div>

          <div className={wizardContactRowClass}>
            <Controller
              control={control}
              name="phone_numbers"
              render={({ field }) => (
                <LabeledContactListField
                  label="Phone numbers"
                  items={field.value}
                  onChange={field.onChange}
                  typeOptions={phoneContactTypes}
                  valuePlaceholder={PHONE_LOCAL_PLACEHOLDER}
                  valueInputType="tel"
                  addLabel="Add phone number"
                  errors={phoneFieldErrors}
                  phoneCountries={phoneCountries}
                  defaultPhoneCountryIso2={defaultPhoneCountryIso2}
                  fullWidth={false}
                />
              )}
            />

            <Controller
              control={control}
              name="fax_numbers"
              render={({ field }) => (
                <LabeledContactListField
                  label="Fax numbers"
                  items={field.value}
                  onChange={field.onChange}
                  typeOptions={phoneContactTypes}
                  valuePlaceholder={PHONE_LOCAL_PLACEHOLDER}
                  valueInputType="tel"
                  addLabel="Add fax number"
                  errors={faxFieldErrors}
                  phoneCountries={phoneCountries}
                  defaultPhoneCountryIso2={defaultPhoneCountryIso2}
                  fullWidth={false}
                />
              )}
            />

            <Controller
              control={control}
              name="email_addresses"
              render={({ field }) => (
                <LabeledContactListField
                  label="Email addresses"
                  items={field.value}
                  onChange={field.onChange}
                  typeOptions={emailContactTypes}
                  valuePlaceholder="info@university.edu"
                  valueInputType="email"
                  addLabel="Add email address"
                  errors={emailFieldErrors}
                  typeSelectWidthClass="w-full sm:w-[9.5rem]"
                  fullWidth={false}
                />
              )}
            />
          </div>

          <div className="col-span-full">
            <Controller
              control={control}
              name="web_links"
              render={({ field }) => (
                <LabeledContactListField
                  label="Institution web URLs"
                  items={field.value}
                  onChange={field.onChange}
                  typeOptions={WEB_LINK_TYPES}
                  valuePlaceholder="https://www.university.edu"
                  valueInputType="url"
                  addLabel="Add web links"
                  errors={webLinkFieldErrors}
                  typeSelectWidthClass="w-full sm:w-[8.75rem]"
                  maxLength={250}
                  fullWidth
                  showViewWebsiteLink
                />
              )}
            />
          </div>
        </div>
      </section>

    </div>
  );
});

InstitutionWizardStep1.displayName = 'InstitutionWizardStep1';

export default InstitutionWizardStep1;
