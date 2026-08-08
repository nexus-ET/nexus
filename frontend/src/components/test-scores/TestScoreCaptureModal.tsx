import React, { useEffect, useId, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import DatePicker from 'react-datepicker';
import 'react-datepicker/dist/react-datepicker.css';
import { Loader2, X } from 'lucide-react';
import { apiFetch } from '../../utils/api';
import { formatLocalIsoDate, parseLocalIsoDate } from '../../types/candidateProfile';
import {
  TEST_NAME_OPTIONS,
  calculateAutoOverallScore,
  emptyTestScoreForm,
  getOverallConfig,
  getSectionsForTest,
  normalizeOverallInput,
  normalizeScoreInput,
  showsSeparateOverallField,
  testScoreFormToSavePayload,
  validateOverallScore,
  validateSectionScore,
  validateTestScoreForm,
  type TestName,
  type TestScoreFormState,
} from '../../types/candidateTestScores';
import { emitTestScoresChanged } from '../../utils/testScoreEvents';
import { nexusDatePickerModalPortalProps } from '../../utils/nexusDatePickerPortal';
import {
  studentInfoFieldErrorClass as fieldErrorClass,
  studentInfoInputClass as inputClass,
  studentInfoLabelClass as labelClass,
} from '../studentInfoFormStyles';

const fieldClass = (hasError: boolean) =>
  `${inputClass}${hasError ? ' border-red-400 ring-1 ring-red-200' : ''}`;

export interface TestScoreCaptureModalProps {
  open: boolean;
  bookingId: number;
  /** Pre-selected / locked test when opened from Aspirations. */
  initialTestName: TestName;
  /** When set, modal updates this attempt instead of creating a new one. */
  editingScoreIds?: number[];
  /** Prefill form (e.g. existing scores from Test Scores tab). */
  initialForm?: TestScoreFormState | null;
  /** When false, Cancel closes without unchecking the aspiration option. */
  uncheckOnCancel?: boolean;
  source?: 'aspirations' | 'test-scores-tab' | string;
  onClose: () => void;
  /** Called after a successful save. */
  onSaved?: () => void;
  /** Called when the user dismisses without saving (e.g. uncheck the aspiration option). */
  onCancel?: () => void;
}

function buildFormForTest(testName: TestName): TestScoreFormState {
  const section_scores: Record<string, string> = {};
  getSectionsForTest(testName).forEach(section => {
    section_scores[section.section_name] = '';
  });
  return {
    ...emptyTestScoreForm(),
    test_name: testName,
    section_scores,
  };
}

export default function TestScoreCaptureModal({
  open,
  bookingId,
  initialTestName,
  editingScoreIds = [],
  initialForm = null,
  uncheckOnCancel = true,
  source = 'aspirations',
  onClose,
  onSaved,
  onCancel,
}: TestScoreCaptureModalProps) {
  const titleId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const [form, setForm] = useState<TestScoreFormState>(() =>
    initialForm ?? buildFormForTest(initialTestName)
  );
  const [sectionErrors, setSectionErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isEditing = editingScoreIds.length > 0;
  const openRef = useRef(false);

  const sections = useMemo(() => getSectionsForTest(form.test_name), [form.test_name]);
  const overallConfig = useMemo(() => getOverallConfig(form.test_name), [form.test_name]);
  const testDate = useMemo(() => parseLocalIsoDate(form.test_date), [form.test_date]);

  // Hydrate when the modal opens. If scores arrive a tick later (initialForm), apply once.
  useEffect(() => {
    if (!open) {
      openRef.current = false;
      return;
    }
    const nextForm = initialForm ?? buildFormForTest(initialTestName);
    if (!openRef.current) {
      openRef.current = true;
      setForm(nextForm);
      setSectionErrors({});
      setError(null);
      setSaving(false);
      return;
    }
    // Already open with a blank shell — fill in when existing scores load.
    if (initialForm) {
      setForm(prev => {
        const hasSectionValues = Object.values(prev.section_scores || {}).some(value =>
          Boolean(String(value || '').trim())
        );
        const hasOverall = Boolean(String(prev.overall_score || '').trim());
        if (hasSectionValues || hasOverall) return prev;
        return initialForm;
      });
    }
  }, [open, initialTestName, initialForm]);

  useEffect(() => {
    if (!open) return;
    const previouslyFocused =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        handleDismiss();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', handleKeyDown);
      previouslyFocused?.focus();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- dismiss closes via latest props
  }, [open]);

  const applyAutoOverall = (nextForm: TestScoreFormState): TestScoreFormState => {
    if (
      !nextForm.test_name ||
      nextForm.overall_manual_override ||
      !showsSeparateOverallField(nextForm.test_name)
    ) {
      return nextForm;
    }
    return {
      ...nextForm,
      overall_score: calculateAutoOverallScore(nextForm.test_name, nextForm.section_scores),
    };
  };

  const handleDismiss = () => {
    if (uncheckOnCancel) {
      onCancel?.();
    }
    onClose();
  };

  const handleSectionChange = (sectionName: string, rawValue: string) => {
    const config = sections.find(section => section.section_name === sectionName);
    if (!config) return;
    const normalized = normalizeScoreInput(rawValue, config);
    setForm(prev =>
      applyAutoOverall({
        ...prev,
        section_scores: {
          ...prev.section_scores,
          [sectionName]: normalized,
        },
      })
    );
    setSectionErrors(prev => {
      const next = { ...prev };
      delete next[sectionName];
      return next;
    });
  };

  const handleOverallChange = (rawValue: string) => {
    if (!overallConfig) return;
    setForm(prev => ({
      ...prev,
      overall_score: normalizeOverallInput(rawValue, overallConfig),
      overall_manual_override: true,
    }));
  };

  const handleSave = async (event: React.FormEvent) => {
    event.preventDefault();
    event.stopPropagation();
    const result = validateTestScoreForm(form);
    if (!result.isValid) {
      setSectionErrors(result.sectionErrors);
      setError('Please fix score validation errors before saving.');
      return;
    }

    try {
      setSaving(true);
      setError(null);
      const saveBody = testScoreFormToSavePayload(form);
      if (isEditing) {
        await apiFetch(`bookings/mine/${bookingId}/test-scores/attempts`, {
          method: 'PUT',
          body: JSON.stringify({
            score_ids: editingScoreIds,
            ...saveBody,
          }),
        });
      } else {
        await apiFetch(`bookings/mine/${bookingId}/test-scores`, {
          method: 'POST',
          body: JSON.stringify(saveBody),
        });
      }
      emitTestScoresChanged({ bookingId, source });
      onSaved?.();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save test scores.');
    } finally {
      setSaving(false);
    }
  };

  if (!open || typeof document === 'undefined') return null;

  const testLabel =
    TEST_NAME_OPTIONS.find(option => option.value === initialTestName)?.label || initialTestName;

  return createPortal(
    <div className="fixed inset-0 z-[400] flex items-center justify-center p-4">
      <button
        type="button"
        className="absolute inset-0 bg-black/40"
        aria-label="Close score capture"
        onClick={handleDismiss}
      />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="relative z-[401] w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-xl border border-border-subtle bg-white shadow-xl"
      >
        <form onSubmit={handleSave} noValidate className="p-5 space-y-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 id={titleId} className="text-lg font-bold text-text-main">
                {isEditing ? `Edit ${testLabel} scores` : `Capture ${testLabel} scores`}
              </h3>
              <p className="text-sm text-text-muted mt-0.5">
                {isEditing
                  ? 'Update the saved attempt. Changes sync with the Test Scores tab.'
                  : 'Scores are saved to Test Scores and stay in sync with Aspirations.'}
              </p>
            </div>
            <button
              type="button"
              onClick={handleDismiss}
              className="rounded-md p-1 text-text-muted hover:bg-surface-bg hover:text-text-main"
              aria-label="Close"
            >
              <X size={18} />
            </button>
          </div>

          {error ? (
            <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {error}
            </div>
          ) : null}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className={labelClass}>Test Name</label>
              <input
                type="text"
                className={`${inputClass} bg-surface-bg/70`}
                value={testLabel}
                readOnly
              />
            </div>
            <div>
              <label htmlFor="aspiration-test-score-date" className={labelClass}>
                Test Date
              </label>
              <DatePicker
                id="aspiration-test-score-date"
                selected={testDate}
                onChange={(date: Date | null) =>
                  setForm(prev => ({ ...prev, test_date: formatLocalIsoDate(date) }))
                }
                dateFormat="dd MMM yyyy"
                placeholderText="Select test date"
                className={inputClass}
                wrapperClassName="w-full"
                isClearable
                {...nexusDatePickerModalPortalProps}
              />
            </div>
            <div className="sm:col-span-2">
              <label htmlFor="aspiration-test-score-url" className={labelClass}>
                Score Report URL
              </label>
              <input
                id="aspiration-test-score-url"
                type="text"
                inputMode="url"
                className={inputClass}
                value={form.score_report_url}
                onChange={e => setForm(prev => ({ ...prev, score_report_url: e.target.value }))}
                placeholder="https://..."
              />
            </div>
          </div>

          {showsSeparateOverallField(form.test_name) && overallConfig ? (
            <div className="rounded-md border border-sky-200 bg-sky-50/60 p-3 space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <label htmlFor="aspiration-test-overall" className="text-sm font-bold text-text-main">
                  Overall/Composite Score
                  <span className="font-normal text-text-muted">
                    {' '}
                    ({overallConfig.min_score}–{overallConfig.max_score})
                  </span>
                </label>
                <button
                  type="button"
                  onClick={() => {
                    if (!form.test_name) return;
                    setForm(prev => ({
                      ...prev,
                      overall_score: calculateAutoOverallScore(
                        prev.test_name as TestName,
                        prev.section_scores
                      ),
                      overall_manual_override: false,
                    }));
                  }}
                  className="text-xs font-semibold text-sky-800 hover:text-sky-950"
                >
                  Recalculate from sections
                </button>
              </div>
              <input
                id="aspiration-test-overall"
                type="text"
                inputMode={overallConfig.data_type === 'float' ? 'decimal' : 'numeric'}
                maxLength={overallConfig.max_length}
                className={fieldClass(Boolean(sectionErrors.overall_score))}
                value={form.overall_score}
                onChange={e => handleOverallChange(e.target.value)}
                onBlur={() => {
                  const result = validateOverallScore(form.overall_score, form.test_name);
                  setSectionErrors(prev => {
                    const next = { ...prev };
                    if (result.error) next.overall_score = result.error;
                    else delete next.overall_score;
                    return next;
                  });
                }}
                placeholder={
                  overallConfig.auto_method === 'sum'
                    ? 'Auto-sums sections; edit to override'
                    : 'Auto-averages sections; edit to override'
                }
              />
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
                    onBlur={() => {
                      const result = validateSectionScore(
                        form.section_scores[section.section_name] ?? '',
                        section
                      );
                      setSectionErrors(prev => {
                        const next = { ...prev };
                        if (result.error) next[section.section_name] = result.error;
                        else delete next[section.section_name];
                        return next;
                      });
                    }}
                    placeholder={section.data_type === 'float' ? 'e.g. 7.5' : 'e.g. 28'}
                  />
                  {hasError ? (
                    <p className={fieldErrorClass}>{sectionErrors[section.section_name]}</p>
                  ) : null}
                </div>
              );
            })}
          </div>

          <div className="flex items-center justify-end gap-2 pt-1 border-t border-border-subtle">
            <button
              type="button"
              onClick={handleDismiss}
              disabled={saving}
              className="rounded-md border border-border-subtle px-4 py-2 text-sm font-semibold text-text-main hover:bg-surface-bg disabled:opacity-60"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-60 inline-flex items-center gap-2"
            >
              {saving ? <Loader2 size={14} className="animate-spin" /> : null}
              {isEditing ? 'Update scores' : 'Save scores'}
            </button>
          </div>
        </form>
      </div>
    </div>,
    document.body
  );
}
