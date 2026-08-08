import React, { useCallback, useEffect, useMemo, useState } from 'react';
import DatePicker from 'react-datepicker';
import 'react-datepicker/dist/react-datepicker.css';
import { Loader2, Pencil, Plus, Trash2 } from 'lucide-react';
import { apiFetch } from '../utils/api';
import { useConfirmation } from '../context/ConfirmationContext';
import { formatLocalIsoDate, parseLocalIsoDate } from '../types/candidateProfile';
import EmptyListMessage from './ui/EmptyListMessage';
import { nexusDatePickerPortalProps } from '../utils/nexusDatePickerPortal';
import {
  createEmptyExperience,
  createEmptyProject,
  experiencesToForm,
  experiencesToSavePayload,
  validateWorkExperiences,
  type WorkExperienceFormEntry,
  type WorkExperiencesResponse,
  type WorkProjectFormEntry,
} from '../types/workExperience';
import {
  studentInfoFieldErrorClass as fieldErrorClass,
  studentInfoInputClass as inputClass,
  studentInfoLabelClass as labelClass,
} from './studentInfoFormStyles';

interface WorkProjectsTabProps {
  bookingId: number;
  compact?: boolean;
}

const fieldClass = (hasError: boolean) =>
  `${inputClass}${hasError ? ' border-red-400 ring-1 ring-red-200' : ''}`;

const formatExperienceDates = (experience: WorkExperienceFormEntry): string => {
  const start = experience.start_date
    ? parseLocalIsoDate(experience.start_date)?.toLocaleDateString(undefined, {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
      })
    : null;
  if (experience.is_current) {
    return start ? `${start} – Present` : 'Present';
  }
  const end = experience.end_date
    ? parseLocalIsoDate(experience.end_date)?.toLocaleDateString(undefined, {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
      })
    : null;
  if (start && end) return `${start} – ${end}`;
  if (start) return start;
  if (end) return end;
  return '—';
};

const WorkProjectsTab: React.FC<WorkProjectsTabProps> = ({ bookingId, compact = false }) => {
  const openConfirm = useConfirmation();
  const [experiences, setExperiences] = useState<WorkExperienceFormEntry[]>([]);
  const [form, setForm] = useState<WorkExperienceFormEntry>(() => createEmptyExperience());
  const [editingClientId, setEditingClientId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deletingClientId, setDeletingClientId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const apiPath = `bookings/mine/${bookingId}/work-experiences`;
  const validationErrors = useMemo(() => validateWorkExperiences([form]), [form]);
  const canSave = Object.keys(validationErrors).length === 0 && !saving;

  const loadExperiences = useCallback(async () => {
    const response = (await apiFetch(apiPath)) as WorkExperiencesResponse;
    setExperiences(experiencesToForm(response.experiences));
  }, [apiPath]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setSuccess(null);

    loadExperiences()
      .catch(err => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Failed to load work experience.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [loadExperiences]);

  const resetForm = () => {
    setForm(createEmptyExperience());
    setEditingClientId(null);
    setFieldErrors({});
  };

  const handleCancelForm = () => {
    resetForm();
    setError(null);
  };

  const updateForm = (patch: Partial<WorkExperienceFormEntry>) => {
    setForm(prev => ({ ...prev, ...patch }));
    setSuccess(null);
    if (patch.end_date !== undefined || patch.start_date !== undefined || patch.is_current !== undefined) {
      setFieldErrors(prev => {
        const next = { ...prev };
        delete next[`${form.clientId}-end_date`];
        return next;
      });
    }
  };

  const handleEdit = (experience: WorkExperienceFormEntry) => {
    setForm({
      ...experience,
      projects: experience.projects.map(project => ({ ...project })),
    });
    setEditingClientId(experience.clientId);
    setError(null);
    setSuccess(null);
    setFieldErrors({});
  };

  const handleAddProject = () => {
    setForm(prev => ({
      ...prev,
      projects: [...prev.projects, createEmptyProject()],
    }));
    setSuccess(null);
  };

  const handleRemoveProject = (projectClientId: string) => {
    setForm(prev => ({
      ...prev,
      projects: prev.projects.filter(project => project.clientId !== projectClientId),
    }));
    setSuccess(null);
  };

  const handleProjectChange = (
    projectClientId: string,
    patch: Partial<Pick<WorkProjectFormEntry, 'project_name' | 'project_description'>>
  ) => {
    setForm(prev => ({
      ...prev,
      projects: prev.projects.map(project =>
        project.clientId === projectClientId ? { ...project, ...patch } : project
      ),
    }));
    setSuccess(null);
  };

  const putExperiences = async (nextList: WorkExperienceFormEntry[]) => {
    const response = (await apiFetch(apiPath, {
      method: 'PUT',
      body: JSON.stringify(experiencesToSavePayload(nextList)),
    })) as WorkExperiencesResponse;
    const next = experiencesToForm(response.experiences);
    setExperiences(next);
    return next;
  };

  const handleDelete = async (clientId: string) => {
    const target = experiences.find(experience => experience.clientId === clientId);
    if (
      !(await openConfirm({
        title: 'Delete work experience?',
        message: `Delete${target?.company_name ? ` “${target.company_name}”` : ' this work experience'}?`,
        confirmLabel: 'Delete',
        variant: 'danger',
      }))
    ) {
      return;
    }

    try {
      setDeletingClientId(clientId);
      setError(null);
      setSuccess(null);
      const nextList = experiences.filter(experience => experience.clientId !== clientId);
      await putExperiences(nextList);
      if (editingClientId === clientId) {
        resetForm();
      }
      setSuccess('Work experience deleted.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete work experience.');
    } finally {
      setDeletingClientId(null);
    }
  };

  const handleSave = async (event: React.FormEvent) => {
    event.preventDefault();
    const errors = validateWorkExperiences([form]);
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      setError('Please fix date errors before saving.');
      setSuccess(null);
      return;
    }

    try {
      setSaving(true);
      setError(null);
      setSuccess(null);
      setFieldErrors({});
      const entryToSave: WorkExperienceFormEntry = { ...form, showForm: true };
      const nextList = editingClientId
        ? experiences.map(experience =>
            experience.clientId === editingClientId ? entryToSave : experience
          )
        : [...experiences, entryToSave];
      await putExperiences(nextList);
      resetForm();
      setSuccess(editingClientId ? 'Work experience updated.' : 'Work experience added.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save work experience.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-text-muted">
        <Loader2 size={22} className="animate-spin mr-2" />
        Loading work experience...
      </div>
    );
  }

  const startDate = parseLocalIsoDate(form.start_date);
  const endDate = parseLocalIsoDate(form.end_date);
  const endDateError =
    fieldErrors[`${form.clientId}-end_date`] || validationErrors[`${form.clientId}-end_date`];

  const recordsTable = (
    <div className="rounded-xl border border-border-subtle bg-surface-bg/40 p-4 space-y-3 h-full">
      <div>
        <h4 className="text-sm font-semibold text-text-main">Work experience on file</h4>
        <p className="text-xs text-text-muted mt-0.5">
          Roles and projects from the candidate profile.
        </p>
      </div>
      {experiences.length === 0 ? (
        <EmptyListMessage
          compact
          message="No work experience yet. Use the form on the right to add one."
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border-subtle">
          <table className="min-w-full text-left text-xs">
            <thead className="bg-surface-bg text-text-muted">
              <tr>
                <th className="px-3 py-2 font-semibold">Company</th>
                <th className="px-3 py-2 font-semibold">Job Title</th>
                <th className="px-3 py-2 font-semibold">Dates</th>
                <th className="px-3 py-2 font-semibold">Projects count</th>
                <th className="px-3 py-2 font-semibold text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {experiences.map(experience => (
                <tr
                  key={experience.clientId}
                  className={`border-t border-border-subtle bg-card ${
                    editingClientId === experience.clientId ? 'ring-1 ring-inset ring-sky-300' : ''
                  }`}
                >
                  <td className="px-3 py-2 text-text-main">
                    {experience.company_name || '—'}
                  </td>
                  <td className="px-3 py-2 text-text-main">{experience.job_title || '—'}</td>
                  <td className="px-3 py-2 text-text-main">
                    {formatExperienceDates(experience)}
                  </td>
                  <td className="px-3 py-2 text-text-main">{experience.projects.length}</td>
                  <td className="px-3 py-2">
                    <div className="flex items-center justify-end gap-1.5">
                      <button
                        type="button"
                        onClick={() => handleEdit(experience)}
                        className="inline-flex items-center gap-1 rounded-md border border-sky-200 bg-sky-50 px-2 py-1 text-[11px] font-semibold text-sky-800 hover:bg-sky-100"
                        aria-label={`Edit ${experience.company_name || 'work experience'}`}
                      >
                        <Pencil size={12} />
                        Edit
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleDelete(experience.clientId)}
                        disabled={deletingClientId === experience.clientId}
                        className="inline-flex items-center gap-1 rounded-md border border-red-200 bg-red-50 px-2 py-1 text-[11px] font-semibold text-red-700 hover:bg-red-100 disabled:opacity-60"
                        aria-label={`Delete ${experience.company_name || 'work experience'}`}
                      >
                        {deletingClientId === experience.clientId ? (
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

  const experienceForm = (
    <form
      onSubmit={handleSave}
      className="rounded-xl border border-border-subtle bg-card p-4 space-y-3 h-full"
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <h4 className="text-sm font-semibold text-text-main">
            {editingClientId ? 'Edit work experience' : 'Add work experience'}
          </h4>
          <p className="text-xs text-text-muted mt-0.5">
            Capture company, role, dates, and projects for this position.
          </p>
        </div>
        {editingClientId ? (
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
          <label className={labelClass}>Company Name</label>
          <input
            className={inputClass}
            value={form.company_name}
            onChange={e => updateForm({ company_name: e.target.value })}
            placeholder="e.g. Acme Corp"
          />
        </div>
        <div>
          <label className={labelClass}>Job Title</label>
          <input
            className={inputClass}
            value={form.job_title}
            onChange={e => updateForm({ job_title: e.target.value })}
            placeholder="e.g. Software Intern"
          />
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <div>
          <label className={labelClass}>Start Date</label>
          <DatePicker
            selected={startDate}
            onChange={(date: Date | null) =>
              updateForm({ start_date: formatLocalIsoDate(date) })
            }
            dateFormat="dd MMM yyyy"
            placeholderText="Select start date"
            className={inputClass}
            wrapperClassName="w-full"
            isClearable
            {...nexusDatePickerPortalProps}
          />
        </div>
        <div>
          <label className={labelClass}>End Date</label>
          <DatePicker
            selected={endDate}
            onChange={(date: Date | null) => updateForm({ end_date: formatLocalIsoDate(date) })}
            dateFormat="dd MMM yyyy"
            placeholderText="Select end date"
            className={fieldClass(Boolean(endDateError))}
            wrapperClassName="w-full"
            isClearable
            disabled={form.is_current}
            {...nexusDatePickerPortalProps}
          />
          {endDateError ? <p className={fieldErrorClass}>{endDateError}</p> : null}
        </div>
      </div>

      <label className="inline-flex items-center gap-2 text-sm text-text-main cursor-pointer">
        <input
          type="checkbox"
          checked={form.is_current}
          onChange={e =>
            updateForm({
              is_current: e.target.checked,
              end_date: e.target.checked ? '' : form.end_date,
            })
          }
        />
        I am currently working here
      </label>

      <div>
        <label className={labelClass}>Description</label>
        <textarea
          className={`${inputClass} min-h-[72px] resize-y`}
          value={form.description}
          onChange={e => updateForm({ description: e.target.value })}
          placeholder="Brief overview of your responsibilities (optional)"
        />
      </div>

      <div className="space-y-2 border-t border-border-subtle pt-3">
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm font-semibold text-text-main">Projects at this role</p>
          <button
            type="button"
            onClick={handleAddProject}
            className="inline-flex items-center gap-1 rounded-md border border-border-subtle px-2 py-1 text-xs font-semibold text-text-main hover:bg-surface-bg"
          >
            <Plus size={11} />
            Add Project
          </button>
        </div>

        {form.projects.length === 0 ? (
          <EmptyListMessage compact message="No projects added for this role." />
        ) : null}

        {form.projects.map((project, projectIndex) => (
          <div
            key={project.clientId}
            className="rounded-md border border-border-subtle bg-surface-bg/40 p-2.5 space-y-2"
          >
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-semibold text-text-main">Project {projectIndex + 1}</p>
              <button
                type="button"
                onClick={() => handleRemoveProject(project.clientId)}
                className="inline-flex items-center gap-1 text-sm text-red-600 hover:text-red-700"
              >
                <Trash2 size={11} />
                Remove
              </button>
            </div>
            <div>
              <label className={labelClass}>Project Name</label>
              <input
                className={inputClass}
                value={project.project_name}
                onChange={e =>
                  handleProjectChange(project.clientId, { project_name: e.target.value })
                }
                placeholder="e.g. Customer portal redesign"
              />
            </div>
            <div>
              <label className={labelClass}>Project Description</label>
              <textarea
                className={`${inputClass} min-h-[60px] resize-y`}
                value={project.project_description}
                onChange={e =>
                  handleProjectChange(project.clientId, {
                    project_description: e.target.value,
                  })
                }
                placeholder="What you built or contributed (optional)"
              />
            </div>
          </div>
        ))}
      </div>

      <div className="flex justify-end pt-1">
        <button
          type="submit"
          disabled={!canSave}
          className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-60 inline-flex items-center gap-2"
        >
          {saving ? <Loader2 size={14} className="animate-spin" /> : null}
          {editingClientId ? 'Update Experience' : 'Save Experience'}
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
          {experienceForm}
        </div>
      </div>
    </div>
  );
};

export default WorkProjectsTab;
