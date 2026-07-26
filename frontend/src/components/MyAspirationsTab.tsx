import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { apiFetch } from '../utils/api';
import { useCountries } from '../hooks/useCountries';
import { useEducationDegrees } from '../hooks/useEducationDegrees';
import {
  APTITUDE_TEST_OPTIONS,
  ASPIRATION_MAJOR_OPTIONS,
  PROGRAM_OTHER_VALUE,
  BUDGET_OPTIONS,
  ENGLISH_TEST_OPTIONS,
  FUNDING_SOURCE_OPTIONS,
  FUNDING_COVERAGE_OPTIONS,
  FUTURE_LOCATION_OPTIONS,
  GLOBAL_RANKING_OPTIONS,
  IMMERSIVE_FAMILY_ACCOMMODATION_OPTIONS,
  INSTITUTION_TYPE_OPTIONS,
  INTAKE_PLANNED_OPTIONS,
  OFF_CAMPUS_INDEPENDENT_ACCOMMODATION_OPTIONS,
  SHARED_LIVING_ACCOMMODATION_OPTIONS,
  UNIVERSITY_MANAGED_ACCOMMODATION_OPTIONS,
  STUDY_COUNTRY_OTHER_VALUE,
  WHY_STUDY_ABROAD_OPTIONS,
  aspirationsToForm,
  aspirationsToSavePayload,
  emptyAspirationsForm,
  getFundingCoverage,
  getIntakeYearOptions,
  isFundingSourceSelected,
  setFundingCoverage,
  splitDegreesByLevel,
  toggleFundingSource,
  toggleListValue,
  validateAspirationsForm,
  type FundingSourceOption,
  type StudentAspirationsFormState,
  type StudentAspirationsResponse,
} from '../types/studentAspirations';

type ColumnCount = 1 | 2 | 3 | 4 | 5 | 6 | 7;

const checkboxClass =
  'flex items-start gap-2 rounded-md border border-border-subtle bg-surface-bg/50 px-2.5 py-2 text-sm text-text-main cursor-pointer hover:bg-surface-bg';

const COLUMN_CLASS: Record<ColumnCount, string> = {
  1: 'grid-cols-1',
  2: 'grid-cols-1 sm:grid-cols-2',
  3: 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3',
  4: 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-4',
  5: 'grid-cols-5',
  6: 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-6',
  7: 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7',
};

interface CheckboxOption<T extends string | number> {
  value: T;
  label?: string;
  title?: string;
  description?: string;
}

interface CheckboxGroupProps<T extends string | number> {
  options: CheckboxOption<T>[];
  selected: T[];
  onChange: (next: T[]) => void;
  columns?: ColumnCount;
  hasError?: boolean;
}

function renderCheckboxLabel(option: CheckboxOption<string | number>) {
  if (option.title && option.description) {
    return (
      <>
        <span className="font-bold">{option.title}</span>
        {' - '}
        {option.description}
      </>
    );
  }
  if (option.title) {
    return <span className="font-bold">{option.title}</span>;
  }
  return option.label;
}

function CheckboxGroup<T extends string | number>({
  options,
  selected,
  onChange,
  columns = 2,
  hasError = false,
}: CheckboxGroupProps<T>) {
  const borderClass = hasError ? 'border-red-300 ring-1 ring-red-100' : 'border-border-subtle';

  return (
    <div className={`grid ${COLUMN_CLASS[columns]} gap-2`}>
      {options.map(option => {
        const checked = selected.includes(option.value);
        return (
          <label
            key={String(option.value)}
            className={`${checkboxClass} ${borderClass}`}
          >
            <input
              type="checkbox"
              className="mt-0.5 shrink-0"
              checked={checked}
              onChange={event =>
                onChange(toggleListValue(selected, option.value, event.target.checked))
              }
            />
            <span>{renderCheckboxLabel(option)}</span>
          </label>
        );
      })}
    </div>
  );
}

interface PaddedCheckboxGridProps<T extends string | number> {
  options: { value: T; label: string }[];
  selected: T[];
  onChange: (next: T[]) => void;
  columns?: 4;
  hasError?: boolean;
}

function PaddedCheckboxGrid<T extends string | number>({
  options,
  selected,
  onChange,
  columns = 4,
  hasError = false,
}: PaddedCheckboxGridProps<T>) {
  const placeholders = Math.max(0, columns - options.length);
  const borderClass = hasError ? 'border-red-300 ring-1 ring-red-100' : 'border-border-subtle';

  return (
    <div className={`grid ${COLUMN_CLASS[columns]} gap-2`}>
      {options.map(option => (
        <label key={option.value} className={`${checkboxClass} ${borderClass}`}>
          <input
            type="checkbox"
            className="mt-0.5 shrink-0"
            checked={selected.includes(option.value)}
            onChange={event =>
              onChange(toggleListValue(selected, option.value, event.target.checked))
            }
          />
          <span>{option.label}</span>
        </label>
      ))}
      {Array.from({ length: placeholders }).map((_, index) => (
        <div
          key={`placeholder-${index}`}
          className="min-h-[40px] rounded-md border border-dashed border-border-subtle/60 bg-surface-bg/20"
          aria-hidden="true"
        />
      ))}
    </div>
  );
}

interface MyAspirationsTabProps {
  bookingId?: number;
  compact?: boolean;
}

const MyAspirationsTab: React.FC<MyAspirationsTabProps> = ({ bookingId, compact = false }) => {
  const sectionStyles = compact
    ? 'rounded-lg border border-border-subtle bg-card/80 p-3 space-y-2.5'
    : 'rounded-xl border border-border-subtle bg-card/80 p-4 space-y-3';
  const sectionHeadingClass = compact
    ? 'text-sm font-bold text-text-main'
    : 'text-base font-bold text-text-main';
  const subHeadingClass = 'text-sm font-bold text-text-main';
  const fieldLabelClass = 'block text-sm font-bold text-text-main mb-1';

  const apiPath = bookingId
    ? `bookings/mine/${bookingId}/aspirations`
    : 'users/me/aspirations';

  const [form, setForm] = useState<StudentAspirationsFormState>(emptyAspirationsForm);
  const [baseline, setBaseline] = useState<StudentAspirationsFormState>(emptyAspirationsForm);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);

  const { countries } = useCountries();
  const { degrees } = useEducationDegrees();
  const intakeYears = useMemo(() => getIntakeYearOptions(), []);
  const { universityCollege, preCollege } = useMemo(
    () => splitDegreesByLevel(degrees),
    [degrees]
  );

  const countryOptions = useMemo(
    () => [
      ...countries
        .map(country => ({ value: country.iso2, label: country.name }))
        .sort((a, b) => a.label.localeCompare(b.label)),
      { value: 'OTHER', label: 'Others' },
    ],
    [countries]
  );

  const programOptions = useMemo(
    () => [
      ...ASPIRATION_MAJOR_OPTIONS.map(label => ({ value: label, label })),
      { value: PROGRAM_OTHER_VALUE, label: 'Others' },
    ],
    []
  );

  const loadAspirations = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const response = (await apiFetch(apiPath)) as StudentAspirationsResponse;
      const next = aspirationsToForm(response.aspirations);
      setForm(next);
      setBaseline(next);
      setSavedAt(response.saved_at || null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load aspirations.');
      const empty = emptyAspirationsForm();
      setForm(empty);
      setBaseline(empty);
    } finally {
      setLoading(false);
    }
  }, [apiPath]);

  useEffect(() => {
    loadAspirations();
  }, [loadAspirations]);

  const updateForm = (patch: Partial<StudentAspirationsFormState>) => {
    setForm(prev => ({ ...prev, ...patch }));
    setSuccess(null);
    setValidationErrors([]);
  };

  const handleCancel = () => {
    setForm(baseline);
    setError(null);
    setSuccess(null);
    setValidationErrors([]);
  };

  const handleSave = async (event: React.FormEvent) => {
    event.preventDefault();
    const errors = validateAspirationsForm(form);
    if (errors.length > 0) {
      setValidationErrors(errors);
      setError('Please complete all required fields before saving.');
      setSuccess(null);
      return;
    }

    try {
      setSaving(true);
      setError(null);
      setSuccess(null);
      setValidationErrors([]);
      const response = (await apiFetch(apiPath, {
        method: 'PUT',
        body: JSON.stringify(aspirationsToSavePayload(form)),
      })) as StudentAspirationsResponse;
      const next = aspirationsToForm(response.aspirations);
      setForm(next);
      setBaseline(next);
      setSavedAt(response.saved_at || new Date().toISOString());
      setSuccess('Your aspirations have been saved.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save aspirations.');
    } finally {
      setSaving(false);
    }
  };

  const hasSectionError = (keywords: string[]) =>
    validationErrors.some(message =>
      keywords.some(keyword => message.toLowerCase().includes(keyword.toLowerCase()))
    );

  const renderFundingColumn = (source: FundingSourceOption, label: string) => {
    const selected = isFundingSourceSelected(form.funding_sources, source);
    const coverage = getFundingCoverage(form.funding_sources, source);
    const showError = hasSectionError(['primary funding', 'funding', label.toLowerCase()]);

    return (
      <div
        key={source}
        className={`rounded-lg border bg-surface-bg/40 p-3 space-y-2 ${
          showError ? 'border-red-300' : 'border-border-subtle'
        }`}
      >
        <label className={`${checkboxClass} border-transparent bg-transparent px-0 py-0 hover:bg-transparent`}>
          <input
            type="checkbox"
            className="mt-0.5 shrink-0"
            checked={selected}
            onChange={event =>
              updateForm({
                funding_sources: toggleFundingSource(
                  form.funding_sources,
                  source,
                  event.target.checked
                ),
              })
            }
          />
          <span className="font-bold">{label}</span>
        </label>
        <div className="flex flex-wrap items-center justify-end gap-x-3 gap-y-1 text-sm">
          {FUNDING_COVERAGE_OPTIONS.map(option => (
            <label key={option.value} className="inline-flex items-center gap-1.5 cursor-pointer">
              <input
                type="radio"
                name={`funding-coverage-${source}`}
                checked={coverage === option.value}
                disabled={!selected}
                onChange={() =>
                  updateForm({
                    funding_sources: setFundingCoverage(form.funding_sources, source, option.value),
                  })
                }
              />
              <span>{renderCheckboxLabel(option)}</span>
            </label>
          ))}
        </div>
      </div>
    );
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-text-muted">
        <Loader2 size={22} className="animate-spin mr-2" />
        Loading aspirations questionnaire...
      </div>
    );
  }

  return (
    <form onSubmit={handleSave} className={compact ? 'flex flex-1 min-h-0 flex-col' : 'space-y-4'}>
      {!compact ? (
        <div>
          <h3 className="text-lg font-bold text-text-main">My Aspirations</h3>
          <p className="text-sm text-text-muted mt-1">
            Tell us about your study-abroad goals. All sections are required.
          </p>
          {savedAt ? (
            <p className="text-sm text-emerald-700 mt-1">
              Last saved {new Date(savedAt).toLocaleString()}
            </p>
          ) : null}
        </div>
      ) : savedAt ? (
        <p className="text-sm font-semibold text-emerald-700 shrink-0">
          Last saved {new Date(savedAt).toLocaleString()}
        </p>
      ) : null}

      <div className={compact ? 'flex-1 min-h-0 overflow-y-auto custom-scrollbar space-y-3 pr-1' : 'space-y-4'}>
        {error ? (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
            {validationErrors.length > 0 ? (
              <ul className="mt-2 list-disc pl-4 space-y-0.5 text-sm">
                {validationErrors.map(item => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
        {success ? (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
            {success}
          </div>
        ) : null}

        <section className={sectionStyles}>
          <h4 className={sectionHeadingClass}>Why study abroad?</h4>
          <CheckboxGroup
            options={WHY_STUDY_ABROAD_OPTIONS}
            selected={form.why_study_abroad}
            onChange={why_study_abroad =>
              updateForm({
                why_study_abroad,
                why_study_abroad_other: why_study_abroad.includes('OTHER')
                  ? form.why_study_abroad_other
                  : '',
              })
            }
            columns={3}
            hasError={hasSectionError(['why study abroad', 'others — why study abroad'])}
          />
          {form.why_study_abroad.includes('OTHER') && (
            <div className="mt-3">
              <label className={fieldLabelClass}>
                Others — why do you want to study abroad?
              </label>
              <input
                type="text"
                value={form.why_study_abroad_other}
                maxLength={100}
                onChange={event => updateForm({ why_study_abroad_other: event.target.value })}
                placeholder="Enter up to 100 characters"
                className={`w-full max-w-md rounded-md border bg-surface-bg px-3 py-2 text-sm text-text-main placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/30 ${
                  hasSectionError(['others — why study abroad'])
                    ? 'border-red-300 ring-1 ring-red-100'
                    : 'border-border-subtle'
                }`}
              />
              <p className="mt-1 text-sm text-text-muted">
                {form.why_study_abroad_other.length}/100 characters
              </p>
            </div>
          )}
        </section>

        <section className={sectionStyles}>
          <h4 className={sectionHeadingClass}>Countries you wish to study?</h4>
          <CheckboxGroup
            options={countryOptions}
            selected={form.study_countries_iso2}
            onChange={study_countries_iso2 =>
              updateForm({
                study_countries_iso2,
                study_countries_other: study_countries_iso2.includes(STUDY_COUNTRY_OTHER_VALUE)
                  ? form.study_countries_other
                  : '',
              })
            }
            columns={6}
            hasError={hasSectionError(['countries', 'others — countries'])}
          />
          {form.study_countries_iso2.includes(STUDY_COUNTRY_OTHER_VALUE) && (
            <div className="mt-3">
              <label className={fieldLabelClass}>
                Others — enter country or countries
              </label>
              <input
                type="text"
                value={form.study_countries_other}
                maxLength={100}
                onChange={event => updateForm({ study_countries_other: event.target.value })}
                placeholder="Enter up to 100 characters"
                className={`w-full max-w-md rounded-md border bg-surface-bg px-3 py-2 text-sm text-text-main placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/30 ${
                  hasSectionError(['others — countries'])
                    ? 'border-red-300 ring-1 ring-red-100'
                    : 'border-border-subtle'
                }`}
              />
              <p className="mt-1 text-sm text-text-muted">
                {form.study_countries_other.length}/100 characters
              </p>
            </div>
          )}
        </section>

        <section className={sectionStyles}>
          <h4 className={sectionHeadingClass}>Your Preferred Institution?</h4>
          <div className="space-y-4">
            <div>
              <p className={`${subHeadingClass} mb-2`}>Institution Type</p>
              <CheckboxGroup
                options={INSTITUTION_TYPE_OPTIONS}
                selected={form.institution_type}
                onChange={institution_type => updateForm({ institution_type })}
                columns={4}
                hasError={hasSectionError(['institution type'])}
              />
            </div>
            <div>
              <p className={`${subHeadingClass} mb-2`}>Ranking Tier (Global)</p>
              <CheckboxGroup
                options={GLOBAL_RANKING_OPTIONS}
                selected={form.global_ranking}
                onChange={global_ranking => updateForm({ global_ranking })}
                columns={4}
                hasError={hasSectionError(['ranking tier'])}
              />
            </div>
            <div>
              <p className={`${subHeadingClass} mb-2`}>Budget Ranges</p>
              <CheckboxGroup
                options={BUDGET_OPTIONS}
                selected={form.budget}
                onChange={budget => updateForm({ budget })}
                columns={5}
                hasError={hasSectionError(['budget'])}
              />
            </div>
          </div>
        </section>

        <section className={sectionStyles}>
          <h4 className={sectionHeadingClass}>Intake Planned?</h4>
          <div className="space-y-4">
            <div>
              <CheckboxGroup
                options={INTAKE_PLANNED_OPTIONS}
                selected={form.intake_seasons}
                onChange={intake_seasons =>
                  updateForm({
                    intake_seasons,
                    intake_season_other: intake_seasons.includes('OTHER')
                      ? form.intake_season_other
                      : '',
                  })
                }
                columns={7}
                hasError={hasSectionError(['intake planned', 'others intake'])}
              />
              {form.intake_seasons.includes('OTHER') && (
                <div className="mt-3">
                  <label className={fieldLabelClass}>
                    Others — enter intake period
                  </label>
                  <input
                    type="text"
                    value={form.intake_season_other}
                    onChange={event => updateForm({ intake_season_other: event.target.value })}
                    placeholder="Enter other intake period"
                    className={`w-full max-w-md rounded-md border bg-surface-bg px-3 py-2 text-sm text-text-main placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/30 ${
                      hasSectionError(['others intake'])
                        ? 'border-red-300 ring-1 ring-red-100'
                        : 'border-border-subtle'
                    }`}
                  />
                </div>
              )}
            </div>
            <div>
              <p className={`${subHeadingClass} mb-2`}>Years</p>
              <PaddedCheckboxGrid
                options={intakeYears.map(year => ({ value: year, label: String(year) }))}
                selected={form.intake_years}
                onChange={intake_years => updateForm({ intake_years })}
                hasError={hasSectionError(['intake years'])}
              />
            </div>
          </div>
        </section>

        <section className={sectionStyles}>
          <h4 className={sectionHeadingClass}>Discipline you wish to enroll?</h4>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="rounded-lg border border-border-subtle bg-surface-bg/40 p-3 space-y-2">
              <p className={subHeadingClass}>University / College</p>
              <CheckboxGroup
                options={universityCollege.map(item => ({ value: item.code, label: item.label }))}
                selected={form.discipline_university_college}
                onChange={discipline_university_college =>
                  updateForm({ discipline_university_college })
                }
                columns={1}
                hasError={hasSectionError(['discipline'])}
              />
            </div>
            <div className="rounded-lg border border-border-subtle bg-surface-bg/40 p-3 space-y-2">
              <p className={subHeadingClass}>Pre-College</p>
              <CheckboxGroup
                options={preCollege.map(item => ({ value: item.code, label: item.label }))}
                selected={form.discipline_pre_college}
                onChange={discipline_pre_college => updateForm({ discipline_pre_college })}
                columns={1}
                hasError={hasSectionError(['discipline'])}
              />
            </div>
          </div>
        </section>

        <section className={sectionStyles}>
          <h4 className={sectionHeadingClass}>Programs you wish to study?</h4>
          <CheckboxGroup
            options={programOptions}
            selected={form.programs}
            onChange={programs =>
              updateForm({
                programs,
                programs_other: programs.includes(PROGRAM_OTHER_VALUE) ? form.programs_other : '',
              })
            }
            columns={4}
            hasError={hasSectionError(['programs', 'others — programs'])}
          />
          {form.programs.includes(PROGRAM_OTHER_VALUE) && (
            <div className="mt-3">
              <label className={fieldLabelClass}>
                Others — enter program or programs
              </label>
              <input
                type="text"
                value={form.programs_other}
                maxLength={50}
                onChange={event => updateForm({ programs_other: event.target.value })}
                placeholder="Enter up to 50 characters"
                className={`w-full max-w-md rounded-md border bg-surface-bg px-3 py-2 text-sm text-text-main placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/30 ${
                  hasSectionError(['others — programs'])
                    ? 'border-red-300 ring-1 ring-red-100'
                    : 'border-border-subtle'
                }`}
              />
              <p className="mt-1 text-sm text-text-muted">
                {form.programs_other.length}/50 characters
              </p>
            </div>
          )}
        </section>

        <section className={sectionStyles}>
          <h4 className={sectionHeadingClass}>Test Preparation?</h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <p className={`${subHeadingClass} mb-2`}>English Language Proficiency</p>
              <CheckboxGroup
                options={ENGLISH_TEST_OPTIONS}
                selected={form.english_tests}
                onChange={english_tests => updateForm({ english_tests })}
                columns={2}
                hasError={hasSectionError(['english language proficiency', 'english'])}
              />
            </div>
            <div>
              <p className={`${subHeadingClass} mb-2`}>Aptitude Tests</p>
              <CheckboxGroup
                options={APTITUDE_TEST_OPTIONS}
                selected={form.aptitude_tests}
                onChange={aptitude_tests => updateForm({ aptitude_tests })}
                columns={2}
                hasError={hasSectionError(['aptitude tests', 'aptitude'])}
              />
            </div>
          </div>
        </section>

        <section className={sectionStyles}>
          <h4 className={sectionHeadingClass}>Primary Funding Source?</h4>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {FUNDING_SOURCE_OPTIONS.map(option =>
              renderFundingColumn(option.value, option.label)
            )}
            <div
              className="hidden lg:block min-h-[88px] rounded-lg border border-dashed border-border-subtle/60 bg-surface-bg/20"
              aria-hidden="true"
            />
          </div>
        </section>

        <section className={sectionStyles}>
          <h4 className={sectionHeadingClass}>Preferred Accommodation?</h4>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div>
              <p className={`${subHeadingClass} mb-2`}>University Managed</p>
              <CheckboxGroup
                options={UNIVERSITY_MANAGED_ACCOMMODATION_OPTIONS}
                selected={form.accommodation_university_managed}
                onChange={accommodation_university_managed =>
                  updateForm({ accommodation_university_managed })
                }
                columns={1}
                hasError={hasSectionError(['preferred accommodation', 'accommodation'])}
              />
            </div>
            <div>
              <p className={`${subHeadingClass} mb-2`}>Off-Campus Independent</p>
              <CheckboxGroup
                options={OFF_CAMPUS_INDEPENDENT_ACCOMMODATION_OPTIONS}
                selected={form.accommodation_off_campus_independent}
                onChange={accommodation_off_campus_independent =>
                  updateForm({ accommodation_off_campus_independent })
                }
                columns={1}
                hasError={hasSectionError(['preferred accommodation', 'accommodation'])}
              />
            </div>
            <div>
              <p className={`${subHeadingClass} mb-2`}>Shared Living</p>
              <CheckboxGroup
                options={SHARED_LIVING_ACCOMMODATION_OPTIONS}
                selected={form.accommodation_shared_living}
                onChange={accommodation_shared_living =>
                  updateForm({ accommodation_shared_living })
                }
                columns={1}
                hasError={hasSectionError(['preferred accommodation', 'accommodation'])}
              />
            </div>
            <div>
              <p className={`${subHeadingClass} mb-2`}>Immersive/Family</p>
              <CheckboxGroup
                options={IMMERSIVE_FAMILY_ACCOMMODATION_OPTIONS}
                selected={form.accommodation_immersive_family}
                onChange={accommodation_immersive_family =>
                  updateForm({ accommodation_immersive_family })
                }
                columns={1}
                hasError={hasSectionError(['preferred accommodation', 'accommodation'])}
              />
            </div>
          </div>
        </section>

        <section className={sectionStyles}>
          <h4 className={sectionHeadingClass}>Future Plans?</h4>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div>
              <p className={`${subHeadingClass} mb-2`}>To Seek a Job</p>
              <CheckboxGroup
                options={FUTURE_LOCATION_OPTIONS}
                selected={form.future_job}
                onChange={future_job => updateForm({ future_job })}
                columns={1}
                hasError={hasSectionError(['future plan', 'future plans'])}
              />
            </div>
            <div>
              <p className={`${subHeadingClass} mb-2`}>To Study Further</p>
              <CheckboxGroup
                options={FUTURE_LOCATION_OPTIONS}
                selected={form.future_study}
                onChange={future_study => updateForm({ future_study })}
                columns={1}
                hasError={hasSectionError(['future plan', 'future plans'])}
              />
            </div>
            <div
              className="hidden lg:block min-h-[40px] rounded-md border border-dashed border-border-subtle/60 bg-surface-bg/20"
              aria-hidden="true"
            />
            <div
              className="hidden lg:block min-h-[40px] rounded-md border border-dashed border-border-subtle/60 bg-surface-bg/20"
              aria-hidden="true"
            />
          </div>
        </section>
      </div>

      <div
        className={
          compact
            ? 'shrink-0 flex items-center justify-end gap-2 border-t border-border-subtle bg-surface-bg/70 px-1 pt-3'
            : 'flex items-center justify-end gap-2 pt-2'
        }
      >
        <button
          type="button"
          onClick={handleCancel}
          disabled={saving}
          className={
            compact
              ? 'rounded-md border border-border-subtle px-4 py-2 text-sm font-semibold text-text-main hover:bg-card disabled:opacity-60'
              : 'rounded-lg border border-border-subtle px-4 py-2 text-sm font-semibold text-text-main hover:bg-surface-bg disabled:opacity-60'
          }
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={saving}
          className={
            compact
              ? 'inline-flex items-center gap-2 rounded-md bg-sky-700 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-800 disabled:opacity-60'
              : 'inline-flex items-center gap-2 rounded-lg bg-sky-700 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-800 disabled:opacity-60'
          }
        >
          {saving ? <Loader2 size={16} className="animate-spin" /> : null}
          Save
        </button>
      </div>
    </form>
  );
};

export default MyAspirationsTab;
