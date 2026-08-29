import React, { useEffect, useId, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ChevronLeft, ChevronRight, Loader2, UserRound, X } from 'lucide-react';
import { useBusinessTimezone } from '../context/BusinessTimezoneContext';
import { useGpaCgpaScores } from '../hooks/useGpaCgpaScores';
import type { CountryRecord } from '../types/country';
import type { LevelRecord } from '../types/level';
import type { QualificationProgramRecord } from '../types/qualificationProgram';
import type { StudentAspirationsFormState } from '../types/studentAspirations';
import {
  buildStudentProfilePreviewModel,
  joinLabels,
  type ProfileInstitutionOption,
} from '../utils/studentProfilePreview';

export type CreateProfileInstitutionOption = ProfileInstitutionOption;

interface CreateProfileModalProps {
  open: boolean;
  onClose: () => void;
  candidateName: string;
  loading?: boolean;
  aspirations: StudentAspirationsFormState | null;
  countries: CountryRecord[];
  levels: LevelRecord[];
  qualificationPrograms: QualificationProgramRecord[];
  selectedInstitutions: ProfileInstitutionOption[];
  selectedLevelId: string;
  selectedMajorIds: string[];
  selectedProgramIds: Array<number | string>;
  scholarshipInterests?: string;
}

const CreateProfileModal: React.FC<CreateProfileModalProps> = ({
  open,
  onClose,
  candidateName,
  loading = false,
  aspirations,
  countries,
  levels,
  qualificationPrograms,
  selectedInstitutions,
  selectedLevelId,
  selectedMajorIds,
  selectedProgramIds,
  scholarshipInterests = '',
}) => {
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const { formatDateTime } = useBusinessTimezone();
  const { scores } = useGpaCgpaScores();
  const [viewPage, setViewPage] = useState<1 | 2>(1);
  const [generatedAt] = useState(() => new Date());

  useEffect(() => {
    if (!open) return;
    setViewPage(1);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    window.requestAnimationFrame(() => closeButtonRef.current?.focus());

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [open, onClose]);

  const standingLabels = useMemo(
    () => Object.fromEntries(scores.map(score => [score.code, score.label])),
    [scores]
  );

  const model = useMemo(
    () =>
      buildStudentProfilePreviewModel({
        candidateName,
        generatedAtLabel: formatDateTime(generatedAt, { second: undefined }),
        aspirations,
        countries,
        levels,
        standingLabels,
        qualificationPrograms,
        selectedInstitutions,
        selectedLevelId,
        selectedMajorIds,
        selectedProgramIds,
        scholarshipInterests,
      }),
    [
      aspirations,
      candidateName,
      countries,
      formatDateTime,
      generatedAt,
      levels,
      qualificationPrograms,
      scholarshipInterests,
      selectedInstitutions,
      selectedLevelId,
      selectedMajorIds,
      selectedProgramIds,
      standingLabels,
    ]
  );

  if (!open || typeof document === 'undefined') return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[400] flex items-center justify-center bg-black/45 p-4"
      onMouseDown={onClose}
      role="presentation"
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="flex max-h-[92vh] w-full max-w-6xl flex-col overflow-hidden rounded-2xl border border-border-subtle bg-card shadow-2xl"
        onMouseDown={event => event.stopPropagation()}
      >
        <div className="flex shrink-0 items-start justify-between gap-3 border-b border-border-subtle bg-surface-bg px-5 py-4">
          <div className="min-w-0">
            <h2
              id={titleId}
              className="text-2xl sm:text-3xl font-bold tracking-tight text-text-main"
            >
              Student Profile Preview
            </h2>
            <p className="mt-1.5 flex items-center gap-1.5 text-sm text-text-muted">
              <UserRound size={14} className="shrink-0" />
              <span className="font-semibold text-text-main">{candidateName}</span>
            </p>
          </div>
          <div className="flex items-start gap-3">
            <div className="text-right">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
                Date &amp; Time
              </p>
              <p className="mt-0.5 text-sm font-semibold text-text-main">
                {model.generatedAtLabel}
              </p>
            </div>
            <button
              ref={closeButtonRef}
              type="button"
              onClick={onClose}
              className="rounded-lg border border-border-subtle p-2 text-text-muted hover:bg-card hover:text-text-main"
              aria-label="Close student profile preview"
            >
              <X size={16} />
            </button>
          </div>
        </div>

        <div className="flex shrink-0 items-center justify-between gap-3 border-b border-border-subtle px-5 py-2.5">
          <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
            {viewPage === 1 ? 'Page 1 · Aspirations' : 'Page 2 · Recommended Institutions'}
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={viewPage === 1}
              onClick={() => setViewPage(1)}
              className="inline-flex items-center gap-1 rounded-lg border border-border-subtle px-2.5 py-1.5 text-xs font-semibold text-text-main hover:bg-surface-bg disabled:opacity-40"
            >
              <ChevronLeft size={14} />
              Prev
            </button>
            <button
              type="button"
              disabled={viewPage === 2}
              onClick={() => setViewPage(2)}
              className="inline-flex items-center gap-1 rounded-lg border border-border-subtle px-2.5 py-1.5 text-xs font-semibold text-text-main hover:bg-surface-bg disabled:opacity-40"
            >
              Next
              <ChevronRight size={14} />
            </button>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto custom-scrollbar px-5 py-5">
          {loading ? (
            <div className="flex items-center justify-center gap-2 py-16 text-text-muted">
              <Loader2 size={18} className="animate-spin" />
              Loading profile…
            </div>
          ) : viewPage === 1 ? (
            <section className="space-y-3">
              <div>
                <h3 className="text-base font-semibold text-text-main">Aspirations</h3>
                <p className="text-xs text-text-muted mt-0.5">
                  Condensed questionnaire responses in structured form.
                </p>
              </div>
              {model.aspirationSections.length === 0 ? (
                <div className="rounded-xl border border-dashed border-border-subtle px-4 py-8 text-center text-sm text-text-muted">
                  No aspiration answers available yet.
                </div>
              ) : (
                <div className="space-y-3">
                  {model.aspirationSections.map(section => (
                    <div
                      key={section.id}
                      className="overflow-hidden rounded-lg border border-border-subtle"
                    >
                      <div className="border-b border-border-subtle bg-surface-bg px-3 py-1.5">
                        <p className="text-[11px] font-bold uppercase tracking-wide text-text-muted">
                          {section.title}
                        </p>
                      </div>
                      <dl className="divide-y divide-border-subtle">
                        {section.items.map(item => (
                          <div
                            key={item.code}
                            className="grid grid-cols-1 sm:grid-cols-[minmax(11rem,32%)_1fr] gap-x-3 gap-y-0.5 px-3 py-2"
                          >
                            <dt className="text-xs font-semibold text-text-muted leading-snug">
                              <span className="text-violet-700">{item.code}</span>
                              <span className="mx-1 text-border-subtle">·</span>
                              {item.question}
                            </dt>
                            <dd className="text-sm text-text-main leading-snug">
                              {item.answer}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    </div>
                  ))}
                </div>
              )}
            </section>
          ) : (
            <section className="space-y-4">
              <div>
                <h3 className="text-base font-semibold text-text-main">
                  Recommended Institutions by Country
                </h3>
                <p className="text-xs text-text-muted mt-0.5">
                  Grouped by country, then college / institution details.
                </p>
              </div>

              {model.countryGroups.length === 0 ? (
                <div className="rounded-xl border border-dashed border-border-subtle px-4 py-8 text-center text-sm text-text-muted">
                  Select recommended institutions on the Session form to include them here.
                </div>
              ) : (
                model.countryGroups.map(group => (
                  <div
                    key={group.countryKey}
                    className="overflow-hidden rounded-xl border border-border-subtle"
                  >
                    <div className="border-b border-border-subtle bg-violet-50/70 px-4 py-2.5">
                      <p className="text-xs font-semibold uppercase tracking-wide text-violet-800">
                        Country
                      </p>
                      <p className="text-base font-bold text-text-main">{group.countryName}</p>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="min-w-full text-sm">
                        <thead className="bg-surface-bg text-left text-[11px] uppercase tracking-wide text-text-muted">
                          <tr>
                            <th className="px-3 py-2 font-semibold">College / Institution</th>
                            <th className="px-3 py-2 font-semibold">State</th>
                            <th className="px-3 py-2 font-semibold">City</th>
                            <th className="px-3 py-2 font-semibold">Level</th>
                            <th className="px-3 py-2 font-semibold">Majors</th>
                            <th className="px-3 py-2 font-semibold">Programs</th>
                            <th className="px-3 py-2 font-semibold">English Proficiency</th>
                            <th className="px-3 py-2 font-semibold">Aptitude Test</th>
                            <th className="px-3 py-2 font-semibold">Average Cost</th>
                            <th className="px-3 py-2 font-semibold">Backlog Accepted</th>
                            <th className="px-3 py-2 font-semibold">Scholarship</th>
                          </tr>
                        </thead>
                        <tbody>
                          {group.colleges.map(college => (
                            <tr
                              key={college.value}
                              className="border-t border-border-subtle align-top"
                            >
                              <td className="px-3 py-2.5 font-semibold text-text-main">
                                {college.name}
                                <span className="mt-0.5 block text-[11px] font-medium uppercase tracking-wide text-text-muted">
                                  {college.kind === 'college' ? 'College' : 'Institution'}
                                </span>
                              </td>
                              <td className="px-3 py-2.5 text-text-main">
                                {college.state_name || '—'}
                              </td>
                              <td className="px-3 py-2.5 text-text-main">
                                {college.city_name || '—'}
                              </td>
                              <td className="px-3 py-2.5 text-text-main">{model.levelLabel}</td>
                              <td className="px-3 py-2.5 text-text-main">
                                {joinLabels(model.majorLabels)}
                              </td>
                              <td className="px-3 py-2.5 text-text-main">
                                {joinLabels(model.programLabels)}
                              </td>
                              <td className="px-3 py-2.5 text-text-main">
                                {joinLabels(model.englishLabels)}
                              </td>
                              <td className="px-3 py-2.5 text-text-main">
                                {joinLabels(model.aptitudeLabels)}
                              </td>
                              <td className="px-3 py-2.5 text-text-muted">—</td>
                              <td className="px-3 py-2.5 text-text-muted">—</td>
                              <td className="px-3 py-2.5 text-text-main">
                                {model.scholarshipLabel}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ))
              )}
            </section>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
};

export default CreateProfileModal;
