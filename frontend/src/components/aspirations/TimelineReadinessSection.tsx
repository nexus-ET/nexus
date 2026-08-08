import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ASPIRATION_OPTION_CATALOGS,
  getAspirationQuestion,
  isQuestionComplete,
} from '../../config/aspirations.config';
import { useConsultationStore } from '../../stores/consultationStore';
import { apiFetch } from '../../utils/api';
import { emitTestScoresChanged, subscribeTestScoresChanged } from '../../utils/testScoreEvents';
import { useConfirmation, useAlert } from '../../context/ConfirmationContext';
import {
  getIntakeYearOptions,
  INTAKE_CALENDAR_SYSTEMS,
  termsForCalendarSystem,
  toggleListValue,
  type AptitudeTestOption,
  type EnglishTestOption,
  type GlobalRankingOption,
  type IntakeCalendarSystemOption,
  type IntakeTermOption,
} from '../../types/studentAspirations';
import {
  ASPIRATION_TESTS_SKIP_SCORE_CAPTURE,
  APTITUDE_SCORE_TEST_NAMES,
  ENGLISH_SCORE_TEST_NAMES,
  aspirationOptionForTestName,
  formatAttemptDateLabel,
  formatAttemptScoreSummary,
  groupedAttemptToForm,
  latestAttemptForTest,
  resolveAspirationTestForCapture,
  uniqueTestNamesFromScores,
  type CandidateTestScoreRecord,
  type CandidateTestScoresResponse,
  type GroupedTestAttempt,
  type TestName,
  type TestScoreFormState,
} from '../../types/candidateTestScores';
import TestScoreCaptureModal from '../test-scores/TestScoreCaptureModal';
import SearchableMultiSelect from '../academia/SearchableMultiSelect';
import {
  AspirationBlock,
  AspirationSectionShell,
  OptionCardGroup,
  fieldLabelClass,
} from './AspirationControls';

const ASPIRATION_TEST_LABELS: Record<string, string> = {
  IELTS: 'IELTS',
  TOEFL: 'TOEFL',
  PTE: 'PTE',
  DUOLINGO: 'Duolingo',
  GRE: 'GRE',
  GMAT: 'GMAT',
  SAT: 'SAT',
  ACT: 'ACT',
  LSAT_MCAT: 'LSAT / MCAT',
};

export function TimelineReadinessSection({
  bookingId: bookingIdProp,
}: {
  bookingId?: number;
} = {}) {
  const form = useConsultationStore(state => state.form);
  const patchForm = useConsultationStore(state => state.patchForm);
  const validationErrors = useConsultationStore(state => state.validationErrors);
  const storeBookingId = useConsultationStore(state => state.bookingId);
  const bookingId = bookingIdProp ?? storeBookingId;
  const hydrated = useConsultationStore(state => state.hydrated);
  const intakeYears = useMemo(() => getIntakeYearOptions(), []);
  const openConfirm = useConfirmation();
  const showAlert = useAlert();
  const [savedScores, setSavedScores] = useState<CandidateTestScoreRecord[]>([]);
  const [deletingKey, setDeletingKey] = useState<string | null>(null);
  const [captureTest, setCaptureTest] = useState<TestName | null>(null);
  const [captureKind, setCaptureKind] = useState<'english' | 'aptitude' | null>(null);
  const [captureOption, setCaptureOption] = useState<string | null>(null);
  const [captureUncheckOnCancel, setCaptureUncheckOnCancel] = useState(true);
  const [captureEditingIds, setCaptureEditingIds] = useState<number[]>([]);
  const [captureInitialForm, setCaptureInitialForm] = useState<TestScoreFormState | null>(null);

  const hasError = (keywords: string[]) =>
    validationErrors.some(message =>
      keywords.some(keyword => message.toLowerCase().includes(keyword.toLowerCase()))
    );

  const q7 = getAspirationQuestion('ranking_tier');
  const q8 = getAspirationQuestion('intake_year');
  const q9 = getAspirationQuestion('test_prep');

  const syncCheckboxesFromScores = useCallback(
    (scores: CandidateTestScoreRecord[]) => {
      const testNames = uniqueTestNamesFromScores(scores);
      if (!testNames.length) return;

      patchForm(prev => {
        const english = new Set(prev.english_tests);
        const aptitude = new Set(prev.aptitude_tests);
        let changed = false;

        testNames.forEach(testName => {
          const mapped = aspirationOptionForTestName(testName);
          if (!mapped) return;
          if (mapped.kind === 'english') {
            if (!english.has(mapped.code as EnglishTestOption)) {
              english.add(mapped.code as EnglishTestOption);
              changed = true;
            }
          } else if (!aptitude.has(mapped.code as AptitudeTestOption)) {
            aptitude.add(mapped.code as AptitudeTestOption);
            changed = true;
          }
        });

        if (!changed) return {};
        return {
          english_tests: Array.from(english),
          aptitude_tests: Array.from(aptitude),
        };
      });
    },
    [patchForm]
  );

  const loadScores = useCallback(async (): Promise<CandidateTestScoreRecord[]> => {
    if (!bookingId) return [];
    const response = (await apiFetch(
      `bookings/mine/${bookingId}/test-scores`
    )) as CandidateTestScoresResponse;
    setSavedScores(response.scores);
    syncCheckboxesFromScores(response.scores);
    return response.scores;
  }, [bookingId, syncCheckboxesFromScores]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await loadScores();
      } catch {
        if (!cancelled) setSavedScores([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loadScores]);

  useEffect(() => {
    if (!bookingId) return;
    return subscribeTestScoresChanged(bookingId, () => {
      loadScores().catch(() => undefined);
    });
  }, [bookingId, loadScores]);

  // Re-apply score → checkbox sync after aspirations hydrate (avoids wipe race).
  useEffect(() => {
    if (!hydrated || !savedScores.length) return;
    syncCheckboxesFromScores(savedScores);
  }, [hydrated, savedScores, syncCheckboxesFromScores]);

  const openCapture = async (
    kind: 'english' | 'aptitude',
    optionCode: string,
    testName: TestName,
    options: { uncheckOnCancel: boolean }
  ) => {
    let scores = savedScores;
    if (bookingId) {
      try {
        scores = await loadScores();
      } catch {
        // Fall back to whatever is already in memory.
      }
    }

    const existing = latestAttemptForTest(scores, testName);
    setCaptureKind(kind);
    setCaptureOption(optionCode);
    setCaptureUncheckOnCancel(options.uncheckOnCancel);
    if (existing) {
      setCaptureEditingIds([...existing.score_ids]);
      setCaptureInitialForm(groupedAttemptToForm(existing));
    } else {
      setCaptureEditingIds([]);
      setCaptureInitialForm(null);
    }
    // Set test last so the modal mounts with the form payload already prepared.
    setCaptureTest(testName);
  };

  const handleTestToggle = (
    kind: 'english' | 'aptitude',
    optionCode: string,
    checked: boolean
  ) => {
    if (ASPIRATION_TESTS_SKIP_SCORE_CAPTURE.has(optionCode)) {
      if (kind === 'english') {
        patchForm(prev => ({
          english_tests: toggleListValue(
            prev.english_tests,
            optionCode as EnglishTestOption,
            checked
          ),
        }));
      } else {
        patchForm(prev => ({
          aptitude_tests: toggleListValue(
            prev.aptitude_tests,
            optionCode as AptitudeTestOption,
            checked
          ),
        }));
      }
      return;
    }

    const testName = resolveAspirationTestForCapture(optionCode);
    if (!testName) {
      // Keep selection for any unmapped option without opening capture.
      if (kind === 'english') {
        patchForm(prev => ({
          english_tests: toggleListValue(
            prev.english_tests,
            optionCode as EnglishTestOption,
            checked
          ),
        }));
      } else {
        patchForm(prev => ({
          aptitude_tests: toggleListValue(
            prev.aptitude_tests,
            optionCode as AptitudeTestOption,
            checked
          ),
        }));
      }
      return;
    }

    const alreadySelected =
      kind === 'english'
        ? form.english_tests.includes(optionCode as EnglishTestOption)
        : form.aptitude_tests.includes(optionCode as AptitudeTestOption);
    const hasScores = Boolean(latestAttemptForTest(savedScores, testName));

    if (!bookingId) {
      void showAlert({
        title: 'Session required',
        message:
          'Open this candidate from a counselling session to capture test scores.',
        variant: 'warning',
      });
      return;
    }

    // Clicking a scorable test always opens capture (selected or not).
    if (alreadySelected) {
      openCapture(kind, optionCode, testName, { uncheckOnCancel: !hasScores });
      return;
    }

    if (checked) {
      if (kind === 'english') {
        patchForm(prev => ({
          english_tests: toggleListValue(
            prev.english_tests,
            optionCode as EnglishTestOption,
            true
          ),
        }));
      } else {
        patchForm(prev => ({
          aptitude_tests: toggleListValue(
            prev.aptitude_tests,
            optionCode as AptitudeTestOption,
            true
          ),
        }));
      }
      openCapture(kind, optionCode, testName, { uncheckOnCancel: true });
    }
  };

  const closeCapture = () => {
    setCaptureTest(null);
    setCaptureKind(null);
    setCaptureOption(null);
    setCaptureEditingIds([]);
    setCaptureInitialForm(null);
    setCaptureUncheckOnCancel(true);
  };

  const revertOption = (kind: 'english' | 'aptitude', code: string) => {
    if (kind === 'english') {
      patchForm(prev => ({
        english_tests: prev.english_tests.filter(item => item !== code),
      }));
    } else {
      patchForm(prev => ({
        aptitude_tests: prev.aptitude_tests.filter(item => item !== code),
      }));
    }
  };

  const cancelCapture = () => {
    if (!captureOption || !captureKind) return;
    revertOption(captureKind, captureOption);
  };

  const englishScoreCards = useMemo(() => {
    return Array.from(ENGLISH_SCORE_TEST_NAMES)
      .map(testName => latestAttemptForTest(savedScores, testName))
      .filter((attempt): attempt is NonNullable<typeof attempt> => Boolean(attempt));
  }, [savedScores]);

  const aptitudeScoreCards = useMemo(() => {
    return Array.from(APTITUDE_SCORE_TEST_NAMES)
      .map(testName => latestAttemptForTest(savedScores, testName))
      .filter((attempt): attempt is NonNullable<typeof attempt> => Boolean(attempt));
  }, [savedScores]);

  const openExistingAttempt = (
    kind: 'english' | 'aptitude',
    testName: TestName
  ) => {
    if (!bookingId) return;
    const mapped = aspirationOptionForTestName(testName);
    openCapture(kind, mapped?.code || testName, testName, { uncheckOnCancel: false });
  };

  const handleDeleteSavedAttempt = async (attempt: GroupedTestAttempt) => {
    if (!bookingId) return;

    const testLabel = ASPIRATION_TEST_LABELS[attempt.test_name] || attempt.test_name;
    const scoreIdsForTest = savedScores
      .filter(record => record.test_name === attempt.test_name)
      .map(record => record.id);

    if (!scoreIdsForTest.length) {
      await showAlert({
        title: 'Nothing to delete',
        message: `No saved ${testLabel} scores were found.`,
        variant: 'warning',
      });
      return;
    }

    const confirmed = await openConfirm({
      title: `Delete saved ${testLabel} scores?`,
      message: `This will permanently delete the already saved ${testLabel} test scores for this candidate. This cannot be undone.`,
      confirmLabel: 'Delete scores',
      cancelLabel: 'Cancel',
      variant: 'danger',
    });
    if (!confirmed) return;

    try {
      setDeletingKey(attempt.key);
      const response = (await apiFetch(
        `bookings/mine/${bookingId}/test-scores/delete-attempt`,
        {
          method: 'POST',
          body: JSON.stringify({ score_ids: scoreIdsForTest }),
        }
      )) as CandidateTestScoresResponse;
      setSavedScores(response.scores);
      emitTestScoresChanged({ bookingId, source: 'aspirations' });
      const mapped = aspirationOptionForTestName(attempt.test_name);
      if (mapped) {
        revertOption(mapped.kind, mapped.code);
      }
      if (captureTest === attempt.test_name) {
        setCaptureTest(null);
        setCaptureKind(null);
        setCaptureOption(null);
        setCaptureEditingIds([]);
        setCaptureInitialForm(null);
      }
    } catch (err) {
      await showAlert({
        title: 'Delete failed',
        message:
          err instanceof Error
            ? err.message
            : `Failed to delete saved ${testLabel} scores. Please try again.`,
        variant: 'warning',
      });
    } finally {
      setDeletingKey(null);
    }
  };

  return (
    <>
      <AspirationSectionShell
        title="Timeline & Execution Readiness"
        progressLabel={`${
          ['ranking_tier', 'intake_year', 'test_prep'].filter(id =>
            isQuestionComplete(id as 'ranking_tier', form)
          ).length
        }/3 complete`}
      >
        <div className="space-y-5">
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 items-start">
        <AspirationBlock
          code={q7.code}
          title={q7.title}
          complete={isQuestionComplete('ranking_tier', form)}
        >
          <OptionCardGroup
            name="global_ranking"
            options={ASPIRATION_OPTION_CATALOGS.ranking_tiers}
            value=""
            onChange={() => undefined}
            multi
            selectedValues={form.global_ranking}
            onToggle={(value, checked) => {
              patchForm(prev => ({
                global_ranking: toggleListValue(
                  prev.global_ranking,
                  value as GlobalRankingOption,
                  checked
                ),
              }));
            }}
            columns="fit"
            hasError={hasError(['ranking'])}
          />
        </AspirationBlock>

        <AspirationBlock
          code={q8.code}
          title={q8.title}
          complete={isQuestionComplete('intake_year', form)}
        >
          <div className="space-y-4">
            <div className="flex flex-nowrap items-stretch gap-2 min-w-0">
              <div
                className="min-w-0 flex-1 flex flex-nowrap gap-2 overflow-x-auto"
                role="radiogroup"
                aria-label="Academic calendar system"
              >
                {INTAKE_CALENDAR_SYSTEMS.map(system => {
                  const checked = form.intake_calendar_system === system.value;
                  return (
                    <label
                      key={system.value}
                      className={`min-w-0 flex-1 flex items-start gap-2.5 rounded-lg border px-3 py-2.5 text-sm cursor-pointer transition-colors ${
                        hasError(['intake calendar', 'intended intake'])
                          ? 'border-red-300 ring-1 ring-red-100'
                          : 'border-border-subtle'
                      } ${
                        checked
                          ? 'bg-primary/5 border-primary/40'
                          : 'bg-surface-bg/50 hover:bg-surface-bg'
                      }`}
                    >
                      <input
                        type="radio"
                        name="intake_calendar_system"
                        className="mt-0.5 shrink-0"
                        value={system.value}
                        checked={checked}
                        onChange={() =>
                          patchForm({
                            intake_calendar_system: system.value,
                            intake_terms: [],
                            intake_seasons: [],
                            intake_season_other: '',
                          })
                        }
                      />
                      <span className="min-w-0">
                        <span className="font-semibold block leading-snug">{system.label}</span>
                        <span className="block text-xs text-text-muted mt-0.5 leading-snug">
                          {system.terms.map(term => term.label).join(' · ')}
                        </span>
                      </span>
                    </label>
                  );
                })}
              </div>

              <div className="w-[8.5rem] shrink-0 self-stretch flex">
                <SearchableMultiSelect
                  id="q8-intake-years"
                  values={form.intake_years.map(String)}
                  options={intakeYears.map(year => ({
                    value: String(year),
                    label: String(year),
                  }))}
                  onChange={values => {
                    const nextYears = values
                      .map(value => Number(value))
                      .filter(year => Number.isFinite(year))
                      .sort((a, b) => a - b);
                    patchForm({ intake_years: nextYears });
                  }}
                  placeholder="Select Year"
                  emptyMessage="No intake years available."
                  selectedDisplay={
                    form.intake_years.length
                      ? form.intake_years.length === 1
                        ? String(form.intake_years[0])
                        : `${form.intake_years.length} years`
                      : undefined
                  }
                  className={`flex h-full w-full flex-col justify-center ${
                    hasError(['intake year']) ? 'rounded-md ring-1 ring-red-200' : ''
                  } [&>div]:h-full [&>div>button]:h-full [&>div>button]:rounded-lg`.trim()}
                />
              </div>
            </div>

            {form.intake_calendar_system ? (
              <div>
                <p className={fieldLabelClass}>
                  {INTAKE_CALENDAR_SYSTEMS.find(
                    item => item.value === form.intake_calendar_system
                  )?.label || 'Intake'}{' '}
                  terms
                </p>
                <div
                  className="flex flex-nowrap gap-2 overflow-x-auto"
                  role="group"
                  aria-label="Intake terms"
                >
                  {termsForCalendarSystem(
                    form.intake_calendar_system as IntakeCalendarSystemOption
                  ).map(term => {
                    const checked = form.intake_terms.includes(term.value);
                    return (
                      <label
                        key={term.value}
                        className={`min-w-0 flex-1 flex items-center gap-2.5 rounded-lg border px-3 py-2.5 text-sm cursor-pointer transition-colors ${
                          hasError(['intake term'])
                            ? 'border-red-300 ring-1 ring-red-100'
                            : 'border-border-subtle'
                        } ${
                          checked
                            ? 'bg-primary/5 border-primary/40'
                            : 'bg-surface-bg/50 hover:bg-surface-bg'
                        }`}
                      >
                        <input
                          type="checkbox"
                          className="shrink-0"
                          value={term.value}
                          checked={checked}
                          onChange={event => {
                            patchForm(prev => ({
                              intake_terms: toggleListValue(
                                prev.intake_terms,
                                term.value as IntakeTermOption,
                                event.target.checked
                              ),
                            }));
                          }}
                        />
                        <span className="font-semibold leading-snug">{term.label}</span>
                      </label>
                    );
                  })}
                </div>
              </div>
            ) : null}
          </div>
        </AspirationBlock>
        </div>

        <AspirationBlock
          code={q9.code}
          title={q9.title}
          complete={isQuestionComplete('test_prep', form)}
        >
          <p className={fieldLabelClass}>English proficiency</p>
          <OptionCardGroup
            name="english_tests"
            options={ASPIRATION_OPTION_CATALOGS.english_tests}
            value=""
            onChange={() => undefined}
            multi
            selectedValues={form.english_tests}
            onToggle={(value, checked) => handleTestToggle('english', value, checked)}
            columns="fit"
            hasError={hasError(['english'])}
          />
          {englishScoreCards.length > 0 ? (
            <div className="mt-3 space-y-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
                Saved English scores
              </p>
              <div className="grid grid-cols-4 gap-2">
                {englishScoreCards.map(attempt => (
                  <div
                    key={attempt.key}
                    className="min-w-0 rounded-lg border border-emerald-200 bg-emerald-50/70 px-3 py-2"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-bold text-text-main">
                        {ASPIRATION_TEST_LABELS[attempt.test_name] || attempt.test_name}
                      </span>
                      {formatAttemptDateLabel(attempt) ? (
                        <span className="text-xs text-text-muted">
                          {formatAttemptDateLabel(attempt)}
                        </span>
                      ) : null}
                    </div>
                    <p className="mt-1 text-sm text-text-main leading-snug">
                      {formatAttemptScoreSummary(attempt)}
                    </p>
                    <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
                      <button
                        type="button"
                        onClick={() => openExistingAttempt('english', attempt.test_name)}
                        className="text-xs font-semibold text-emerald-800 hover:underline"
                      >
                        View / edit
                      </button>
                      <button
                        type="button"
                        disabled={deletingKey === attempt.key}
                        onClick={() => handleDeleteSavedAttempt(attempt)}
                        className="text-xs font-semibold text-red-700 hover:underline disabled:opacity-50"
                      >
                        {deletingKey === attempt.key ? 'Deleting…' : 'Delete'}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          <div className="mt-4">
            <p className={fieldLabelClass}>Aptitude tests</p>
            <OptionCardGroup
              name="aptitude_tests"
              options={ASPIRATION_OPTION_CATALOGS.aptitude_tests}
              value=""
              onChange={() => undefined}
              multi
              selectedValues={form.aptitude_tests}
              onToggle={(value, checked) => handleTestToggle('aptitude', value, checked)}
              columns="fit"
              hasError={hasError(['aptitude'])}
            />
            {aptitudeScoreCards.length > 0 ? (
              <div className="mt-3 space-y-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
                  Saved aptitude scores
                </p>
                <div className="grid grid-cols-4 gap-2">
                  {aptitudeScoreCards.map(attempt => (
                    <div
                      key={attempt.key}
                      className="min-w-0 rounded-lg border border-sky-200 bg-sky-50/70 px-3 py-2"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-bold text-text-main">
                          {ASPIRATION_TEST_LABELS[attempt.test_name] || attempt.test_name}
                        </span>
                        {formatAttemptDateLabel(attempt) ? (
                          <span className="text-xs text-text-muted">
                            {formatAttemptDateLabel(attempt)}
                          </span>
                        ) : null}
                      </div>
                      <p className="mt-1 text-sm text-text-main leading-snug">
                        {formatAttemptScoreSummary(attempt)}
                      </p>
                      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
                        <button
                          type="button"
                          onClick={() => openExistingAttempt('aptitude', attempt.test_name)}
                          className="text-xs font-semibold text-sky-800 hover:underline"
                        >
                          View / edit
                        </button>
                        <button
                          type="button"
                          disabled={deletingKey === attempt.key}
                          onClick={() => handleDeleteSavedAttempt(attempt)}
                          className="text-xs font-semibold text-red-700 hover:underline disabled:opacity-50"
                        >
                          {deletingKey === attempt.key ? 'Deleting…' : 'Delete'}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </AspirationBlock>
        </div>
      </AspirationSectionShell>

      {bookingId && captureTest ? (
        <TestScoreCaptureModal
          open
          bookingId={bookingId}
          initialTestName={captureTest}
          editingScoreIds={captureEditingIds}
          initialForm={captureInitialForm}
          uncheckOnCancel={captureUncheckOnCancel}
          source="aspirations"
          onClose={closeCapture}
          onCancel={cancelCapture}
          onSaved={() => {
            loadScores().catch(() => undefined);
          }}
        />
      ) : null}
    </>
  );
}
