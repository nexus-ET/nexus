import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Loader2, Pencil, Trash2 } from 'lucide-react';
import { apiFetch } from '../utils/api';
import { useConfirmation } from '../context/ConfirmationContext';
import EmptyListMessage from './ui/EmptyListMessage';
import { findEducationDegree, useEducationDegrees } from '../hooks/useEducationDegrees';
import {
  findQualificationProgram,
  useQualificationPrograms,
} from '../hooks/useQualificationPrograms';
import { useLevels } from '../hooks/useLevels';
import { levelSelectOptions } from '../constants/levels';
import { useEducationMajors } from '../hooks/useEducationMajors';
import { findGpaCgpaScore, useGpaCgpaScores } from '../hooks/useGpaCgpaScores';
import {
  useFullTimeStudyYears,
  findFullTimeStudyYear,
  filterFullTimeStudyYearsByLevel,
} from '../hooks/useFullTimeStudyYears';
import {
  GRADUATION_MONTH_OPTIONS,
  emptyCandidateEducationForm,
  educationToForm,
  formToEducationPayload,
  sortEducationsByDegreeOrder,
  validateCandidateEducationForm,
  type CandidateEducationFormState,
  type CandidateEducationRecord,
  type CandidateEducationsResponse,
} from '../types/candidateEducation';
import {
  studentInfoFieldErrorClass as fieldErrorClass,
  studentInfoInputClass as inputClass,
  studentInfoLabelClass as labelClass,
} from './studentInfoFormStyles';

interface CandidateEducationsTabProps {
  bookingId: number;
  compact?: boolean;
}

const fieldClass = (hasError: boolean) =>
  `${inputClass}${hasError ? ' border-red-400 ring-1 ring-red-200' : ''}`;

const RequiredLabel: React.FC<{ htmlFor?: string; children: React.ReactNode }> = ({
  htmlFor,
  children,
}) => (
  <label htmlFor={htmlFor} className={labelClass}>
    {children}
    <span className="text-red-600" aria-hidden="true">
      {' '}
      *
    </span>
  </label>
);

const CandidateEducationsTab: React.FC<CandidateEducationsTabProps> = ({
  bookingId,
  compact = false,
}) => {
  const openConfirm = useConfirmation();
  const [educations, setEducations] = useState<CandidateEducationRecord[]>([]);
  const [form, setForm] = useState<CandidateEducationFormState>(emptyCandidateEducationForm);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [levelId, setLevelId] = useState('');

  const { levels } = useLevels();
  const { programs: qualificationPrograms } = useQualificationPrograms();
  const { degrees: allDegrees } = useEducationDegrees();
  const filteredPrograms = useMemo(() => {
    if (!levelId) return [];
    return qualificationPrograms.filter(program => program.level_id === Number(levelId));
  }, [qualificationPrograms, levelId]);
  const { majors } = useEducationMajors();
  const selectedProgram = useMemo(
    () => findQualificationProgram(qualificationPrograms, form.degree_code),
    [qualificationPrograms, form.degree_code]
  );
  const mappedProgramMajors = selectedProgram?.majors ?? [];
  const filteredMajors = useMemo(() => {
    const otherMajors = majors.filter(major => major.is_other);
    if (!form.degree_code || !mappedProgramMajors.length) {
      return majors;
    }
    const labels = new Set(mappedProgramMajors.map(major => major.label.trim().toLowerCase()));
    const codes = new Set(
      mappedProgramMajors
        .map(major => (major.code || '').trim().toUpperCase())
        .filter(Boolean)
    );
    const matched = majors.filter(
      major =>
        !major.is_other &&
        (labels.has(major.label.trim().toLowerCase()) ||
          Boolean(major.code && codes.has(major.code.trim().toUpperCase())))
    );
    if (matched.length) {
      return [...matched, ...otherMajors];
    }
    return [
      ...mappedProgramMajors.map(major => ({
        id: major.id,
        code: major.code,
        label: major.label,
        is_other: false,
        sort_order: 0,
        is_active: true,
      })),
      ...otherMajors,
    ];
  }, [form.degree_code, majors, mappedProgramMajors]);
  const { scores: gpaCgpaScores } = useGpaCgpaScores();
  const { options: studyYearOptions } = useFullTimeStudyYears();
  const filteredStudyYears = useMemo(
    () => filterFullTimeStudyYearsByLevel(studyYearOptions, levelId),
    [studyYearOptions, levelId]
  );
  const selectedGpa = useMemo(
    () => findGpaCgpaScore(gpaCgpaScores, form.gpa_cgpa_code),
    [gpaCgpaScores, form.gpa_cgpa_code]
  );

  const apiPath = `bookings/mine/${bookingId}/educations`;
  const validationErrors = useMemo(
    () =>
      validateCandidateEducationForm(form, {
        gpaIsOther: selectedGpa?.is_other,
      }),
    [form, selectedGpa?.is_other]
  );
  const canSave = Object.keys(validationErrors).length === 0 && !saving;

  const sortedEducations = useMemo(
    () =>
      sortEducationsByDegreeOrder(
        educations,
        qualificationPrograms.map(program => ({
          code: program.code,
          sort_order: program.sort_order,
        }))
      ),
    [educations, qualificationPrograms]
  );

  const loadEducations = useCallback(async () => {
    const response = (await apiFetch(apiPath)) as CandidateEducationsResponse;
    setEducations(response.educations);
  }, [apiPath]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setSuccess(null);

    loadEducations()
      .catch(err => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Failed to load education records.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [loadEducations]);

  const resetForm = () => {
    setForm(emptyCandidateEducationForm());
    setLevelId('');
    setEditingId(null);
    setFieldErrors({});
  };

  const handleCancelForm = () => {
    resetForm();
    setError(null);
  };

  const updateForm = (patch: Partial<CandidateEducationFormState>) => {
    setForm(prev => ({ ...prev, ...patch }));
    setSuccess(null);
    const clearedKeys = Object.keys(patch);
    if (clearedKeys.length) {
      setFieldErrors(prev => {
        const next = { ...prev };
        clearedKeys.forEach(key => delete next[key]);
        return next;
      });
    }
  };

  const handleEdit = (education: CandidateEducationRecord) => {
    const nextForm = educationToForm(education, majors);
    setForm(nextForm);
    const program = findQualificationProgram(qualificationPrograms, nextForm.degree_code);
    const legacyDegree = findEducationDegree(allDegrees, nextForm.degree_code);
    const resolvedLevelId = program?.level_id ?? legacyDegree?.level_id;
    const studyYear = findFullTimeStudyYear(
      studyYearOptions,
      nextForm.full_time_study_years,
      resolvedLevelId
    );
    setLevelId(
      studyYear?.level_id
        ? String(studyYear.level_id)
        : resolvedLevelId
          ? String(resolvedLevelId)
          : ''
    );
    setEditingId(education.id);
    setError(null);
    setSuccess(null);
    setFieldErrors({});
  };

  const handleDelete = async (educationId: number) => {
    if (
      !(await openConfirm({
        title: 'Delete education record?',
        message: 'Delete this education record?',
        confirmLabel: 'Delete',
        variant: 'danger',
      }))
    ) {
      return;
    }

    try {
      setDeletingId(educationId);
      setError(null);
      setSuccess(null);
      const response = (await apiFetch(`${apiPath}/${educationId}`, {
        method: 'DELETE',
      })) as CandidateEducationsResponse;
      setEducations(response.educations);
      if (editingId === educationId) {
        resetForm();
      }
      setSuccess('Education record deleted.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete education record.');
    } finally {
      setDeletingId(null);
    }
  };

  const handleSave = async (event: React.FormEvent) => {
    event.preventDefault();
    const errors = validateCandidateEducationForm(form, {
      gpaIsOther: selectedGpa?.is_other,
    });
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      setError('Please complete all required fields before saving.');
      setSuccess(null);
      return;
    }

    try {
      setSaving(true);
      setError(null);
      setSuccess(null);
      setFieldErrors({});
      const response = (await apiFetch(editingId ? `${apiPath}/${editingId}` : apiPath, {
        method: editingId ? 'PUT' : 'POST',
        body: JSON.stringify(formToEducationPayload(form)),
      })) as CandidateEducationsResponse;
      setEducations(response.educations);
      resetForm();
      setSuccess(editingId ? 'Education updated.' : 'Education added.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save education record.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-text-muted">
        <Loader2 size={22} className="animate-spin mr-2" />
        Loading education records...
      </div>
    );
  }

  const recordsTable = (
    <div className="rounded-xl border border-border-subtle bg-surface-bg/40 p-4 space-y-3 h-full">
      <div>
        <h4 className="text-sm font-semibold text-text-main">Academic records on file</h4>
        <p className="text-xs text-text-muted mt-0.5">
          Transcripts / GPA history from the candidate profile.
        </p>
      </div>
      {educations.length === 0 ? (
        <EmptyListMessage
          compact
          message="No education records yet. Use the form on the right to add one."
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border-subtle">
          <table className="min-w-full text-left text-xs">
            <thead className="bg-surface-bg text-text-muted">
              <tr>
                <th className="px-3 py-2 font-semibold">Institution</th>
                <th className="px-3 py-2 font-semibold">Degree</th>
                <th className="px-3 py-2 font-semibold">GPA / Scale</th>
                <th className="px-3 py-2 font-semibold">Grad</th>
                <th className="px-3 py-2 font-semibold text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {sortedEducations.map(edu => (
                <tr
                  key={edu.id}
                  className={`border-t border-border-subtle bg-card ${
                    editingId === edu.id ? 'ring-1 ring-inset ring-sky-300' : ''
                  }`}
                >
                  <td className="px-3 py-2 text-text-main">{edu.university_name || '—'}</td>
                  <td className="px-3 py-2 text-text-main">
                    {[edu.degree_label, edu.major].filter(Boolean).join(' · ') || '—'}
                  </td>
                  <td className="px-3 py-2 text-text-main">
                    {edu.gpa_cgpa_label || edu.gpa_cgpa_code || '—'}
                  </td>
                  <td className="px-3 py-2 text-text-main">
                    {edu.graduation_month && edu.graduation_year
                      ? `${edu.graduation_month}/${edu.graduation_year}`
                      : edu.graduation_year || '—'}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex items-center justify-end gap-1.5">
                      <button
                        type="button"
                        onClick={() => handleEdit(edu)}
                        className="inline-flex items-center gap-1 rounded-md border border-sky-200 bg-sky-50 px-2 py-1 text-[11px] font-semibold text-sky-800 hover:bg-sky-100"
                        aria-label={`Edit ${edu.university_name || 'education record'}`}
                      >
                        <Pencil size={12} />
                        Edit
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleDelete(edu.id)}
                        disabled={deletingId === edu.id}
                        className="inline-flex items-center gap-1 rounded-md border border-red-200 bg-red-50 px-2 py-1 text-[11px] font-semibold text-red-700 hover:bg-red-100 disabled:opacity-60"
                        aria-label={`Delete ${edu.university_name || 'education record'}`}
                      >
                        {deletingId === edu.id ? (
                          <Loader2 size={12} className="animate-spin" />
                        ) : (
                          <Trash2 size={12} />
                        )}
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );

  const institutionForm = (
    <form
      onSubmit={handleSave}
      className="rounded-xl border border-border-subtle bg-card p-4 space-y-3 h-full"
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <h4 className="text-sm font-semibold text-text-main">
            {editingId ? 'Edit institution' : 'Add institution'}
          </h4>
          <p className="text-xs text-text-muted mt-0.5">
            Capture degree, major, school, graduation, and GPA details.
          </p>
        </div>
        {editingId ? (
          <button
            type="button"
            onClick={handleCancelForm}
            className="text-xs font-semibold text-text-muted hover:text-text-main"
          >
            Clear / New
          </button>
        ) : null}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <div>
          <RequiredLabel htmlFor="education-course-level">Levels</RequiredLabel>
          <select
            id="education-course-level"
            className={fieldClass(false)}
            value={levelId}
            onChange={e => {
              const nextLevelId = e.target.value;
              setLevelId(nextLevelId);
              updateForm({
                full_time_study_years: '',
                degree_code: '',
                degree_other: '',
                major: '',
                major_custom: '',
              });
            }}
          >
            <option value="">Select level</option>
            {levelSelectOptions(levels).map(option => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <RequiredLabel htmlFor="education-study-years">Full-Time Study Years</RequiredLabel>
          <select
            id="education-study-years"
            className={fieldClass(Boolean(fieldErrors.full_time_study_years))}
            value={form.full_time_study_years}
            disabled={!levelId}
            onChange={e => updateForm({ full_time_study_years: e.target.value })}
          >
            <option value="">
              {levelId
                ? filteredStudyYears.length
                  ? 'Select study years'
                  : 'No study years for this level'
                : 'Select level first'}
            </option>
            {filteredStudyYears.map(option => (
              <option key={option.code} value={option.code}>
                {option.label}
              </option>
            ))}
          </select>
          {fieldErrors.full_time_study_years ? (
            <p className={fieldErrorClass}>{fieldErrors.full_time_study_years}</p>
          ) : null}
        </div>
        <div className="sm:col-span-2">
          <RequiredLabel htmlFor="education-program">Current Programs</RequiredLabel>
          <select
            id="education-program"
            className={fieldClass(Boolean(fieldErrors.degree_code))}
            value={form.degree_code}
            disabled={!levelId}
            onChange={e => {
              const nextCode = e.target.value;
              const program = findQualificationProgram(qualificationPrograms, nextCode);
              const mapped = program?.majors ?? [];
              const autoMajor = mapped.length === 1 ? mapped[0].label : '';
              updateForm({
                degree_code: nextCode,
                degree_other: '',
                major: autoMajor,
                major_custom: '',
              });
            }}
          >
            <option value="">
              {levelId
                ? filteredPrograms.length
                  ? 'Select program'
                  : 'No programs for this level'
                : 'Select level first'}
            </option>
            {filteredPrograms.map(program => (
              <option key={program.code} value={program.code}>
                {program.name}
              </option>
            ))}
          </select>
          {fieldErrors.degree_code ? (
            <p className={fieldErrorClass}>{fieldErrors.degree_code}</p>
          ) : null}
        </div>

        <div className="sm:col-span-2">
          <RequiredLabel htmlFor="education-major">Current Major</RequiredLabel>
          <select
            id="education-major"
            className={fieldClass(Boolean(fieldErrors.major))}
            disabled={!form.degree_code}
            value={
              filteredMajors.some(major => !major.is_other && major.label === form.major)
                ? form.major
                : form.major || form.major_custom
                  ? 'Other'
                  : ''
            }
            onChange={e => {
              const value = e.target.value;
              if (value === 'Other') {
                updateForm({ major: 'Other', major_custom: form.major_custom || '' });
              } else {
                updateForm({ major: value, major_custom: '' });
              }
            }}
          >
            <option value="">
              {form.degree_code
                ? mappedProgramMajors.length > 1
                  ? 'Select major'
                  : filteredMajors.some(major => !major.is_other)
                    ? 'Select major'
                    : 'No majors for this program'
                : 'Select program first'}
            </option>
            {filteredMajors.map(major => (
              <option key={major.code || major.id} value={major.is_other ? 'Other' : major.label}>
                {major.label}
              </option>
            ))}
          </select>
          {(form.major === 'Other' ||
            (!filteredMajors.some(major => !major.is_other && major.label === form.major) &&
              Boolean(form.major_custom || form.major))) && (
            <input
              className={`${fieldClass(Boolean(fieldErrors.major))} mt-1`}
              value={form.major === 'Other' ? form.major_custom : form.major}
              onChange={e => updateForm({ major: 'Other', major_custom: e.target.value })}
              placeholder="Enter major"
            />
          )}
          {fieldErrors.major ? <p className={fieldErrorClass}>{fieldErrors.major}</p> : null}
        </div>

        <div className="sm:col-span-2">
          <RequiredLabel htmlFor="education-university">School / University Name</RequiredLabel>
          <input
            id="education-university"
            className={fieldClass(Boolean(fieldErrors.university_name))}
            value={form.university_name}
            onChange={e => updateForm({ university_name: e.target.value })}
          />
          {fieldErrors.university_name ? (
            <p className={fieldErrorClass}>{fieldErrors.university_name}</p>
          ) : null}
        </div>

        <div className="sm:col-span-2">
          <label htmlFor="education-affiliation" className={labelClass}>
            University Affiliation
          </label>
          <input
            id="education-affiliation"
            className={inputClass}
            value={form.university_affiliation}
            onChange={e => updateForm({ university_affiliation: e.target.value })}
            placeholder="e.g. State University System"
          />
        </div>

        <div>
          <RequiredLabel htmlFor="education-graduation-month">Graduation Month</RequiredLabel>
          <select
            id="education-graduation-month"
            className={fieldClass(Boolean(fieldErrors.graduation_month))}
            value={form.graduation_month}
            onChange={e => updateForm({ graduation_month: e.target.value })}
          >
            <option value="">Select month</option>
            {GRADUATION_MONTH_OPTIONS.map(option => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          {fieldErrors.graduation_month ? (
            <p className={fieldErrorClass}>{fieldErrors.graduation_month}</p>
          ) : null}
        </div>

        <div>
          <RequiredLabel htmlFor="education-graduation-year">Graduation Year</RequiredLabel>
          <input
            id="education-graduation-year"
            type="number"
            min={1950}
            max={2100}
            className={fieldClass(Boolean(fieldErrors.graduation_year))}
            value={form.graduation_year}
            onChange={e => updateForm({ graduation_year: e.target.value })}
          />
          {fieldErrors.graduation_year ? (
            <p className={fieldErrorClass}>{fieldErrors.graduation_year}</p>
          ) : null}
        </div>

        <div className="sm:col-span-2">
          <RequiredLabel htmlFor="education-gpa">GPA / CGPA Scores</RequiredLabel>
          <select
            id="education-gpa"
            className={fieldClass(Boolean(fieldErrors.gpa_cgpa_code))}
            value={form.gpa_cgpa_code}
            onChange={e => {
              const nextCode = e.target.value;
              const nextScore = findGpaCgpaScore(gpaCgpaScores, nextCode);
              updateForm({
                gpa_cgpa_code: nextCode,
                gpa_cgpa_other: nextScore?.is_other ? form.gpa_cgpa_other : '',
              });
            }}
          >
            <option value="">Select GPA / CGPA</option>
            {gpaCgpaScores.map(score => (
              <option key={score.code} value={score.code}>
                {score.label}
              </option>
            ))}
          </select>
          {fieldErrors.gpa_cgpa_code ? (
            <p className={fieldErrorClass}>{fieldErrors.gpa_cgpa_code}</p>
          ) : null}
          {selectedGpa?.is_other ? (
            <input
              className={`${fieldClass(Boolean(fieldErrors.gpa_cgpa_other))} mt-1`}
              value={form.gpa_cgpa_other}
              onChange={e => updateForm({ gpa_cgpa_other: e.target.value })}
              placeholder="Enter GPA / CGPA"
            />
          ) : null}
          {fieldErrors.gpa_cgpa_other ? (
            <p className={fieldErrorClass}>{fieldErrors.gpa_cgpa_other}</p>
          ) : null}
        </div>
      </div>

      <div className="flex justify-end pt-1">
        <button
          type="submit"
          disabled={!canSave}
          className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-60 inline-flex items-center gap-2"
        >
          {saving ? <Loader2 size={14} className="animate-spin" /> : null}
          {editingId ? 'Update Education' : 'Save Education'}
        </button>
      </div>
    </form>
  );

  return (
    <div className={compact ? 'flex flex-1 min-h-0 flex-col' : 'space-y-4'}>
      <div
        className={
          compact
            ? 'flex-1 min-h-0 overflow-y-auto custom-scrollbar space-y-4 p-4'
            : 'space-y-4'
        }
      >
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

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 items-start">
          {recordsTable}
          {institutionForm}
        </div>
      </div>
    </div>
  );
};

export default CandidateEducationsTab;
