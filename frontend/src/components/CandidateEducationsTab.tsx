import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Loader2, Pencil, Plus, Trash2 } from 'lucide-react';
import { apiFetch } from '../utils/api';
import { useConfirmation } from '../context/ConfirmationContext';
import EmptyListMessage from './ui/EmptyListMessage';
import { findEducationDegree, useEducationDegrees } from '../hooks/useEducationDegrees';
import { useLevels } from '../hooks/useLevels';
import { levelSelectOptions } from '../constants/levels';
import { useEducationMajors } from '../hooks/useEducationMajors';
import { findGpaCgpaScore, useGpaCgpaScores } from '../hooks/useGpaCgpaScores';
import {
  GRADUATION_MONTH_OPTIONS,
  emptyCandidateEducationForm,
  educationToForm,
  formToEducationPayload,
  formatGraduationPeriod,
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
  studentInfoSectionClass as sectionClass,
} from './studentInfoFormStyles';

interface CandidateEducationsTabProps {
  bookingId: number;
  compact?: boolean;
}

const fieldClass = (hasError: boolean) =>
  `${inputClass}${hasError ? ' border-red-400 ring-1 ring-red-200' : ''}`;

const cardClass = 'rounded-md border border-border-subtle bg-surface-bg/40 p-3 space-y-2';

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
  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [levelId, setLevelId] = useState('');

  const { levels } = useLevels();
  const { degrees: allDegrees } = useEducationDegrees();
  const filteredDegrees = useMemo(() => {
    if (!levelId) return allDegrees;
    return allDegrees.filter(degree => degree.level_id === Number(levelId));
  }, [allDegrees, levelId]);
  const { majors } = useEducationMajors();
  const { scores: gpaCgpaScores } = useGpaCgpaScores();
  const selectedDegree = useMemo(
    () => findEducationDegree(allDegrees, form.degree_code),
    [allDegrees, form.degree_code]
  );
  const selectedGpa = useMemo(
    () => findGpaCgpaScore(gpaCgpaScores, form.gpa_cgpa_code),
    [gpaCgpaScores, form.gpa_cgpa_code]
  );

  const apiPath = `bookings/mine/${bookingId}/educations`;
  const validationErrors = useMemo(
    () =>
      validateCandidateEducationForm(form, {
        degreeIsOther: selectedDegree?.is_other,
        gpaIsOther: selectedGpa?.is_other,
      }),
    [form, selectedDegree?.is_other, selectedGpa?.is_other]
  );
  const canSave = Object.keys(validationErrors).length === 0 && !saving;

  const sortedEducations = useMemo(
    () => sortEducationsByDegreeOrder(educations, allDegrees),
    [educations, allDegrees]
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

  const handleAddEducation = () => {
    resetForm();
    setShowForm(true);
    setSuccess(null);
    setError(null);
  };

  const handleCancelForm = () => {
    resetForm();
    setShowForm(false);
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
    const degree = findEducationDegree(allDegrees, nextForm.degree_code);
    setLevelId(degree ? String(degree.level_id) : '');
    setEditingId(education.id);
    setShowForm(true);
    setError(null);
    setSuccess(null);
    setFieldErrors({});
  };

  const handleDelete = async (educationId: number) => {
    if (!(await openConfirm({
      title: 'Delete education record?',
      message: 'Delete this education record?',
      confirmLabel: 'Delete',
      variant: 'danger',
    }))) {
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
        setShowForm(false);
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
      degreeIsOther: selectedDegree?.is_other,
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
      setShowForm(false);
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

  return (
    <div className={compact ? 'flex flex-1 min-h-0 flex-col' : 'space-y-4'}>
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
          <div className="flex items-start justify-between gap-2">
            <div>
              <h3 className="text-sm font-bold text-text-main uppercase tracking-wide">Education</h3>
              <p className="text-sm text-text-muted mt-1">
                Add each degree or program as a separate education record.
              </p>
            </div>
            {!showForm ? (
              <button
                type="button"
                onClick={handleAddEducation}
                className="inline-flex items-center gap-1 rounded-md border border-sky-200 bg-sky-50 px-2.5 py-1.5 text-sm font-semibold text-sky-800 hover:bg-sky-100"
              >
                <Plus size={12} />
                Add Education
              </button>
            ) : null}
          </div>

          {showForm ? (
            <form
              onSubmit={handleSave}
              className="rounded-md border border-border-subtle bg-surface-bg/30 p-3 space-y-3"
            >
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm font-bold text-text-main">
                  {editingId ? 'Edit Education' : 'New Education'}
                </p>
                <button
                  type="button"
                  onClick={handleCancelForm}
                  className="text-sm text-text-muted hover:text-text-main"
                >
                  Cancel
                </button>
              </div>

              <div className="grid grid-cols-2 xl:grid-cols-3 gap-2">
                <div>
                  <RequiredLabel htmlFor="education-course-level">Course Level</RequiredLabel>
                  <select
                    id="education-course-level"
                    className={fieldClass(false)}
                    value={levelId}
                    onChange={e => {
                      const nextLevelId = e.target.value;
                      setLevelId(nextLevelId);
                      if (form.degree_code) {
                        const degree = findEducationDegree(allDegrees, form.degree_code);
                        if (
                          degree &&
                          nextLevelId &&
                          degree.level_id !== Number(nextLevelId)
                        ) {
                          updateForm({ degree_code: '', degree_other: '' });
                        }
                      }
                    }}
                  >
                    <option value="">Select course level</option>
                    {levelSelectOptions(levels).map(option => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <RequiredLabel htmlFor="education-degree">Current Degree</RequiredLabel>
                  <select
                    id="education-degree"
                    className={fieldClass(Boolean(fieldErrors.degree_code))}
                    value={form.degree_code}
                    disabled={!levelId}
                    onChange={e => {
                      const nextCode = e.target.value;
                      const nextDegree = findEducationDegree(allDegrees, nextCode);
                      updateForm({
                        degree_code: nextCode,
                        degree_other: nextDegree?.is_other ? form.degree_other : '',
                      });
                    }}
                  >
                    <option value="">
                      {levelId ? 'Select degree' : 'Select course level first'}
                    </option>
                    {filteredDegrees.map(degree => (
                      <option key={degree.code} value={degree.code}>
                        {degree.label}
                      </option>
                    ))}
                  </select>
                  {fieldErrors.degree_code ? (
                    <p className={fieldErrorClass}>{fieldErrors.degree_code}</p>
                  ) : null}
                  {selectedDegree?.is_other ? (
                    <input
                      className={`${fieldClass(Boolean(fieldErrors.degree_other))} mt-1`}
                      value={form.degree_other}
                      onChange={e => updateForm({ degree_other: e.target.value })}
                      placeholder="Enter degree"
                    />
                  ) : null}
                  {fieldErrors.degree_other ? (
                    <p className={fieldErrorClass}>{fieldErrors.degree_other}</p>
                  ) : null}
                </div>

                <div>
                  <RequiredLabel htmlFor="education-major">Current Major</RequiredLabel>
                  <select
                    id="education-major"
                    className={fieldClass(Boolean(fieldErrors.major))}
                    value={
                      majors.some(
                        major => !major.is_other && major.label === form.major
                      )
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
                    <option value="">Select major</option>
                    {majors.map(major => (
                      <option
                        key={major.code}
                        value={major.is_other ? 'Other' : major.label}
                      >
                        {major.label}
                      </option>
                    ))}
                  </select>
                  {(form.major === 'Other' ||
                    (!majors.some(major => !major.is_other && major.label === form.major) &&
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

                <div>
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

                <div>
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

                <div>
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

              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={!canSave}
                  className="rounded-md bg-sky-700 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-800 disabled:opacity-60 inline-flex items-center gap-2"
                >
                  {saving ? <Loader2 size={14} className="animate-spin" /> : null}
                  {editingId ? 'Update Education' : 'Save Education'}
                </button>
              </div>
            </form>
          ) : null}

          {educations.length === 0 ? (
            <EmptyListMessage
              compact
              message='No education records yet. Click "Add Education" to get started.'
            />
          ) : (
            <div className="space-y-3">
              {sortedEducations.map(education => (
                <div key={education.id} className={cardClass}>
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-sm font-bold text-text-main">
                        {education.degree_label || education.degree_code || 'Degree'}
                        {education.major ? ` · ${education.major}` : ''}
                      </p>
                      <p className="text-sm text-text-main mt-0.5">
                        {education.university_name || 'University not specified'}
                      </p>
                      {education.university_affiliation ? (
                        <p className="text-sm text-text-muted">
                          Affiliation: {education.university_affiliation}
                        </p>
                      ) : null}
                      <p className="text-sm text-text-muted mt-1">
                        Graduated:{' '}
                        {formatGraduationPeriod(
                          education.graduation_month,
                          education.graduation_year
                        ) || '—'}
                        {education.gpa_cgpa_label ? ` · GPA/CGPA: ${education.gpa_cgpa_label}` : ''}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        type="button"
                        onClick={() => handleEdit(education)}
                        className="inline-flex items-center gap-1 text-sm text-sky-700 hover:text-sky-900"
                      >
                        <Pencil size={12} />
                        Edit
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDelete(education.id)}
                        disabled={deletingId === education.id}
                        className="inline-flex items-center gap-1 text-sm text-red-600 hover:text-red-700 disabled:opacity-60"
                      >
                        {deletingId === education.id ? (
                          <Loader2 size={12} className="animate-spin" />
                        ) : (
                          <Trash2 size={12} />
                        )}
                        Delete
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {!showForm && educations.length > 0 ? (
            <div className="flex justify-center pt-1">
              <button
                type="button"
                onClick={handleAddEducation}
                className="inline-flex items-center gap-1 rounded-md border border-border-subtle px-3 py-1.5 text-sm font-semibold text-text-main hover:bg-card"
              >
                <Plus size={12} />
                Add Another Education
              </button>
            </div>
          ) : null}
        </section>
      </div>
    </div>
  );
};

export default CandidateEducationsTab;
