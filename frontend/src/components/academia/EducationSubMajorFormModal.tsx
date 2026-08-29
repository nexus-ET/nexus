import { useEffect } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Loader2, X } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';

import { apiFetch } from '../../utils/api';
import { fetchAcademiaListItems } from '../../utils/academiaList';
import {
  emptySubMajorFormValues,
  subMajorSchema,
  type SubMajorFormValues,
} from '../../schemas/subMajorSchema';
import {
  educationMajorOptionLabel,
  type EducationMajorRecord,
} from '../../types/educationMajor';
import type { EducationSubMajorRecord } from '../../types/educationSubMajor';
import RichTextEditor from '../ui/rich-text-editor';
import { FrameworkIdField } from './FrameworkIdDisplay';
import SelectField from './form/SelectField';

interface EducationSubMajorFormModalProps {
  open: boolean;
  subMajor: EducationSubMajorRecord | null;
  onClose: () => void;
  onSaved: () => void;
}

const EducationSubMajorFormModal: React.FC<EducationSubMajorFormModalProps> = ({
  open,
  subMajor,
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
  } = useForm<SubMajorFormValues>({
    resolver: zodResolver(subMajorSchema),
    defaultValues: emptySubMajorFormValues,
    mode: 'onSubmit',
  });

  const majorId = watch('major_id');

  const majorsQuery = useQuery({
    queryKey: ['academia-majors-for-sub-major-form'],
    queryFn: () =>
      fetchAcademiaListItems<EducationMajorRecord>('academia/education-majors', {
        active_only: 'false',
        catalog_only: 'true',
      }),
    enabled: open,
  });

  useEffect(() => {
    if (!open) return;
    if (subMajor) {
      reset({
        name: subMajor.name,
        major_id: subMajor.major_id,
        sub_major_description: subMajor.sub_major_description || null,
      });
      return;
    }
    reset(emptySubMajorFormValues);
  }, [open, reset, subMajor]);

  if (!open) return null;

  const onSubmit = handleSubmit(async values => {
    try {
      const payload = {
        name: values.name.trim(),
        major_id: values.major_id,
        sub_major_description: values.sub_major_description?.trim() || null,
      };
      if (subMajor) {
        await apiFetch(`academia/education-sub-majors/${subMajor.id}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        });
      } else {
        await apiFetch('academia/education-sub-majors', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
      }
      onSaved();
      onClose();
    } catch (err) {
      setError('root', {
        message: err instanceof Error ? err.message : 'Failed to save sub-major',
      });
    }
  });

  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="flex max-h-[90vh] min-h-[min(82vh,760px)] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-border-subtle bg-card shadow-2xl">
        <div className="flex shrink-0 items-center justify-between border-b border-border-subtle px-5 py-4">
          <div>
            <h3 className="text-lg font-bold text-text-main">
              {subMajor ? 'Edit Sub-Major' : 'Create Sub-Major'}
            </h3>
            <p className="text-xs text-text-muted">
              Concentrations under a catalog major. Parent major cannot be deleted while
              sub-majors remain.
            </p>
          </div>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-text-muted hover:bg-surface-bg">
            <X size={18} />
          </button>
        </div>
        <form onSubmit={onSubmit} noValidate className="flex min-h-0 flex-1 flex-col space-y-4 overflow-y-auto p-5">
          <FrameworkIdField value={subMajor?.id} />
          <FrameworkIdField label="Major ID" value={majorId || undefined} placeholder="—" />
          <SelectField
            label="Parent major"
            required
            value={majorId ? String(majorId) : ''}
            onChange={value => setValue('major_id', value ? Number(value) : 0, { shouldValidate: true })}
            placeholder={majorsQuery.isLoading ? 'Loading majors...' : 'Select a major'}
            options={(majorsQuery.data ?? []).map(major => ({
              value: String(major.id),
              label: educationMajorOptionLabel(major),
            }))}
            hint="Required. Sub-majors belong to one catalog major."
          />
          {errors.major_id ? <p className="text-xs text-alert">{errors.major_id.message}</p> : null}

          <label className="block space-y-1 text-sm">
            <span className="font-medium text-text-main">Sub-major name *</span>
            <input
              type="text"
              {...register('name')}
              placeholder="e.g. Cybersecurity, Data Science & AI"
              className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
            />
            {errors.name ? <p className="text-xs text-alert">{errors.name.message}</p> : null}
          </label>

          <Controller
            control={control}
            name="sub_major_description"
            render={({ field, fieldState }) => (
              <RichTextEditor
                label="Sub-major description"
                content={field.value || ''}
                onChange={field.onChange}
                maxLength={2000}
                placeholder="Short counselor-facing description of this concentration"
                error={fieldState.error?.message}
              />
            )}
          />

          {errors.root ? <p className="text-sm text-alert">{errors.root.message}</p> : null}

          <div className="mt-auto flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl border border-border-subtle px-4 py-2 text-sm font-semibold text-text-muted"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg disabled:opacity-50"
            >
              {isSubmitting ? <Loader2 size={16} className="animate-spin" /> : null}
              Save Sub-Major
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default EducationSubMajorFormModal;
