import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Loader2, Pencil, Save, Trash2 } from 'lucide-react';

import { apiFetch } from '../../../utils/api';
import { fetchAcademiaListItems } from '../../../utils/academiaList';
import { EMAIL_CONTACT_TYPES, FAX_CONTACT_TYPES, PHONE_CONTACT_TYPES, WEB_LINK_TYPES } from '../../../constants/contactTypes';
import { formatContactList, normalizeEmailContacts, normalizeFaxContacts, normalizePhoneContacts, normalizeWebLinks, serializeContacts } from '../../../schemas/contactEntry';
import { PHONE_LOCAL_PLACEHOLDER } from '../../../utils/phoneCountry';
import LabeledContactListField from '../form/LabeledContactListField';
import RichTextEditor from '../../ui/rich-text-editor';
import {
  campusToApiPayload,
  createEmptyWizardCampusDraft,
  emptyWizardCampusDraft,
  hydrateWizardCampus,
  wizardCampusDraftSchema,
  wizardCampusesStepSchema,
  type WizardCampusItem,
} from '../../../schemas/wizard/step2-campus';
import type { WizardInstitutionFormValues } from '../../../schemas/wizard/step1-institution';
import type { CampusTypeRecord } from '../../../types/campusTypes';
import { CharCountInput } from '../form/CharCountField';
import SelectField from '../form/SelectField';
import SearchableSelect from '../SearchableSelect';
import WizardFieldError from './form/WizardFieldError';
import type { WizardStepHandle } from './form/wizardStepRef';
import {
  flushFocusedFormControl,
  getWizardListStepSnapshot,
  useWizardListStepDefaultsSync,
  useWizardStepSnapshot,
} from './form/wizardDirtyTracking';
import { useConfirmation } from '../../../context/ConfirmationContext';
import EmptyListMessage from '../../ui/EmptyListMessage';
import {
  geographyCountriesToPhoneCountries,
  resolveGeographyCountryIso2,
  type GeographyCountry,
} from '../../../types/geography';
import { wizardContactRowClass, wizardDenseGridClass, wizardGeoRowClass, wizardLabelClass, wizardSectionClass, wizardSectionTitleClass, wizardStackClass } from './form/wizardFormStyles';

interface GeographyOption {
  id: number;
  name: string;
  iso2?: string;
  dial_code?: string;
}

interface CityLookupOption extends GeographyOption {
  country_id?: number;
  state_id?: number;
}

interface InstitutionWizardStep2Props {
  defaultCampuses: WizardCampusItem[];
  countries: GeographyCountry[];
  getInstitutionValues: () => WizardInstitutionFormValues;
  onSaveStep: (advance: boolean) => void;
  saving: boolean;
  /** When true, hide the step-level Save buttons (parent page owns save). */
  embedded?: boolean;
  /** When true, show a lock overlay and disable campus editing. */
  locked?: boolean;
  lockedMessage?: string;
}

const InstitutionWizardStep2 = forwardRef<
  WizardStepHandle<WizardCampusItem[]>,
  InstitutionWizardStep2Props
>(({ defaultCampuses, countries, getInstitutionValues, onSaveStep, saving, embedded = false, locked = false, lockedMessage }, ref) => {
  const openConfirm = useConfirmation();
  const [campuses, setCampuses] = useState<WizardCampusItem[]>(defaultCampuses);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [campusTypes, setCampusTypes] = useState<CampusTypeRecord[]>([]);
  const [loadingTypes, setLoadingTypes] = useState(true);
  const [typesError, setTypesError] = useState<string | null>(null);
  const [states, setStates] = useState<GeographyOption[]>([]);
  const [cities, setCities] = useState<GeographyOption[]>([]);
  const [lookupStates, setLookupStates] = useState<GeographyOption[]>([]);
  const [lookupCities, setLookupCities] = useState<CityLookupOption[]>([]);
  const [listError, setListError] = useState<string | null>(null);
  const [inheritInstitutionDetails, setInheritInstitutionDetails] = useState(false);

  const form = useForm({
    resolver: zodResolver(wizardCampusDraftSchema),
    defaultValues: createEmptyWizardCampusDraft(),
    mode: 'onSubmit',
    shouldUnregister: false,
  });

  const { control, reset, getValues, trigger, watch, setValue, formState: { errors } } = form;

  useEffect(() => {
    let cancelled = false;
    void apiFetch<CampusTypeRecord[]>('academia/campus-types')
      .then(data => {
        if (!cancelled) setCampusTypes(Array.isArray(data) ? data : []);
      })
      .catch(err => {
        if (!cancelled) {
          setTypesError(err instanceof Error ? err.message : 'Failed to load campus types');
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingTypes(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    void Promise.all([
      fetchAcademiaListItems<GeographyOption>('academia/states'),
      fetchAcademiaListItems<CityLookupOption>('academia/cities'),
    ])
      .then(([stateData, cityData]) => {
        if (cancelled) return;
        setLookupStates(stateData);
        setLookupCities(cityData);
      })
      .catch(() => {
        if (cancelled) return;
        setLookupStates([]);
        setLookupCities([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const loadStates = useCallback(async (countryId: number | null | undefined) => {
    if (!countryId) {
      setStates([]);
      return;
    }
    const data = await fetchAcademiaListItems<GeographyOption>('academia/states', {
      country_id: String(countryId),
    });
    setStates(data);
  }, []);

  const loadCities = useCallback(async (countryId: number | null | undefined, stateId: number | null | undefined) => {
    if (!countryId) {
      setCities([]);
      return;
    }
    const data = await fetchAcademiaListItems<GeographyOption>('academia/cities', {
      country_id: String(countryId),
      state_id: stateId ? String(stateId) : undefined,
    });
    setCities(data);
  }, []);

  const countryId = watch('country_id');
  const stateId = watch('state_id');

  useEffect(() => {
    void loadStates(countryId);
  }, [countryId, loadStates]);

  useEffect(() => {
    void loadCities(countryId, stateId);
  }, [countryId, stateId, loadCities]);

  const phoneCountries = useMemo(() => geographyCountriesToPhoneCountries(countries), [countries]);
  const defaultPhoneCountryIso2 = useMemo(
    () => resolveGeographyCountryIso2(countries, countryId),
    [countries, countryId]
  );

  const getSnapshot = useCallback(
    () =>
      getWizardListStepSnapshot(campuses, campusToApiPayload, {
        editingIndex,
        getDraft: () => getValues() as Record<string, unknown>,
        emptyDraftTemplate: emptyWizardCampusDraft as Record<string, unknown>,
      }),
    [campuses, editingIndex, getValues]
  );
  const { markClean, isDirty } = useWizardStepSnapshot(getSnapshot);

  useWizardListStepDefaultsSync(
    defaultCampuses,
    () => {
      setCampuses(defaultCampuses);
      reset(createEmptyWizardCampusDraft());
      setEditingIndex(null);
      setListError(null);
      setInheritInstitutionDetails(false);
    },
    markClean
  );

  useImperativeHandle(ref, () => ({
    validate: async () => {
      const parsed = wizardCampusesStepSchema.safeParse(campuses);
      if (!parsed.success) {
        setListError(parsed.error.issues[0]?.message || 'Add at least one campus.');
        return false;
      }
      setListError(null);
      return true;
    },
    getValues: () => campuses.map(campusToApiPayload),
    getCampusDrafts: () => campuses,
    reset: values => {
      setCampuses(values.map(item => hydrateWizardCampus(item)));
      resetDraftForm();
      markClean();
    },
    isDirty,
    markClean: () => {
      resetDraftForm();
      markClean();
    },
  }));

  const resetDraftForm = () => {
    reset(createEmptyWizardCampusDraft());
    setEditingIndex(null);
    setListError(null);
    setInheritInstitutionDetails(false);
  };

  const applyInstitutionDetails = () => {
    void flushFocusedFormControl().then(() => {
      const institution = getInstitutionValues();
      const inheritedWebLinks = normalizeWebLinks(
        institution.web_links,
        (institution as { institution_web_url?: string | null }).institution_web_url
      );
      const inheritedPhones = normalizePhoneContacts(institution.phone_numbers);
      const inheritedFaxes = normalizeFaxContacts(
        institution.fax_numbers,
        (institution as { fax_number?: string | null }).fax_number
      );
      const inheritedEmails = normalizeEmailContacts(institution.email_addresses);
      const current = getValues();

      // Use reset so Controller-bound array fields (including web_links) always re-render.
      reset(
        {
          ...current,
          address: institution.address || null,
          country_id: institution.country_id || undefined,
          state_id: institution.state_id || undefined,
          location_id: institution.city_id || undefined,
          zipcode: institution.zipcode || null,
          phone_numbers: inheritedPhones.map(entry => ({ ...entry })),
          fax_numbers: inheritedFaxes.map(entry => ({ ...entry })),
          email_addresses: inheritedEmails.map(entry => ({ ...entry })),
          web_links: inheritedWebLinks.map(entry => ({ ...entry })),
        },
        { keepDefaultValues: true }
      );
    });
  };

  const campusTypeOptions = useMemo(
    () => campusTypes.map(type => ({ value: String(type.id), label: `${type.name} (${type.code})` })),
    [campusTypes]
  );
  const countryOptions = useMemo(
    () => countries.map(country => ({ value: String(country.id), label: country.name })),
    [countries]
  );
  const stateOptions = useMemo(
    () => states.map(state => ({ value: String(state.id), label: state.name })),
    [states]
  );
  const cityOptions = useMemo(
    () => cities.map(city => ({ value: String(city.id), label: city.name })),
    [cities]
  );

  const handleSaveCampusToList = async () => {
    await flushFocusedFormControl();
    const valid = await trigger();
    if (!valid) return;
    const values = getValues();
    const selectedCityLabel =
      cityOptions.find(option => option.value === String(values.location_id))?.label || '';
    const selectedCountryLabel =
      countryOptions.find(option => option.value === String(values.country_id))?.label || '';
    const selectedStateLabel =
      stateOptions.find(option => option.value === String(values.state_id))?.label || '';
    const nextCampus = hydrateWizardCampus({
      ...values,
      local_id: values.local_id || crypto.randomUUID(),
      city_label: selectedCityLabel,
      country_label: selectedCountryLabel,
      state_label: selectedStateLabel,
    });
    if (editingIndex !== null) {
      setCampuses(prev => prev.map((item, index) => (index === editingIndex ? nextCampus : item)));
    } else {
      setCampuses(prev => [...prev, nextCampus]);
    }
    resetDraftForm();
  };

  const campusTypeName = (campusTypeId: number) =>
    campusTypes.find(type => type.id === campusTypeId)?.name || '—';

  const campusStateName = (campus: WizardCampusItem) =>
    lookupStates.find(state => state.id === campus.state_id)?.name ||
    states.find(state => state.id === campus.state_id)?.name ||
    '—';

  const campusCityName = (campus: WizardCampusItem) =>
    campus.city_label ||
    lookupCities.find(city => city.id === campus.location_id)?.name ||
    cities.find(city => city.id === campus.location_id)?.name ||
    '—';

  const formatListValues = (entries: { type: string; value: string }[]) => formatContactList(entries);

  const phoneFieldErrors = (watch('phone_numbers') || []).map((_, index) => {
    const row = errors.phone_numbers?.[index] as { value?: { message?: string }; type?: { message?: string } } | undefined;
    return row?.value?.message || row?.type?.message || (index === 0 ? (errors.phone_numbers as { message?: string } | undefined)?.message : undefined);
  });

  const faxFieldErrors = (watch('fax_numbers') || []).map((_, index) => {
    const row = errors.fax_numbers?.[index] as { value?: { message?: string }; type?: { message?: string } } | undefined;
    return row?.value?.message || row?.type?.message || (index === 0 ? (errors.fax_numbers as { message?: string } | undefined)?.message : undefined);
  });

  const emailFieldErrors = (watch('email_addresses') || []).map((_, index) => {
    const row = errors.email_addresses?.[index] as { value?: { message?: string }; type?: { message?: string } } | undefined;
    return row?.value?.message || row?.type?.message || (index === 0 ? (errors.email_addresses as { message?: string } | undefined)?.message : undefined);
  });

  const webLinkFieldErrors = (watch('web_links') || []).map((_, index) => {
    const row = errors.web_links?.[index] as
      | { value?: { message?: string }; type?: { message?: string } }
      | undefined;
    return row?.value?.message || row?.type?.message;
  });

  return (
    <div className={`relative ${wizardStackClass}`}>
      {locked ? (
        <div
          className="absolute inset-0 z-10 flex items-start justify-center rounded-2xl bg-surface-bg/70 p-4 backdrop-blur-[1px]"
          data-wizard-campus-lock
        >
          <div className="mt-4 max-w-md rounded-2xl border border-border-subtle bg-card px-4 py-3 text-center shadow-sm">
            <p className="text-sm font-semibold text-text-main">Campuses unlock after institution save</p>
            <p className="mt-1 text-sm text-text-muted">
              {lockedMessage ||
                'Save the institution profile above first. Then you can add one or more campuses here.'}
            </p>
          </div>
        </div>
      ) : null}

      <section className={`rounded-2xl border border-border-subtle bg-card p-4 ${locked ? 'pointer-events-none opacity-55' : ''}`}>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className={wizardSectionTitleClass}>Campuses</h3>
            <p className="-mt-2 text-sm text-text-muted">
              {locked
                ? 'This section stays disabled until the institution is saved.'
                : 'Saved campuses for this institution. Add at least one before continuing.'}
            </p>
          </div>
          <span className="rounded-full bg-surface-bg px-3 py-1 text-xs font-semibold text-text-muted">
            {campuses.length} campus{campuses.length === 1 ? '' : 'es'}
          </span>
        </div>
        <WizardFieldError message={listError || undefined} />

        {campuses.length === 0 ? (
          <EmptyListMessage message='No campuses added yet. Complete the form below and click "Add campus to list".' />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-surface-bg text-left text-sm font-bold text-text-main">
                <tr>
                  <th className="px-3 py-2">Campus Name</th>
                  <th className="px-3 py-2">Type</th>
                  <th className="px-3 py-2">State</th>
                  <th className="px-3 py-2">City</th>
                  <th className="px-3 py-2">Zipcode</th>
                  <th className="px-3 py-2">Phone</th>
                  <th className="px-3 py-2">Email ID</th>
                  <th className="px-3 py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {campuses.map((campus, index) => {
                  const isEditing = editingIndex === index;
                  return (
                  <tr
                    key={campus.local_id || index}
                    aria-selected={isEditing}
                    className={`border-t border-border-subtle/70 transition-colors ${
                      isEditing
                        ? 'bg-accent/10 ring-2 ring-inset ring-accent/40'
                        : 'hover:bg-surface-bg/60'
                    }`}
                  >
                    <td className="px-3 py-2 font-semibold text-text-main">
                      <span className="inline-flex flex-wrap items-center gap-2">
                        {campus.name}
                        {isEditing ? (
                          <span className="rounded-full bg-accent/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-accent">
                            Editing
                          </span>
                        ) : null}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-text-muted">{campusTypeName(campus.campus_type_id)}</td>
                    <td className="px-3 py-2 text-text-muted">{campusStateName(campus)}</td>
                    <td className="px-3 py-2 text-text-muted">{campusCityName(campus)}</td>
                    <td className="px-3 py-2 text-text-muted">{campus.zipcode || '—'}</td>
                    <td className="px-3 py-2 text-text-muted">{formatListValues(campus.phone_numbers)}</td>
                    <td className="px-3 py-2 text-text-muted">{formatListValues(campus.email_addresses)}</td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap gap-2">
                        {isEditing ? (
                          <button
                            type="button"
                            onClick={resetDraftForm}
                            className="inline-flex items-center gap-1 rounded-lg border border-border-subtle bg-card px-2 py-1 text-xs font-semibold text-text-muted hover:bg-surface-bg hover:text-text-main"
                          >
                            Cancel
                          </button>
                        ) : (
                          <button
                            type="button"
                            onClick={() => {
                              reset(hydrateWizardCampus(campus));
                              setEditingIndex(index);
                              setInheritInstitutionDetails(false);
                            }}
                            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-accent hover:bg-accent/10"
                          >
                            <Pencil size={14} />
                            Edit
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={async () => {
                            if (!(await openConfirm({
                              title: 'Remove campus?',
                              message: 'Delete this campus from the list?',
                              confirmLabel: 'Remove',
                              variant: 'warning',
                            }))) return;
                            setCampuses(prev => prev.filter((_, itemIndex) => itemIndex !== index));
                            if (editingIndex === index) resetDraftForm();
                          }}
                          className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-alert hover:bg-alert/10"
                        >
                          <Trash2 size={14} />
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className={`${wizardSectionClass} ${locked ? 'pointer-events-none opacity-55' : ''}`}>
        <h3 className={wizardSectionTitleClass}>Campus details</h3>
        <div className={wizardDenseGridClass}>
          <div className="md:col-span-2 xl:col-span-2">
            <CharCountInput
              label="Campus name"
              required
              maxLength={250}
              value={watch('name') || ''}
              onChange={value => setValue('name', value, { shouldValidate: true })}
              placeholder="e.g. Main Campus — Boston"
              hint="Example: North Campus or Downtown Medical Center"
            />
            <WizardFieldError message={errors.name?.message} />
          </div>

          {loadingTypes ? (
            <div className="flex items-center gap-2 text-sm text-text-muted">
              <Loader2 size={16} className="animate-spin" />
              Loading campus types...
            </div>
          ) : typesError ? (
            <div className="text-sm text-alert">{typesError}</div>
          ) : (
            <Controller
              control={control}
              name="campus_type_id"
              render={({ field, fieldState }) => (
                <div>
                  <SelectField
                    label="Campus type"
                    required
                    value={field.value ? String(field.value) : ''}
                    onChange={value => field.onChange(value ? Number(value) : undefined)}
                    placeholder="Select campus type..."
                    hint="Loaded from the campus_types lookup table"
                    options={campusTypeOptions}
                  />
                  <WizardFieldError message={fieldState.error?.message} />
                </div>
              )}
            />
          )}

          <div className="md:col-span-2 xl:col-span-3">
            <Controller
              control={control}
              name="description"
              render={({ field, fieldState }) => (
                <RichTextEditor
                  label="Campus description"
                  content={field.value || ''}
                  onChange={field.onChange}
                  maxLength={2000}
                  placeholder="Brief summary of this campus..."
                  error={fieldState.error?.message}
                />
              )}
            />
          </div>

          <div className="md:col-span-2 xl:col-span-3">
            <label className="flex cursor-pointer items-start gap-2 rounded-xl border border-border-subtle bg-card px-3 py-2">
              <input
                type="checkbox"
                checked={inheritInstitutionDetails}
                onChange={event => {
                  const checked = event.target.checked;
                  setInheritInstitutionDetails(checked);
                  if (checked) applyInstitutionDetails();
                }}
                className="mt-0.5 accent-accent"
              />
              <span>
                <span className="block text-sm font-semibold text-text-main">
                  Inherit institution address, contacts, and web URLs
                </span>
                <span className="block text-xs text-text-muted">
                  Copies address, country, state, city, zipcode, phone, fax, email, and web URLs.
                  You can edit the copied values below.
                </span>
              </span>
            </label>
          </div>

          <div className="md:col-span-2 xl:col-span-3">
            <CharCountInput
              label="Campus address"
              maxLength={200}
              value={watch('address') || ''}
              onChange={value => setValue('address', value || null)}
              placeholder="Street address, building, or campus location"
            />
            <WizardFieldError message={errors.address?.message} />
          </div>

          <div className={wizardGeoRowClass}>
            <Controller
              control={control}
              name="country_id"
              render={({ field, fieldState }) => (
                <div>
                  <SearchableSelect
                    label="Country"
                    required
                    value={field.value ? String(field.value) : ''}
                    options={countryOptions}
                    onChange={value => {
                      const next = value ? Number(value) : undefined;
                      field.onChange(next);
                      setValue('state_id', undefined);
                      setValue('location_id', undefined);
                    }}
                    placeholder="Select country..."
                  />
                  <WizardFieldError message={fieldState.error?.message} />
                </div>
              )}
            />

            <Controller
              control={control}
              name="state_id"
              render={({ field, fieldState }) => (
                <div>
                  <SearchableSelect
                    label="State"
                    required
                    value={field.value ? String(field.value) : ''}
                    options={stateOptions}
                    onChange={value => {
                      const next = value ? Number(value) : undefined;
                      field.onChange(next);
                      setValue('location_id', undefined);
                    }}
                    placeholder={countryId ? 'Select state...' : 'Select country first'}
                    disabled={!countryId}
                  />
                  <WizardFieldError message={fieldState.error?.message} />
                </div>
              )}
            />

            <Controller
              control={control}
              name="location_id"
              render={({ field, fieldState }) => (
                <div>
                  <SearchableSelect
                    label="City"
                    required
                    value={field.value ? String(field.value) : ''}
                    options={cityOptions}
                    onChange={value => field.onChange(value ? Number(value) : undefined)}
                    placeholder={stateId ? 'Select city...' : 'Select state first'}
                    disabled={!stateId}
                  />
                  <WizardFieldError message={fieldState.error?.message} />
                </div>
              )}
            />

            <CharCountInput
              label="Zipcode"
              maxLength={10}
              value={watch('zipcode') || ''}
              onChange={value => setValue('zipcode', value || null)}
              placeholder="e.g. 02139"
            />
          </div>

          <div className={wizardContactRowClass}>
            <Controller
              control={control}
              name="phone_numbers"
              render={({ field }) => (
                <LabeledContactListField
                  label="Phone numbers"
                  required
                  items={field.value}
                  onChange={field.onChange}
                  typeOptions={PHONE_CONTACT_TYPES}
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
                  typeOptions={FAX_CONTACT_TYPES}
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
                  required
                  items={field.value}
                  onChange={field.onChange}
                  typeOptions={EMAIL_CONTACT_TYPES}
                  valuePlaceholder="campus@university.edu"
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
                  label="Campus web URLs"
                  items={field.value}
                  onChange={field.onChange}
                  typeOptions={WEB_LINK_TYPES}
                  valuePlaceholder="https://www.university.edu/campus"
                  valueInputType="url"
                  addLabel="Add web links"
                  errors={webLinkFieldErrors}
                  typeSelectWidthClass="w-full sm:w-[8.75rem]"
                  maxLength={250}
                  fullWidth
                />
              )}
            />
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={locked}
            onClick={() => void handleSaveCampusToList()}
            className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg disabled:opacity-50"
          >
            {editingIndex !== null ? 'Update campus in list' : 'Add campus to list'}
          </button>
          {editingIndex !== null ? (
            <button
              type="button"
              disabled={locked}
              onClick={resetDraftForm}
              className="rounded-xl border border-border-subtle px-4 py-2 text-sm font-semibold text-text-muted disabled:opacity-50"
            >
              Cancel edit
            </button>
          ) : null}
        </div>

        {!embedded ? (
          <div className="mt-6 flex flex-wrap justify-end gap-2 border-t border-border-subtle pt-4">
            <button
              type="button"
              disabled={saving || locked}
              onClick={() => onSaveStep(false)}
              className="inline-flex items-center gap-2 rounded-xl border border-border-subtle px-4 py-2 text-sm font-semibold text-text-main disabled:opacity-50"
            >
              {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
              Save step
            </button>
            <button
              type="button"
              disabled={saving || locked}
              onClick={() => onSaveStep(true)}
              className="rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg disabled:opacity-50"
            >
              Save & continue
            </button>
          </div>
        ) : null}
      </section>
    </div>
  );
});

InstitutionWizardStep2.displayName = 'InstitutionWizardStep2';

export default InstitutionWizardStep2;
