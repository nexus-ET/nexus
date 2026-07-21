import React, { useCallback, useEffect, useMemo, useState } from 'react';
import DatePicker from 'react-datepicker';
import 'react-datepicker/dist/react-datepicker.css';
import { Info, Loader2, Plus, Trash2 } from 'lucide-react';
import { apiFetch } from '../utils/api';
import { formatLocalIsoDate, parseLocalIsoDate } from '../types/candidateProfile';
import EmptyListMessage from './ui/EmptyListMessage';
import {
  createEmptyExperience,
  createEmptyProject,
  experiencesToForm,
  experiencesToSavePayload,
  validateWorkExperiences,
  type WorkExperienceFormEntry,
  type WorkExperiencesResponse,
} from '../types/workExperience';

interface WorkProjectsTabProps {
  bookingId: number;
  compact?: boolean;
}

const inputClass =
  'w-full rounded-md border border-border-subtle bg-card px-2.5 py-1.5 text-xs text-text-main focus:outline-none focus:ring-1 focus:ring-sky-400/40 min-h-[32px]';

const labelClass = 'block text-[11px] font-bold text-text-main mb-1';

const sectionClass = 'rounded-lg border border-border-subtle bg-card/80 p-3 space-y-3';

const fieldErrorClass = 'mt-1 text-[10px] text-red-600';

const fieldClass = (hasError: boolean) =>
  `${inputClass}${hasError ? ' border-red-400 ring-1 ring-red-200' : ''}`;

const cardClass = 'rounded-md border border-border-subtle bg-surface-bg/40 p-3 space-y-3';

const WorkProjectsTab: React.FC<WorkProjectsTabProps> = ({ bookingId, compact = false }) => {
  const [experiences, setExperiences] = useState<WorkExperienceFormEntry[]>([]);
  const [baseline, setBaseline] = useState<WorkExperienceFormEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [showTooltip, setShowTooltip] = useState(false);

  const apiPath = `bookings/mine/${bookingId}/work-experiences`;
  const validationErrors = useMemo(() => validateWorkExperiences(experiences), [experiences]);
  const canSave = Object.keys(validationErrors).length === 0 && !saving;

  const loadExperiences = useCallback(async () => {
    const response = (await apiFetch(apiPath)) as WorkExperiencesResponse;
    const next = experiencesToForm(response.experiences);
    setExperiences(next);
    setBaseline(next);
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

  const updateExperience = (
    clientId: string,
    patch: Partial<WorkExperienceFormEntry>
  ) => {
    setExperiences(prev =>
      prev.map(experience =>
        experience.clientId === clientId ? { ...experience, ...patch } : experience
      )
    );
    setSuccess(null);
    if (patch.end_date !== undefined || patch.start_date !== undefined || patch.is_current !== undefined) {
      setFieldErrors(prev => {
        const next = { ...prev };
        delete next[`${clientId}-end_date`];
        return next;
      });
    }
  };

  const handleAddExperience = () => {
    setExperiences(prev => [...prev, createEmptyExperience(true)]);
    setSuccess(null);
  };

  const handleRemoveExperience = (clientId: string) => {
    setExperiences(prev => prev.filter(experience => experience.clientId !== clientId));
    setSuccess(null);
  };

  const handleAddProject = (experienceClientId: string) => {
    setExperiences(prev =>
      prev.map(experience =>
        experience.clientId === experienceClientId
          ? { ...experience, projects: [...experience.projects, createEmptyProject()] }
          : experience
      )
    );
    setSuccess(null);
  };

  const handleRemoveProject = (experienceClientId: string, projectClientId: string) => {
    setExperiences(prev =>
      prev.map(experience =>
        experience.clientId === experienceClientId
          ? {
              ...experience,
              projects: experience.projects.filter(project => project.clientId !== projectClientId),
            }
          : experience
      )
    );
    setSuccess(null);
  };

  const handleProjectChange = (
    experienceClientId: string,
    projectClientId: string,
    patch: { project_name?: string; project_description?: string }
  ) => {
    setExperiences(prev =>
      prev.map(experience =>
        experience.clientId === experienceClientId
          ? {
              ...experience,
              projects: experience.projects.map(project =>
                project.clientId === projectClientId ? { ...project, ...patch } : project
              ),
            }
          : experience
      )
    );
    setSuccess(null);
  };

  const handleSave = async (event: React.FormEvent) => {
    event.preventDefault();
    const errors = validateWorkExperiences(experiences);
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
      const response = (await apiFetch(apiPath, {
        method: 'PUT',
        body: JSON.stringify(experiencesToSavePayload(experiences)),
      })) as WorkExperiencesResponse;
      const next = experiencesToForm(response.experiences);
      setExperiences(next);
      setBaseline(next);
      setSuccess('Work experience saved. You can return and update this anytime.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save work experience.');
    } finally {
      setSaving(false);
    }
  };

  const handleSkip = () => {
    setExperiences(baseline);
    setError(null);
    setSuccess(null);
    setFieldErrors({});
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-text-muted">
        <Loader2 size={22} className="animate-spin mr-2" />
        Loading work experience...
      </div>
    );
  }

  const visibleExperiences = experiences.filter(experience => experience.showForm);

  return (
    <form onSubmit={handleSave} className={compact ? 'flex flex-1 min-h-0 flex-col' : 'space-y-4'}>
      <div className={compact ? 'flex-1 min-h-0 overflow-y-auto custom-scrollbar space-y-4' : 'space-y-4'}>
        {error ? (
          <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
            {error}
          </div>
        ) : null}
        {success ? (
          <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800">
            {success}
          </div>
        ) : null}

        <section className={sectionClass}>
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-1.5">
              <h3 className="text-xs font-bold text-text-main uppercase tracking-wide">
                Work Experience (Optional)
              </h3>
              <div className="relative">
                <button
                  type="button"
                  className="text-text-muted hover:text-text-main"
                  aria-label="About work experience"
                  onMouseEnter={() => setShowTooltip(true)}
                  onMouseLeave={() => setShowTooltip(false)}
                  onFocus={() => setShowTooltip(true)}
                  onBlur={() => setShowTooltip(false)}
                >
                  <Info size={13} />
                </button>
                {showTooltip ? (
                  <div className="absolute left-0 top-full z-10 mt-1 w-64 rounded-md border border-border-subtle bg-card px-2.5 py-2 text-[10px] text-text-muted shadow-sm">
                    Optional: Adding your work experience and projects helps us provide better
                    career guidance.
                  </div>
                ) : null}
              </div>
            </div>
            <button
              type="button"
              onClick={handleAddExperience}
              className="inline-flex items-center gap-1 rounded-md border border-sky-200 bg-sky-50 px-2.5 py-1.5 text-[11px] font-semibold text-sky-800 hover:bg-sky-100"
            >
              <Plus size={12} />
              Add Work Experience
            </button>
          </div>

          <p className="text-xs text-text-muted">
            Add one or more roles if you have work history. Leave this section empty if it does not
            apply to you.
          </p>

          {visibleExperiences.length === 0 ? (
            <EmptyListMessage
              compact
              message='No work experience added yet. Click "Add Work Experience" when you are ready.'
            />
          ) : null}

          <div className="space-y-3">
            {visibleExperiences.map((experience, index) => {
              const startDate = parseLocalIsoDate(experience.start_date);
              const endDate = parseLocalIsoDate(experience.end_date);
              const endDateError =
                fieldErrors[`${experience.clientId}-end_date`] ||
                validationErrors[`${experience.clientId}-end_date`];

              return (
                <div key={experience.clientId} className={cardClass}>
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs font-bold text-text-main">
                      Work Experience {index + 1}
                    </p>
                    <button
                      type="button"
                      onClick={() => handleRemoveExperience(experience.clientId)}
                      className="inline-flex items-center gap-1 text-[11px] text-red-600 hover:text-red-700"
                    >
                      <Trash2 size={12} />
                      Remove
                    </button>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    <div>
                      <label className={labelClass}>Company Name</label>
                      <input
                        className={inputClass}
                        value={experience.company_name}
                        onChange={e =>
                          updateExperience(experience.clientId, { company_name: e.target.value })
                        }
                        placeholder="e.g. Acme Corp"
                      />
                    </div>
                    <div>
                      <label className={labelClass}>Job Title</label>
                      <input
                        className={inputClass}
                        value={experience.job_title}
                        onChange={e =>
                          updateExperience(experience.clientId, { job_title: e.target.value })
                        }
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
                          updateExperience(experience.clientId, {
                            start_date: formatLocalIsoDate(date),
                          })
                        }
                        dateFormat="dd MMM yyyy"
                        placeholderText="Select start date"
                        className={inputClass}
                        wrapperClassName="w-full"
                        isClearable
                      />
                    </div>
                    <div>
                      <label className={labelClass}>End Date</label>
                      <DatePicker
                        selected={endDate}
                        onChange={(date: Date | null) =>
                          updateExperience(experience.clientId, {
                            end_date: formatLocalIsoDate(date),
                          })
                        }
                        dateFormat="dd MMM yyyy"
                        placeholderText="Select end date"
                        className={fieldClass(Boolean(endDateError))}
                        wrapperClassName="w-full"
                        isClearable
                        disabled={experience.is_current}
                      />
                      {endDateError ? <p className={fieldErrorClass}>{endDateError}</p> : null}
                    </div>
                  </div>

                  <label className="inline-flex items-center gap-2 text-xs text-text-main cursor-pointer">
                    <input
                      type="checkbox"
                      checked={experience.is_current}
                      onChange={e =>
                        updateExperience(experience.clientId, {
                          is_current: e.target.checked,
                          end_date: e.target.checked ? '' : experience.end_date,
                        })
                      }
                    />
                    I am currently working here
                  </label>

                  <div>
                    <label className={labelClass}>Description</label>
                    <textarea
                      className={`${inputClass} min-h-[72px] resize-y`}
                      value={experience.description}
                      onChange={e =>
                        updateExperience(experience.clientId, { description: e.target.value })
                      }
                      placeholder="Brief overview of your responsibilities (optional)"
                    />
                  </div>

                  <div className="space-y-2 border-t border-border-subtle pt-3">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-[11px] font-bold text-text-main">Projects at this role</p>
                      <button
                        type="button"
                        onClick={() => handleAddProject(experience.clientId)}
                        className="inline-flex items-center gap-1 rounded-md border border-border-subtle px-2 py-1 text-[10px] font-semibold text-text-main hover:bg-card"
                      >
                        <Plus size={11} />
                        Add Project
                      </button>
                    </div>

                    {experience.projects.length === 0 ? (
                      <EmptyListMessage compact message="No projects added for this role." />
                    ) : null}

                    {experience.projects.map((project, projectIndex) => (
                      <div
                        key={project.clientId}
                        className="rounded-md border border-border-subtle bg-card/70 p-2.5 space-y-2"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <p className="text-[10px] font-bold text-text-main">
                            Project {projectIndex + 1}
                          </p>
                          <button
                            type="button"
                            onClick={() =>
                              handleRemoveProject(experience.clientId, project.clientId)
                            }
                            className="inline-flex items-center gap-1 text-[10px] text-red-600 hover:text-red-700"
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
                              handleProjectChange(experience.clientId, project.clientId, {
                                project_name: e.target.value,
                              })
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
                              handleProjectChange(experience.clientId, project.clientId, {
                                project_description: e.target.value,
                              })
                            }
                            placeholder="What you built or contributed (optional)"
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      </div>

      <div className="shrink-0 flex items-center justify-end gap-2 border-t border-border-subtle bg-surface-bg/70 px-0 py-3">
        <button
          type="button"
          onClick={handleSkip}
          disabled={saving}
          className="rounded-md border border-border-subtle px-4 py-2 text-xs font-semibold text-text-muted hover:bg-card hover:text-text-main disabled:opacity-60"
        >
          Skip for Now
        </button>
        <button
          type="submit"
          disabled={!canSave}
          className="rounded-md bg-sky-700 px-4 py-2 text-xs font-semibold text-white hover:bg-sky-800 disabled:opacity-60 inline-flex items-center gap-2"
        >
          {saving ? <Loader2 size={14} className="animate-spin" /> : null}
          Save for Later
        </button>
      </div>
    </form>
  );
};

export default WorkProjectsTab;
