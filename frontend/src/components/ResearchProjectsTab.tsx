import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Info, Loader2, Pencil, Trash2 } from 'lucide-react';
import { apiFetch } from '../utils/api';
import { useConfirmation } from '../context/ConfirmationContext';
import EmptyListMessage from './ui/EmptyListMessage';
import {
  DESCRIPTION_MAX_LENGTH,
  ROLE_MAX_LENGTH,
  TITLE_MAX_LENGTH,
  emptyResearchProjectForm,
  filterProjectTypeOptions,
  formToSavePayload,
  getProjectTypeLabel,
  projectToForm,
  validateResearchProjectForm,
  type ResearchProjectFormState,
  type ResearchProjectRecord,
  type ResearchProjectType,
  type ResearchProjectTypeOption,
  type ResearchProjectsResponse,
} from '../types/researchProject';
import {
  studentInfoFieldErrorClass as fieldErrorClass,
  studentInfoInputClass as inputClass,
  studentInfoLabelClass as labelClass,
} from './studentInfoFormStyles';

interface ResearchProjectsTabProps {
  bookingId: number;
  compact?: boolean;
}

const fieldClass = (hasError: boolean) =>
  `${inputClass}${hasError ? ' border-red-400 ring-1 ring-red-200' : ''}`;

const ResearchProjectsTab: React.FC<ResearchProjectsTabProps> = ({
  bookingId,
  compact = false,
}) => {
  const openConfirm = useConfirmation();
  const [projects, setProjects] = useState<ResearchProjectRecord[]>([]);
  const [typeOptions, setTypeOptions] = useState<ResearchProjectTypeOption[]>([]);
  const [form, setForm] = useState<ResearchProjectFormState>(emptyResearchProjectForm);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [typeSearch, setTypeSearch] = useState('');
  const [showTypeDropdown, setShowTypeDropdown] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [showTooltip, setShowTooltip] = useState(false);

  const typeDropdownRef = useRef<HTMLDivElement>(null);
  const apiPath = `bookings/mine/${bookingId}/research-projects`;

  const filteredTypeOptions = useMemo(
    () => filterProjectTypeOptions(typeSearch, typeOptions),
    [typeOptions, typeSearch]
  );

  const validationErrors = useMemo(() => validateResearchProjectForm(form), [form]);
  const canSave = Object.keys(validationErrors).length === 0 && !saving;

  const loadProjects = useCallback(async () => {
    const response = (await apiFetch(apiPath)) as ResearchProjectsResponse;
    setProjects(response.projects);
    setTypeOptions(response.project_types);
  }, [apiPath]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setSuccess(null);

    loadProjects()
      .catch(err => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Failed to load research projects.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [loadProjects]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        typeDropdownRef.current &&
        !typeDropdownRef.current.contains(event.target as Node)
      ) {
        setShowTypeDropdown(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const resetForm = () => {
    setForm(emptyResearchProjectForm());
    setEditingId(null);
    setTypeSearch('');
    setFieldErrors({});
  };

  const handleCancelForm = () => {
    resetForm();
    setError(null);
  };

  const updateForm = (patch: Partial<ResearchProjectFormState>) => {
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

  const handleSelectType = (value: ResearchProjectType, label: string) => {
    updateForm({ project_type: value });
    setTypeSearch(label);
    setShowTypeDropdown(false);
  };

  const handleEdit = (project: ResearchProjectRecord) => {
    setForm(projectToForm(project));
    setTypeSearch(project.project_type_label);
    setEditingId(project.id);
    setError(null);
    setSuccess(null);
    setFieldErrors({});
  };

  const handleDelete = async (projectId: number) => {
    if (
      !(await openConfirm({
        title: 'Delete research project?',
        message: 'Delete this research project?',
        confirmLabel: 'Delete',
        variant: 'danger',
      }))
    ) {
      return;
    }

    try {
      setDeletingId(projectId);
      setError(null);
      setSuccess(null);
      const response = (await apiFetch(`${apiPath}/${projectId}`, {
        method: 'DELETE',
      })) as ResearchProjectsResponse;
      setProjects(response.projects);
      if (editingId === projectId) {
        resetForm();
      }
      setSuccess('Research project deleted.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete research project.');
    } finally {
      setDeletingId(null);
    }
  };

  const handleSave = async (event: React.FormEvent) => {
    event.preventDefault();
    const errors = validateResearchProjectForm(form);
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      setError('Please fix validation errors before saving.');
      setSuccess(null);
      return;
    }

    try {
      setSaving(true);
      setError(null);
      setSuccess(null);
      setFieldErrors({});
      const payload = formToSavePayload(form);
      const response = (await apiFetch(editingId ? `${apiPath}/${editingId}` : apiPath, {
        method: editingId ? 'PUT' : 'POST',
        body: JSON.stringify(payload),
      })) as ResearchProjectsResponse;
      setProjects(response.projects);
      resetForm();
      setSuccess(editingId ? 'Research project updated.' : 'Research project saved.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save research project.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-text-muted">
        <Loader2 size={22} className="animate-spin mr-2" />
        Loading research projects...
      </div>
    );
  }

  const recordsTable = (
    <div className="rounded-xl border border-border-subtle bg-surface-bg/40 p-4 space-y-3 h-full">
      <div>
        <div className="flex items-center gap-1.5">
          <h4 className="text-sm font-semibold text-text-main">Projects on file</h4>
          <div className="relative">
            <button
              type="button"
              className="text-text-muted hover:text-text-main"
              aria-label="About research projects"
              onMouseEnter={() => setShowTooltip(true)}
              onMouseLeave={() => setShowTooltip(false)}
              onFocus={() => setShowTooltip(true)}
              onBlur={() => setShowTooltip(false)}
            >
              <Info size={13} />
            </button>
            {showTooltip ? (
              <div className="absolute left-0 top-full z-10 mt-1 w-64 rounded-md border border-border-subtle bg-card px-2.5 py-2 text-xs text-text-muted shadow-sm">
                Optional: Share academic projects, publications, and research work to
                strengthen your profile.
              </div>
            ) : null}
          </div>
        </div>
        <p className="text-xs text-text-muted mt-0.5">
          Research projects, papers, and academic work from the candidate profile.
        </p>
      </div>
      {projects.length === 0 ? (
        <EmptyListMessage
          compact
          message="No research projects yet. Use the form on the right to add one."
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border-subtle">
          <table className="min-w-full text-left text-xs">
            <thead className="bg-surface-bg text-text-muted">
              <tr>
                <th className="px-3 py-2 font-semibold">Type</th>
                <th className="px-3 py-2 font-semibold">Title</th>
                <th className="px-3 py-2 font-semibold text-right whitespace-nowrap">Actions</th>
                <th className="px-3 py-2 font-semibold">Role</th>
              </tr>
            </thead>
            <tbody>
              {projects.map(project => (
                <tr
                  key={project.id}
                  className={`border-t border-border-subtle bg-card ${
                    editingId === project.id ? 'ring-1 ring-inset ring-sky-300' : ''
                  }`}
                >
                  <td className="px-3 py-2 text-text-main">
                    {project.project_type_label || '—'}
                  </td>
                  <td className="px-3 py-2 text-text-main">
                    {project.project_title || 'Untitled project'}
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap shrink-0">
                    <div className="flex items-center justify-end gap-1.5">
                      <button
                        type="button"
                        onClick={() => handleEdit(project)}
                        className="inline-flex items-center gap-1 rounded-md border border-sky-200 bg-sky-50 px-2 py-1 text-[11px] font-semibold text-sky-800 hover:bg-sky-100"
                        aria-label={`Edit ${project.project_title || 'research project'}`}
                      >
                        <Pencil size={12} />
                        Edit
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleDelete(project.id)}
                        disabled={deletingId === project.id}
                        className="inline-flex items-center gap-1 rounded-md border border-red-200 bg-red-50 px-2 py-1 text-[11px] font-semibold text-red-700 hover:bg-red-100 disabled:opacity-60"
                        aria-label={`Delete ${project.project_title || 'research project'}`}
                      >
                        {deletingId === project.id ? (
                          <Loader2 size={12} className="animate-spin" />
                        ) : (
                          <Trash2 size={12} />
                        )}
                        Delete
                      </button>
                    </div>
                  </td>
                  <td className="px-3 py-2 text-text-main">{project.role || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );

  const projectForm = (
    <form
      onSubmit={handleSave}
      className="rounded-xl border border-border-subtle bg-card p-4 space-y-3 h-full"
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <h4 className="text-sm font-semibold text-text-main">
            {editingId ? 'Edit project' : 'Add project'}
          </h4>
          <p className="text-xs text-text-muted mt-0.5">
            Capture type, title, description, role, and publication link. All fields are
            optional.
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

      <div ref={typeDropdownRef} className="relative">
        <label htmlFor="research-project-type" className={labelClass}>
          Project Type
        </label>
        <input
          id="research-project-type"
          type="text"
          className={fieldClass(Boolean(fieldErrors.project_type))}
          value={typeSearch || getProjectTypeLabel(form.project_type, typeOptions)}
          onChange={e => {
            setTypeSearch(e.target.value);
            setShowTypeDropdown(true);
            if (!e.target.value.trim()) {
              updateForm({ project_type: '' });
            }
          }}
          onFocus={() => setShowTypeDropdown(true)}
          placeholder="Search project type..."
          autoComplete="off"
        />
        {showTypeDropdown ? (
          <div className="absolute z-20 mt-1 max-h-48 w-full overflow-y-auto rounded-md border border-border-subtle bg-card shadow-sm">
            {filteredTypeOptions.length === 0 ? (
              <p className="px-2.5 py-2 text-sm text-text-muted">No matches found.</p>
            ) : (
              filteredTypeOptions.map(option => (
                <button
                  key={option.value}
                  type="button"
                  className="block w-full px-2.5 py-2 text-left text-sm text-text-main hover:bg-surface-bg"
                  onClick={() => handleSelectType(option.value, option.label)}
                >
                  {option.label}
                </button>
              ))
            )}
          </div>
        ) : null}
        {fieldErrors.project_type ? (
          <p className={fieldErrorClass}>{fieldErrors.project_type}</p>
        ) : null}
      </div>

      <div>
        <label htmlFor="research-project-title" className={labelClass}>
          Project Title
        </label>
        <input
          id="research-project-title"
          className={fieldClass(Boolean(fieldErrors.project_title))}
          value={form.project_title}
          maxLength={TITLE_MAX_LENGTH}
          onChange={e => updateForm({ project_title: e.target.value })}
          placeholder="e.g. Urban heat island mitigation study"
        />
        {fieldErrors.project_title ? (
          <p className={fieldErrorClass}>{fieldErrors.project_title}</p>
        ) : null}
      </div>

      <div>
        <label htmlFor="research-project-description" className={labelClass}>
          Description
        </label>
        <textarea
          id="research-project-description"
          className={`${fieldClass(Boolean(fieldErrors.project_description))} min-h-[96px] resize-y`}
          value={form.project_description}
          maxLength={DESCRIPTION_MAX_LENGTH}
          onChange={e => updateForm({ project_description: e.target.value })}
          placeholder="Brief summary of your research focus and outcomes (optional)"
        />
        <p className="mt-1 text-xs text-text-muted text-right">
          {form.project_description.length}/{DESCRIPTION_MAX_LENGTH}
        </p>
        {fieldErrors.project_description ? (
          <p className={fieldErrorClass}>{fieldErrors.project_description}</p>
        ) : null}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <div>
          <label htmlFor="research-project-role" className={labelClass}>
            Role
          </label>
          <input
            id="research-project-role"
            className={fieldClass(Boolean(fieldErrors.role))}
            value={form.role}
            maxLength={ROLE_MAX_LENGTH}
            onChange={e => updateForm({ role: e.target.value })}
            placeholder="e.g. Lead Researcher, Author"
          />
          {fieldErrors.role ? <p className={fieldErrorClass}>{fieldErrors.role}</p> : null}
        </div>
        <div>
          <label htmlFor="research-project-url" className={labelClass}>
            Publication URL
          </label>
          <input
            id="research-project-url"
            type="url"
            className={inputClass}
            value={form.publication_url}
            onChange={e => updateForm({ publication_url: e.target.value })}
            placeholder="https://..."
          />
        </div>
      </div>

      <div className="flex justify-end pt-1">
        <button
          type="submit"
          disabled={!canSave}
          className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-60 inline-flex items-center gap-2"
        >
          {saving ? <Loader2 size={14} className="animate-spin" /> : null}
          {editingId ? 'Update Project' : 'Save Project'}
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
          {projectForm}
        </div>
      </div>
    </div>
  );
};

export default ResearchProjectsTab;
