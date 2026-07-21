import { useEffect, useMemo, useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Loader2, X } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';

import { apiFetch } from '../../utils/api';
import { fetchAcademiaListItems } from '../../utils/academiaList';
import { assignMajorColor } from '../../utils/majorColors';
import {
  emptyMajorFormValues,
  majorSchema,
  type MajorFormValues,
} from '../../schemas/majorSchema';
import type { EducationMajorRecord } from '../../types/educationMajor';
import ActiveStatusField from './ActiveStatusField';
import MajorColorSwatch from './MajorColorSwatch';
import RichTextEditor from '../ui/rich-text-editor';

interface EducationMajorFormModalProps {
  open: boolean;
  major: EducationMajorRecord | null;
  onClose: () => void;
  onSaved: () => void;
}

const EducationMajorFormModal: React.FC<EducationMajorFormModalProps> = ({
  open,
  major,
  onClose,
  onSaved,
}) => {
  const {
    control,
    register,
    handleSubmit,
    reset,
    watch,
    setValue,
    formState: { errors, isSubmitting },
    setError,
  } = useForm<MajorFormValues>({
    resolver: zodResolver(majorSchema),
    defaultValues: emptyMajorFormValues,
    mode: 'onSubmit',
  });

  const isActive = watch('is_active');
  const labelValue = watch('label');

  const majorsForDuplicateCheckQuery = useQuery({
    queryKey: ['academia-majors-for-duplicate-check'],
    queryFn: () =>
      fetchAcademiaListItems<EducationMajorRecord>('academia/education-majors', {
        active_only: 'false',
        catalog_only: 'true',
      }),
    enabled: open,
  });

  const [assignedColor, setAssignedColor] = useState<string | null>(major?.color ?? null);

  useEffect(() => {
    if (!open) return;
    setAssignedColor(major?.color ?? null);
    const hydrate = async () => {
      if (major) {
        let record = major;
        try {
          record = await apiFetch<EducationMajorRecord>(`academia/education-majors/${major.id}`);
        } catch {
          record = major;
        }
        setAssignedColor(record.color ?? null);
        reset({
          label: record.label,
          code: record.code || '',
          description: record.description || null,
          sort_order: record.sort_order ?? 0,
          is_other: record.is_other ?? false,
          is_active: record.is_active ?? true,
        });
        return;
      }
      setAssignedColor(null);
      reset(emptyMajorFormValues);
    };
    void hydrate();
  }, [major, open, reset]);

  const previewColor = useMemo(() => {
    if (assignedColor) return assignedColor;
    const existingMajors = (majorsForDuplicateCheckQuery.data ?? []).filter(
      item => item.id !== major?.id
    );
    const usedColors = existingMajors.map(item => item.color);
    return assignMajorColor(labelValue?.trim() || 'Major', usedColors, existingMajors.length);
  }, [assignedColor, labelValue, major?.id, majorsForDuplicateCheckQuery.data]);

  if (!open) return null;

  const onSubmit = handleSubmit(async values => {
    const normalizedLabel = values.label.trim().toLocaleLowerCase();
    const duplicate = (majorsForDuplicateCheckQuery.data ?? []).some(
      item =>
        item.id !== major?.id &&
        !item.program_id &&
        item.label.trim().toLocaleLowerCase() === normalizedLabel
    );
    if (duplicate) {
      setError('label', {
        message: 'A major with this name already exists.',
      });
      return;
    }
    try {
      const payload = {
        label: values.label.trim(),
        code: values.code?.trim() ? values.code.trim().toUpperCase() : null,
        description: values.description?.trim() || null,
        sort_order: values.sort_order ?? 0,
        is_other: values.is_other ?? false,
        is_active: values.is_active ?? true,
      };
      if (major) {
        await apiFetch(`academia/education-majors/${major.id}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        });
      } else {
        await apiFetch('academia/education-majors', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
      }
      onSaved();
      onClose();
    } catch (err) {
      setError('root', {
        message: err instanceof Error ? err.message : 'Failed to save major',
      });
    }
  });

  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-border-subtle bg-card shadow-2xl">
        <div className="flex items-center justify-between border-b border-border-subtle px-5 py-4">
          <div>
            <h3 className="text-lg font-bold text-text-main">
              {major ? 'Edit Major' : 'Create Major'}
            </h3>
            <p className="text-xs text-text-muted">
              Create a major, then assign it when creating or editing a program.
            </p>
          </div>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-text-muted hover:bg-surface-bg">
            <X size={18} />
          </button>
        </div>
        <form onSubmit={onSubmit} noValidate className="space-y-4 p-5">
          <div className="flex items-center gap-3 rounded-xl border border-border-subtle bg-surface-bg/60 px-3 py-2">
            <MajorColorSwatch color={previewColor} label={labelValue || 'Major'} size="md" />
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
                Major color
              </p>
              <p className="text-sm text-text-main">
                {major
                  ? 'Assigned automatically and kept for program assignment.'
                  : 'Assigned automatically when you save this major.'}
              </p>
            </div>
            <span className="ml-auto font-mono text-xs text-text-muted">{previewColor}</span>
          </div>

          <label className="block space-y-1 text-sm">
            <span className="font-medium text-text-main">Major name *</span>
            <input
              type="text"
              {...register('label')}
              placeholder="e.g. Computer Science, Mechanical Engineering"
              className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
            />
            {errors.label ? <p className="text-xs text-alert">{errors.label.message}</p> : null}
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

          <label className="block space-y-1 text-sm">
            <span className="font-medium text-text-main">Major code</span>
            <input
              type="text"
              {...register('code')}
              placeholder="Optional — e.g. COMPUTER_SCIENCE"
              className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm uppercase outline-none focus:border-accent"
            />
            {errors.code ? <p className="text-xs text-alert">{errors.code.message}</p> : null}
          </label>

          <label className="block space-y-1 text-sm">
            <span className="font-medium text-text-main">Sort order</span>
            <input
              type="number"
              min={0}
              {...register('sort_order')}
              className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
            />
          </label>

          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" {...register('is_other')} className="rounded border-border-subtle" />
            <span className="font-medium text-text-main">Other / catch-all option</span>
          </label>

          <ActiveStatusField
            entityType="major"
            entityId={major?.id}
            value={isActive}
            initialValue={major?.is_active ?? true}
            onChange={next => setValue('is_active', next)}
          />

          {errors.root ? (
            <p className="text-sm text-alert">{errors.root.message}</p>
          ) : null}

          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="rounded-xl border border-border-subtle px-4 py-2 text-sm font-semibold text-text-muted">
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg disabled:opacity-50"
            >
              {isSubmitting ? <Loader2 size={16} className="animate-spin" /> : null}
              Save Major
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default EducationMajorFormModal;
