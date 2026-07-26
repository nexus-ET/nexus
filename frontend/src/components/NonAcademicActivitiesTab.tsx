import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import DatePicker from 'react-datepicker';
import 'react-datepicker/dist/react-datepicker.css';
import { Info, Loader2, Pencil, Plus, Trash2 } from 'lucide-react';
import { apiFetch } from '../utils/api';
import { useConfirmation } from '../context/ConfirmationContext';
import EmptyListMessage from './ui/EmptyListMessage';
import { formatLocalIsoDate, parseLocalIsoDate } from '../types/candidateProfile';
import { nexusDatePickerPortalProps } from '../utils/nexusDatePickerPortal';
import {
  DESCRIPTION_MAX_LENGTH,
  NAME_MAX_LENGTH,
  ROLE_MAX_LENGTH,
  activityToForm,
  emptyNonAcademicActivityForm,
  filterActivityCategoryOptions,
  formToSavePayload,
  formatActivityDateRange,
  getActivityCategoryLabel,
  validateNonAcademicActivityForm,
  type ActivityCategory,
  type ActivityCategoryOption,
  type NonAcademicActivitiesResponse,
  type NonAcademicActivityFormState,
  type NonAcademicActivityRecord,
} from '../types/nonAcademicActivity';
import {
  studentInfoFieldErrorClass as fieldErrorClass,
  studentInfoInputClass as inputClass,
  studentInfoLabelClass as labelClass,
  studentInfoSectionClass as sectionClass,
} from './studentInfoFormStyles';

interface NonAcademicActivitiesTabProps {
  bookingId: number;
  compact?: boolean;
}

const fieldClass = (hasError: boolean) =>
  `${inputClass}${hasError ? ' border-red-400 ring-1 ring-red-200' : ''}`;

const cardClass = 'rounded-md border border-border-subtle bg-surface-bg/40 p-3 space-y-2';

const NonAcademicActivitiesTab: React.FC<NonAcademicActivitiesTabProps> = ({
  bookingId,
  compact = false,
}) => {
  const openConfirm = useConfirmation();
  const [activities, setActivities] = useState<NonAcademicActivityRecord[]>([]);
  const [categoryOptions, setCategoryOptions] = useState<ActivityCategoryOption[]>([]);
  const [form, setForm] = useState<NonAcademicActivityFormState>(emptyNonAcademicActivityForm);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [categorySearch, setCategorySearch] = useState('');
  const [showCategoryDropdown, setShowCategoryDropdown] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [showTooltip, setShowTooltip] = useState(false);

  const categoryDropdownRef = useRef<HTMLDivElement>(null);
  const apiPath = `bookings/mine/${bookingId}/non-academic-activities`;

  const filteredCategoryOptions = useMemo(
    () => filterActivityCategoryOptions(categorySearch, categoryOptions),
    [categoryOptions, categorySearch]
  );

  const validationErrors = useMemo(() => validateNonAcademicActivityForm(form), [form]);
  const canSave = Object.keys(validationErrors).length === 0 && !saving;

  const startDate = useMemo(() => parseLocalIsoDate(form.start_date), [form.start_date]);
  const endDate = useMemo(() => parseLocalIsoDate(form.end_date), [form.end_date]);

  const loadActivities = useCallback(async () => {
    const response = (await apiFetch(apiPath)) as NonAcademicActivitiesResponse;
    setActivities(response.activities);
    setCategoryOptions(response.activity_categories);
  }, [apiPath]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setSuccess(null);

    loadActivities()
      .catch(err => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Failed to load non-academic activities.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [loadActivities]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        categoryDropdownRef.current &&
        !categoryDropdownRef.current.contains(event.target as Node)
      ) {
        setShowCategoryDropdown(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const resetForm = () => {
    setForm(emptyNonAcademicActivityForm());
    setEditingId(null);
    setCategorySearch('');
    setFieldErrors({});
  };

  const handleAddAnother = () => {
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

  const updateForm = (patch: Partial<NonAcademicActivityFormState>) => {
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

  const handleSelectCategory = (value: ActivityCategory, label: string) => {
    updateForm({ activity_category: value });
    setCategorySearch(label);
    setShowCategoryDropdown(false);
  };

  const handleEdit = (activity: NonAcademicActivityRecord) => {
    setForm(activityToForm(activity));
    setCategorySearch(activity.activity_category_label ?? '');
    setEditingId(activity.id);
    setShowForm(true);
    setError(null);
    setSuccess(null);
    setFieldErrors({});
  };

  const handleDelete = async (activityId: number) => {
    if (!(await openConfirm({
      title: 'Delete activity?',
      message: 'Delete this activity?',
      confirmLabel: 'Delete',
      variant: 'danger',
    }))) {
      return;
    }

    try {
      setDeletingId(activityId);
      setError(null);
      setSuccess(null);
      const response = (await apiFetch(`${apiPath}/${activityId}`, {
        method: 'DELETE',
      })) as NonAcademicActivitiesResponse;
      setActivities(response.activities);
      if (editingId === activityId) {
        resetForm();
        setShowForm(false);
      }
      setSuccess('Activity deleted.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete activity.');
    } finally {
      setDeletingId(null);
    }
  };

  const handleSave = async (event: React.FormEvent) => {
    event.preventDefault();
    const errors = validateNonAcademicActivityForm(form);
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      setError('Please fix the highlighted fields before saving.');
      setSuccess(null);
      return;
    }

    try {
      setSaving(true);
      setError(null);
      setSuccess(null);
      setFieldErrors({});
      const payload = formToSavePayload(form);
      const response = (await apiFetch(
        editingId ? `${apiPath}/${editingId}` : apiPath,
        {
          method: editingId ? 'PUT' : 'POST',
          body: JSON.stringify(payload),
        }
      )) as NonAcademicActivitiesResponse;
      setActivities(response.activities);
      resetForm();
      setShowForm(false);
      setSuccess(editingId ? 'Activity updated.' : 'Activity saved. Add another anytime.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save activity.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-text-muted">
        <Loader2 size={22} className="animate-spin mr-2" />
        Loading non-academic activities...
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
            <div className="flex items-center gap-1.5">
              <h3 className="text-sm font-bold text-text-main uppercase tracking-wide">
                Non-Academic Activities (Optional)
              </h3>
              <div className="relative">
                <button
                  type="button"
                  className="text-text-muted hover:text-text-main"
                  aria-label="About non-academic activities"
                  onMouseEnter={() => setShowTooltip(true)}
                  onMouseLeave={() => setShowTooltip(false)}
                  onFocus={() => setShowTooltip(true)}
                  onBlur={() => setShowTooltip(false)}
                >
                  <Info size={13} />
                </button>
                {showTooltip ? (
                  <div className="absolute left-0 top-full z-10 mt-1 w-64 rounded-md border border-border-subtle bg-card px-2.5 py-2 text-xs text-text-muted shadow-sm">
                    Optional: Share clubs, sports, volunteering, and other experiences outside
                    academics.
                  </div>
                ) : null}
              </div>
            </div>
            {!showForm ? (
              <button
                type="button"
                onClick={handleAddAnother}
                className="inline-flex items-center gap-1 rounded-md border border-sky-200 bg-sky-50 px-2.5 py-1.5 text-sm font-semibold text-sky-800 hover:bg-sky-100"
              >
                <Plus size={12} />
                Add Another Activity
              </button>
            ) : null}
          </div>

          <p className="text-sm text-text-muted">
            Build your extracurricular profile over time. All fields are optional.
          </p>

          {showForm ? (
            <form
              onSubmit={handleSave}
              className="rounded-md border border-border-subtle bg-surface-bg/30 p-3 space-y-3"
            >
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm font-bold text-text-main">
                  {editingId ? 'Edit Activity' : 'New Activity'}
                </p>
                <button
                  type="button"
                  onClick={handleCancelForm}
                  className="text-sm text-text-muted hover:text-text-main"
                >
                  Cancel
                </button>
              </div>

              <div ref={categoryDropdownRef} className="relative">
                <label htmlFor="activity-category" className={labelClass}>
                  Activity Category
                </label>
                <input
                  id="activity-category"
                  type="text"
                  className={inputClass}
                  value={
                    categorySearch || getActivityCategoryLabel(form.activity_category, categoryOptions)
                  }
                  onChange={e => {
                    setCategorySearch(e.target.value);
                    setShowCategoryDropdown(true);
                    if (!e.target.value.trim()) {
                      updateForm({ activity_category: '' });
                    }
                  }}
                  onFocus={() => setShowCategoryDropdown(true)}
                  placeholder="Search activity category..."
                  autoComplete="off"
                />
                {showCategoryDropdown ? (
                  <div className="absolute z-20 mt-1 max-h-48 w-full overflow-y-auto rounded-md border border-border-subtle bg-card shadow-sm">
                    {filteredCategoryOptions.length === 0 ? (
                      <p className="px-2.5 py-2 text-sm text-text-muted">No matches found.</p>
                    ) : (
                      filteredCategoryOptions.map(option => (
                        <button
                          key={option.value}
                          type="button"
                          className="block w-full px-2.5 py-2 text-left text-sm text-text-main hover:bg-surface-bg"
                          onClick={() => handleSelectCategory(option.value, option.label)}
                        >
                          {option.label}
                        </button>
                      ))
                    )}
                  </div>
                ) : null}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                <div>
                  <label htmlFor="activity-name" className={labelClass}>
                    Activity Name
                  </label>
                  <input
                    id="activity-name"
                    className={fieldClass(Boolean(fieldErrors.activity_name))}
                    value={form.activity_name}
                    maxLength={NAME_MAX_LENGTH}
                    onChange={e => updateForm({ activity_name: e.target.value })}
                    placeholder="e.g. University Debate Club"
                  />
                  {fieldErrors.activity_name ? (
                    <p className={fieldErrorClass}>{fieldErrors.activity_name}</p>
                  ) : null}
                </div>
                <div>
                  <label htmlFor="activity-role" className={labelClass}>
                    Role or Title
                  </label>
                  <input
                    id="activity-role"
                    className={fieldClass(Boolean(fieldErrors.role_or_title))}
                    value={form.role_or_title}
                    maxLength={ROLE_MAX_LENGTH}
                    onChange={e => updateForm({ role_or_title: e.target.value })}
                    placeholder="e.g. Volunteer, Captain, Member"
                  />
                  {fieldErrors.role_or_title ? (
                    <p className={fieldErrorClass}>{fieldErrors.role_or_title}</p>
                  ) : null}
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
                    onChange={(date: Date | null) =>
                      updateForm({ end_date: formatLocalIsoDate(date) })
                    }
                    dateFormat="dd MMM yyyy"
                    placeholderText="Select end date (optional)"
                    className={fieldClass(Boolean(fieldErrors.end_date || validationErrors.end_date))}
                    wrapperClassName="w-full"
                    isClearable
                    {...nexusDatePickerPortalProps}
                  />
                  {fieldErrors.end_date || validationErrors.end_date ? (
                    <p className={fieldErrorClass}>
                      {fieldErrors.end_date || validationErrors.end_date}
                    </p>
                  ) : null}
                </div>
              </div>

              <div>
                <label htmlFor="activity-description" className={labelClass}>
                  Description
                </label>
                <textarea
                  id="activity-description"
                  className={`${fieldClass(Boolean(fieldErrors.description))} min-h-[96px] resize-y`}
                  value={form.description}
                  maxLength={DESCRIPTION_MAX_LENGTH}
                  onChange={e => updateForm({ description: e.target.value })}
                  placeholder="What you did and what you gained (optional)"
                />
                <p className="mt-1 text-xs text-text-muted text-right">
                  {form.description.length}/{DESCRIPTION_MAX_LENGTH}
                </p>
                {fieldErrors.description ? (
                  <p className={fieldErrorClass}>{fieldErrors.description}</p>
                ) : null}
              </div>

              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={!canSave}
                  className="rounded-md bg-sky-700 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-800 disabled:opacity-60 inline-flex items-center gap-2"
                >
                  {saving ? <Loader2 size={14} className="animate-spin" /> : null}
                  {editingId ? 'Update Activity' : 'Save Activity'}
                </button>
              </div>
            </form>
          ) : null}

          {activities.length === 0 ? (
            <EmptyListMessage
              compact
              message='No activities added yet. Click "Add Another Activity" when you are ready.'
            />
          ) : (
            <div className="space-y-3">
              {activities.map(activity => {
                const dateRange = formatActivityDateRange(activity.start_date, activity.end_date);
                return (
                  <div key={activity.id} className={cardClass}>
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        {activity.activity_category_label ? (
                          <p className="text-xs font-semibold uppercase tracking-wide text-sky-800">
                            {activity.activity_category_label}
                          </p>
                        ) : null}
                        <p className="text-xs font-bold text-text-main truncate">
                          {activity.activity_name || 'Untitled activity'}
                        </p>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <button
                          type="button"
                          onClick={() => handleEdit(activity)}
                          className="inline-flex items-center gap-1 text-sm text-sky-700 hover:text-sky-900"
                        >
                          <Pencil size={12} />
                          Edit
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDelete(activity.id)}
                          disabled={deletingId === activity.id}
                          className="inline-flex items-center gap-1 text-sm text-red-600 hover:text-red-700 disabled:opacity-60"
                        >
                          {deletingId === activity.id ? (
                            <Loader2 size={12} className="animate-spin" />
                          ) : (
                            <Trash2 size={12} />
                          )}
                          Delete
                        </button>
                      </div>
                    </div>

                    {activity.role_or_title ? (
                      <p className="text-sm text-text-muted">
                        <span className="font-bold text-text-main">Role:</span>{' '}
                        {activity.role_or_title}
                      </p>
                    ) : null}

                    {dateRange ? (
                      <p className="text-sm text-text-muted">{dateRange}</p>
                    ) : null}

                    {activity.description ? (
                      <p className="text-sm text-text-main whitespace-pre-wrap">
                        {activity.description}
                      </p>
                    ) : null}
                  </div>
                );
              })}
            </div>
          )}

          {!showForm && activities.length > 0 ? (
            <div className="flex justify-center pt-1">
              <button
                type="button"
                onClick={handleAddAnother}
                className="inline-flex items-center gap-1 rounded-md border border-border-subtle px-3 py-1.5 text-sm font-semibold text-text-main hover:bg-card"
              >
                <Plus size={12} />
                Add Another Activity
              </button>
            </div>
          ) : null}
        </section>
      </div>
    </div>
  );
};

export default NonAcademicActivitiesTab;
