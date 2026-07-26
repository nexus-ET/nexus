import React, { useCallback, useEffect, useMemo, useState } from 'react';
import DatePicker from 'react-datepicker';
import 'react-datepicker/dist/react-datepicker.css';
import { Loader2 } from 'lucide-react';
import { apiFetch } from '../utils/api';
import { formatLocalIsoDate, parseLocalIsoDate } from '../types/candidateProfile';
import {
  TEST_NAME_OPTIONS,
  calculateAutoOverallScore,
  emptyTestScoreForm,
  getOverallConfig,
  getSectionsForTest,
  groupTestScoreRecords,
  normalizeOverallInput,
  normalizeScoreInput,
  showsSeparateOverallField,
  testScoreFormToSavePayload,
  validateOverallScore,
  validateSectionScore,
  validateTestScoreForm,
  type CandidateTestScoresResponse,
  type TestName,
  type TestScoreFormState,
} from '../types/candidateTestScores';
import EmptyListMessage from './ui/EmptyListMessage';
import { nexusDatePickerPortalProps } from '../utils/nexusDatePickerPortal';
import {
  studentInfoFieldErrorClass as fieldErrorClass,
  studentInfoInputClass as inputClass,
  studentInfoLabelClass as labelClass,
  studentInfoSectionClass as sectionClass,
} from './studentInfoFormStyles';

interface CandidateTestScoresTabProps {
  bookingId: number;
  compact?: boolean;
}

const fieldClass = (hasError: boolean) =>
  `${inputClass}${hasError ? ' border-red-400 ring-1 ring-red-200' : ''}`;

const CandidateTestScoresTab: React.FC<CandidateTestScoresTabProps> = ({
  bookingId,
  compact = false,
}) => {
  const [form, setForm] = useState<TestScoreFormState>(emptyTestScoreForm);
  const [savedScores, setSavedScores] = useState<CandidateTestScoresResponse['scores']>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [sectionErrors, setSectionErrors] = useState<Record<string, string>>({});

  const apiPath = `bookings/mine/${bookingId}/test-scores`;
  const sections = useMemo(() => getSectionsForTest(form.test_name), [form.test_name]);
  const overallConfig = useMemo(() => getOverallConfig(form.test_name), [form.test_name]);
  const groupedAttempts = useMemo(() => groupTestScoreRecords(savedScores), [savedScores]);

  const validation = useMemo(() => validateTestScoreForm(form), [form]);
  const canSave = validation.isValid && !saving;

  const testDate = useMemo(() => parseLocalIsoDate(form.test_date), [form.test_date]);

  const loadScores = useCallback(async () => {
    const response = (await apiFetch(apiPath)) as CandidateTestScoresResponse;
    setSavedScores(response.scores);
  }, [apiPath]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setSuccess(null);

    loadScores()
      .catch(err => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Failed to load test scores.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [loadScores]);

  const resetEntryForm = () => {
    setForm(emptyTestScoreForm());
    setSectionErrors({});
  };

  const applyAutoOverall = (nextForm: TestScoreFormState): TestScoreFormState => {
    if (!nextForm.test_name || nextForm.overall_manual_override || !showsSeparateOverallField(nextForm.test_name)) {
      return nextForm;
    }
    const autoOverall = calculateAutoOverallScore(nextForm.test_name, nextForm.section_scores);
    return { ...nextForm, overall_score: autoOverall };
  };

  const updateForm = (patch: Partial<TestScoreFormState>) => {
    setForm(prev => ({ ...prev, ...patch }));
    setSuccess(null);
    if (patch.section_scores) {
      setSectionErrors(prev => {
        const next = { ...prev };
        Object.keys(patch.section_scores ?? {}).forEach(key => {
          delete next[key];
        });
        return next;
      });
    }
    if (patch.test_name !== undefined) {
      setSectionErrors({});
    }
  };

  const handleTestNameChange = (value: string) => {
    const testName = value as TestName | '';
    const nextSections = getSectionsForTest(testName);
    const section_scores: Record<string, string> = {};
    nextSections.forEach(section => {
      section_scores[section.section_name] = '';
    });
    const nextForm = applyAutoOverall({
      ...emptyTestScoreForm(),
      test_name: testName,
      test_date: form.test_date,
      score_report_url: form.score_report_url,
      section_scores,
      overall_manual_override: false,
    });
    updateForm(nextForm);
  };

  const handleSectionChange = (sectionName: string, rawValue: string) => {
    const config = sections.find(section => section.section_name === sectionName);
    if (!config) return;
    const normalized = normalizeScoreInput(rawValue, config);
    const nextForm = applyAutoOverall({
      ...form,
      section_scores: {
        ...form.section_scores,
        [sectionName]: normalized,
      },
    });
    setForm(nextForm);
    setSuccess(null);
    setSectionErrors(prev => {
      const next = { ...prev };
      delete next[sectionName];
      return next;
    });
  };

  const handleOverallChange = (rawValue: string) => {
    if (!overallConfig) return;
    const normalized = normalizeOverallInput(rawValue, overallConfig);
    updateForm({
      overall_score: normalized,
      overall_manual_override: true,
    });
  };

  const handleOverallBlur = () => {
    const result = validateOverallScore(form.overall_score, form.test_name);
    setSectionErrors(prev => {
      const next = { ...prev };
      if (result.error) {
        next.overall_score = result.error;
      } else {
        delete next.overall_score;
      }
      return next;
    });
  };

  const handleRecalculateOverall = () => {
    if (!form.test_name) return;
    const autoOverall = calculateAutoOverallScore(form.test_name, form.section_scores);
    updateForm({
      overall_score: autoOverall,
      overall_manual_override: false,
    });
  };

  const handleSectionBlur = (sectionName: string) => {
    const config = sections.find(section => section.section_name === sectionName);
    if (!config) return;
    const result = validateSectionScore(form.section_scores[sectionName] ?? '', config);
    setSectionErrors(prev => {
      const next = { ...prev };
      if (result.error) {
        next[sectionName] = result.error;
      } else {
        delete next[sectionName];
      }
      return next;
    });
  };

  const handleCancel = () => {
    resetEntryForm();
    setError(null);
    setSuccess(null);
  };

  const handleSave = async (event: React.FormEvent) => {
    event.preventDefault();
    const result = validateTestScoreForm(form);
    if (!result.isValid) {
      setSectionErrors(result.sectionErrors);
      setError('Please fix score validation errors before saving.');
      setSuccess(null);
      return;
    }

    try {
      setSaving(true);
      setError(null);
      setSuccess(null);
      const response = (await apiFetch(apiPath, {
        method: 'POST',
        body: JSON.stringify(testScoreFormToSavePayload(form)),
      })) as CandidateTestScoresResponse;
      setSavedScores(response.scores);
      resetEntryForm();
      setSuccess('Test scores saved. You can add another test attempt below.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save test scores.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-text-muted">
        <Loader2 size={22} className="animate-spin mr-2" />
        Loading test scores...
      </div>
    );
  }

  return (
    <form onSubmit={handleSave} className={compact ? 'flex flex-1 min-h-0 flex-col' : 'space-y-4'}>
      <div className={compact ? 'flex-1 min-h-0 overflow-y-auto custom-scrollbar space-y-4' : 'space-y-4'}>
        {error ? (
          <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        ) : null}
        {success ? (
          <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
            {success}
          </div>
        ) : null}

        <section className={sectionClass}>
          <h3 className="text-sm font-bold text-text-main uppercase tracking-wide">Add Test Scores</h3>
          <p className="text-sm text-text-muted">
            Each save creates a new test record. Retakes and multiple tests are stored separately.
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            <div>
              <label htmlFor="test-score-name" className={labelClass}>
                Test Name
              </label>
              <select
                id="test-score-name"
                className={fieldClass(Boolean(sectionErrors.test_name))}
                value={form.test_name}
                onChange={e => handleTestNameChange(e.target.value)}
              >
                <option value="">Select test</option>
                {TEST_NAME_OPTIONS.map(option => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              {sectionErrors.test_name ? (
                <p className={fieldErrorClass}>{sectionErrors.test_name}</p>
              ) : null}
            </div>

            <div>
              <label htmlFor="test-score-date" className={labelClass}>
                Test Date
              </label>
              <DatePicker
                id="test-score-date"
                selected={testDate}
                onChange={(date: Date | null) =>
                  updateForm({ test_date: formatLocalIsoDate(date) })
                }
                dateFormat="dd MMM yyyy"
                placeholderText="Select test date"
                className={inputClass}
                wrapperClassName="w-full"
                isClearable
                {...nexusDatePickerPortalProps}
              />
            </div>

            <div>
              <label htmlFor="test-score-report-url" className={labelClass}>
                Score Report URL
              </label>
              <input
                id="test-score-report-url"
                type="url"
                className={inputClass}
                value={form.score_report_url}
                onChange={e => updateForm({ score_report_url: e.target.value })}
                placeholder="https://..."
              />
            </div>
          </div>

          {form.test_name ? (
            <>
              {showsSeparateOverallField(form.test_name) && overallConfig ? (
                <div className="rounded-md border border-sky-200 bg-sky-50/60 p-3 space-y-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <label htmlFor="test-overall-score" className="text-sm font-bold text-text-main">
                      Overall/Composite Score
                      <span className="font-normal text-text-muted">
                        {' '}
                        ({overallConfig.min_score}–{overallConfig.max_score})
                      </span>
                    </label>
                    <button
                      type="button"
                      onClick={handleRecalculateOverall}
                      className="text-xs font-semibold text-sky-800 hover:text-sky-950"
                    >
                      Recalculate from sections
                    </button>
                  </div>
                  <input
                    id="test-overall-score"
                    type="text"
                    inputMode={overallConfig.data_type === 'float' ? 'decimal' : 'numeric'}
                    maxLength={overallConfig.max_length}
                    className={fieldClass(Boolean(sectionErrors.overall_score))}
                    value={form.overall_score}
                    onChange={e => handleOverallChange(e.target.value)}
                    onBlur={handleOverallBlur}
                    placeholder={
                      overallConfig.auto_method === 'sum'
                        ? 'Auto-sums sections; edit to override'
                        : 'Auto-averages sections; edit to override'
                    }
                  />
                  <p className="text-sm text-text-muted">
                    {form.overall_manual_override
                      ? 'Manual override active.'
                      : 'Auto-calculated from section scores when all sections are filled.'}
                  </p>
                  {sectionErrors.overall_score ? (
                    <p className={fieldErrorClass}>{sectionErrors.overall_score}</p>
                  ) : null}
                </div>
              ) : null}

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {sections.map(section => {
                const hasError = Boolean(sectionErrors[section.section_name]);
                return (
                  <div key={section.section_name}>
                    <label className={labelClass}>
                      {section.section_name}
                      <span className="font-normal text-text-muted">
                        {' '}
                        ({section.min_score}–{section.max_score})
                      </span>
                    </label>
                    <input
                      type="text"
                      inputMode={section.data_type === 'float' ? 'decimal' : 'numeric'}
                      maxLength={section.max_length}
                      className={fieldClass(hasError)}
                      value={form.section_scores[section.section_name] ?? ''}
                      onChange={e => handleSectionChange(section.section_name, e.target.value)}
                      onBlur={() => handleSectionBlur(section.section_name)}
                      placeholder={section.data_type === 'float' ? 'e.g. 7.5' : 'e.g. 28'}
                    />
                    {hasError ? (
                      <p className={fieldErrorClass}>{sectionErrors[section.section_name]}</p>
                    ) : null}
                  </div>
                );
              })}
              </div>
            </>
          ) : null}
        </section>

        {groupedAttempts.length > 0 ? (
          <section className={sectionClass}>
            <h3 className="text-sm font-bold text-text-main uppercase tracking-wide">
              Saved Test History
            </h3>
            <div className="space-y-3">
              {groupedAttempts.map(attempt => (
                <div
                  key={attempt.key}
                  className="rounded-md border border-border-subtle bg-surface-bg/40 p-3 space-y-2"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <p className="text-sm font-bold text-text-main">{attempt.test_name}</p>
                      {attempt.overall_score != null ? (
                        <p className="text-xs text-sky-800 font-semibold mt-0.5">
                          Overall: {attempt.overall_score}
                        </p>
                      ) : null}
                    </div>
                    <p className="text-sm text-text-muted">
                      {attempt.test_date
                        ? new Date(`${attempt.test_date}T00:00:00`).toLocaleDateString()
                        : 'No date'}
                      {' · '}
                      Saved {new Date(attempt.created_at).toLocaleString()}
                    </p>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    {attempt.sections.map(section => (
                      <div key={section.section_name} className="text-xs">
                        <span className="font-bold text-text-main">{section.section_name}: </span>
                        <span className="text-text-muted">{section.score}</span>
                      </div>
                    ))}
                  </div>
                  {attempt.score_report_url ? (
                    <a
                      href={attempt.score_report_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-xs text-sky-700 hover:underline break-all"
                    >
                      View score report
                    </a>
                  ) : null}
                </div>
              ))}
            </div>
          </section>
        ) : (
          <section className={sectionClass}>
            <h3 className="text-sm font-bold text-text-main uppercase tracking-wide">
              Saved Test History
            </h3>
            <EmptyListMessage
              compact
              message='No test scores saved yet. Complete the form above and click "Save" when you are ready.'
            />
          </section>
        )}
      </div>

      <div className="shrink-0 relative z-0 flex items-center justify-end gap-2 border-t border-border-subtle bg-surface-bg/70 px-0 py-3">
        <button
          type="button"
          onClick={handleCancel}
          disabled={saving}
          className="rounded-md border border-border-subtle px-4 py-2 text-sm font-semibold text-text-main hover:bg-card disabled:opacity-60"
        >
          Clear
        </button>
        <button
          type="submit"
          disabled={!canSave}
          className="rounded-md bg-sky-700 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-800 disabled:opacity-60 inline-flex items-center gap-2"
        >
          {saving ? <Loader2 size={14} className="animate-spin" /> : null}
          Save
        </button>
      </div>
    </form>
  );
};

export default CandidateTestScoresTab;
