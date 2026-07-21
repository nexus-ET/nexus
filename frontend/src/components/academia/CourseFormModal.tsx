import { useEffect, useMemo } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Loader2, X } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';

import { apiFetch } from '../../utils/api';
import { fetchAcademiaListItems } from '../../utils/academiaList';
import { ACADEMIC_FRAMEWORK_STEP_LABELS } from '../../schemas/academicFrameworkHierarchy';
import {
  courseSchema,
  emptyCourseFormValues,
  type CourseFormValues,
} from '../../schemas/courseSchema';
import type { CourseRecord } from '../../types/academicFramework';
import type { EducationMajorRecord } from '../../types/educationMajor';
import {
  buildMajorColorById,
  buildMajorColorByLabel,
  resolveMajorColor,
} from '../../utils/majorColors';
import ActiveStatusField from './ActiveStatusField';
import SearchableMultiSelect from './SearchableMultiSelect';
import RichTextEditor from '../ui/rich-text-editor';

interface CourseFormModalProps {
  open: boolean;
  course: CourseRecord | null;
  presetMajorId?: string;
  onClose: () => void;
  onSaved: () => void;
}

const resolveCourseMajorIds = (course: CourseRecord | null, presetMajorId: string): number[] => {
  if (course) {
    const fromRecord = (course.major_ids ?? [])
      .map(Number)
      .filter(id => Number.isInteger(id) && id > 0);
    if (fromRecord.length > 0) return [...new Set(fromRecord)];
    if (course.major_id) return [Number(course.major_id)];
    return [];
  }
  if (presetMajorId) {
    const preset = Number(presetMajorId);
    return Number.isInteger(preset) && preset > 0 ? [preset] : [];
  }
  return [];
};

const CourseFormModal: React.FC<CourseFormModalProps> = ({
  open,
  course,
  presetMajorId = '',
  onClose,
  onSaved,
}) => {
  const {
    control,
    register,
    handleSubmit,
    reset,
    setValue,
    watch,
    formState: { errors, isSubmitting },
    setError,
  } = useForm<CourseFormValues>({
    resolver: zodResolver(courseSchema),
    defaultValues: emptyCourseFormValues,
    mode: 'onSubmit',
  });

  const majorIds = watch('major_ids') ?? [];
  const isActive = watch('is_active');
  const initialIsActive = course?.is_active ?? true;

  useEffect(() => {
    if (!open) return;
    reset(
      course
        ? {
            major_ids: resolveCourseMajorIds(course, ''),
            name: course.name || course.label || '',
            code: course.code || '',
            description: course.description || null,
            is_active: course.is_active ?? true,
          }
        : {
            ...emptyCourseFormValues,
            major_ids: resolveCourseMajorIds(null, presetMajorId),
          }
    );
  }, [course, open, presetMajorId, reset]);

  const majorsQuery = useQuery({
    queryKey: ['academia-majors-for-course'],
    queryFn: () =>
      fetchAcademiaListItems<EducationMajorRecord>('academia/education-majors', {
        active_only: 'true',
        catalog_only: 'true',
      }),
    enabled: open,
  });

  const majors = majorsQuery.data ?? [];
  const majorColorByLabel = useMemo(() => buildMajorColorByLabel(majors), [majors]);
  const majorColorById = useMemo(() => buildMajorColorById(majors), [majors]);

  const majorOptions = useMemo(
    () =>
      [...majors]
        .sort((left, right) =>
          left.label.localeCompare(right.label, undefined, { sensitivity: 'base' })
        )
        .map(major => {
          const suffix = major.code ? ` (${major.code})` : '';
          return {
            value: String(major.id),
            label: `${major.label}${suffix}`,
            color: resolveMajorColor(major, majorColorByLabel, majorColorById),
          };
        }),
    [majorColorById, majorColorByLabel, majors]
  );

  const majorSelectedDisplay = useMemo(() => {
    if (majorIds.length === 0) return undefined;
    if (majorIds.length === 1) {
      const match = majorOptions.find(option => option.value === String(majorIds[0]));
      return match?.label;
    }
    return `${majorIds.length} majors selected`;
  }, [majorIds, majorOptions]);

  if (!open) return null;

  const onSubmit = handleSubmit(async values => {
    const resolvedMajorIds = [...new Set(values.major_ids.filter(id => id > 0))];
    const payload = {
      major_ids: resolvedMajorIds,
      major_id: resolvedMajorIds[0],
      name: values.name.trim(),
      code: values.code?.trim() ? values.code.trim().toUpperCase() : null,
      description: values.description?.trim() || null,
      is_active: values.is_active,
    };
    try {
      if (course) {
        await apiFetch(`academia/courses/${course.id}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        });
      } else {
        await apiFetch('academia/courses', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
      }
      onSaved();
      onClose();
    } catch (err) {
      setError('root', {
        message: err instanceof Error ? err.message : 'Failed to save course',
      });
    }
  });

  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-border-subtle bg-card shadow-2xl">
        <div className="flex items-center justify-between border-b border-border-subtle px-5 py-4">
          <div>
            <h3 className="text-lg font-bold text-text-main">
              {course ? 'Edit Course' : 'Add Course'}
            </h3>
            <p className="text-xs text-text-muted">
              Map this course to one or more majors and enter the course details.
            </p>
          </div>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-text-muted hover:bg-surface-bg">
            <X size={18} />
          </button>
        </div>
        <form onSubmit={onSubmit} className="space-y-4 p-5">
          <Controller
            control={control}
            name="major_ids"
            render={({ field }) => (
              <SearchableMultiSelect
                label={ACADEMIC_FRAMEWORK_STEP_LABELS.major}
                values={(field.value ?? []).map(String)}
                options={majorOptions}
                onChange={values =>
                  field.onChange(
                    values
                      .map(Number)
                      .filter(id => Number.isInteger(id) && id > 0)
                  )
                }
                placeholder={
                  majorsQuery.isLoading
                    ? 'Loading majors...'
                    : majorOptions.length === 0
                      ? 'No majors available'
                      : 'Select one or more majors'
                }
                emptyMessage="No majors found."
                required
                disabled={majorsQuery.isLoading || majorOptions.length === 0}
                hint="Only catalog majors from the Majors page are listed. A course can belong to multiple majors."
                selectedDisplay={majorSelectedDisplay}
              />
            )}
          />
          {errors.major_ids ? (
            <p className="text-sm text-alert">{errors.major_ids.message}</p>
          ) : null}

          <label className="block space-y-1 text-sm">
            <span className="text-base font-bold text-text-main">
              {ACADEMIC_FRAMEWORK_STEP_LABELS.course} *
            </span>
            <input
              {...register('name')}
              placeholder="e.g. Thermodynamics 101"
              className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
            />
            {errors.name ? <p className="text-sm text-alert">{errors.name.message}</p> : null}
          </label>

          <label className="block space-y-1 text-sm">
            <span className="font-medium text-text-main">Course code</span>
            <input
              {...register('code')}
              placeholder="Optional — e.g. THERMO_101"
              className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm uppercase outline-none focus:border-accent"
            />
            {errors.code ? <p className="text-sm text-alert">{errors.code.message}</p> : null}
          </label>

          <Controller
            control={control}
            name="description"
            render={({ field, fieldState }) => (
              <RichTextEditor
                label="Description"
                content={field.value || ''}
                onChange={field.onChange}
                maxLength={5000}
                error={fieldState.error?.message}
              />
            )}
          />

          {course ? (
            <ActiveStatusField
              entityType="course"
              entityId={course?.id}
              value={isActive}
              initialValue={initialIsActive}
              onChange={next => setValue('is_active', next)}
            />
          ) : null}

          {errors.root ? <p className="text-sm text-alert">{errors.root.message}</p> : null}

          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="rounded-xl border border-border-subtle px-4 py-2 text-sm font-semibold text-text-muted">
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting || majorIds.length === 0}
              className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg disabled:opacity-50"
            >
              {isSubmitting ? <Loader2 size={16} className="animate-spin" /> : null}
              Save Course
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default CourseFormModal;
