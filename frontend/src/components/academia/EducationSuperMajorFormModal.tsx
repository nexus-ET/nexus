import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Loader2, X } from 'lucide-react';

import { apiFetch } from '../../utils/api';
import {
  emptySuperMajorFormValues,
  superMajorSchema,
  type SuperMajorFormValues,
} from '../../schemas/superMajorSchema';
import type { EducationSuperMajorRecord } from '../../types/educationSuperMajor';
import { FrameworkIdField } from './FrameworkIdDisplay';

interface EducationSuperMajorFormModalProps {
  open: boolean;
  superMajor: EducationSuperMajorRecord | null;
  onClose: () => void;
  onSaved: () => void;
}

const EducationSuperMajorFormModal: React.FC<EducationSuperMajorFormModalProps> = ({
  open,
  superMajor,
  onClose,
  onSaved,
}) => {
  const {
    register,
    handleSubmit,
    reset,
    watch,
    setValue,
    formState: { errors, isSubmitting },
    setError,
  } = useForm<SuperMajorFormValues>({
    resolver: zodResolver(superMajorSchema),
    defaultValues: emptySuperMajorFormValues,
    mode: 'onSubmit',
  });

  const isActive = watch('is_active');

  useEffect(() => {
    if (!open) return;
    if (superMajor) {
      reset({
        name: superMajor.name,
        code: superMajor.code || '',
        description: superMajor.description || null,
        sort_order: superMajor.sort_order ?? 0,
        is_active: superMajor.is_active ?? true,
      });
      return;
    }
    reset(emptySuperMajorFormValues);
  }, [open, reset, superMajor]);

  if (!open) return null;

  const onSubmit = handleSubmit(async values => {
    try {
      const payload = {
        name: values.name.trim(),
        code: values.code?.trim() ? values.code.trim().toUpperCase() : null,
        description: values.description?.trim() || null,
        sort_order: values.sort_order ?? 0,
        is_active: values.is_active ?? true,
      };
      if (superMajor) {
        await apiFetch(`academia/education-super-majors/${superMajor.id}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        });
      } else {
        await apiFetch('academia/education-super-majors', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
      }
      onSaved();
      onClose();
    } catch (err) {
      setError('root', {
        message: err instanceof Error ? err.message : 'Failed to save super-major',
      });
    }
  });

  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-border-subtle bg-card shadow-2xl">
        <div className="flex items-center justify-between border-b border-border-subtle px-5 py-4">
          <div>
            <h3 className="text-lg font-bold text-text-main">
              {superMajor ? 'Edit Super-Major' : 'Create Super-Major'}
            </h3>
            <p className="text-xs text-text-muted">
              Marketing clusters that group catalog majors for browsing and reporting.
            </p>
          </div>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-text-muted hover:bg-surface-bg">
            <X size={18} />
          </button>
        </div>
        <form onSubmit={onSubmit} noValidate className="space-y-4 p-5">
          <FrameworkIdField value={superMajor?.id} />

          <label className="block space-y-1 text-sm">
            <span className="font-medium text-text-main">Super-major name *</span>
            <input
              type="text"
              {...register('name')}
              placeholder="e.g. Computer Science & Information Technology"
              className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
            />
            {errors.name ? <p className="text-xs text-alert">{errors.name.message}</p> : null}
          </label>

          <label className="block space-y-1 text-sm">
            <span className="font-medium text-text-main">Description</span>
            <textarea
              rows={4}
              {...register('description')}
              placeholder="Optional marketing or grouping description"
              className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
            />
            {errors.description ? (
              <p className="text-xs text-alert">{errors.description.message}</p>
            ) : null}
          </label>

          <label className="block space-y-1 text-sm">
            <span className="font-medium text-text-main">Code</span>
            <input
              type="text"
              {...register('code')}
              placeholder="Optional — auto-generated from name if blank"
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

          <label className="block space-y-1 text-sm">
            <span className="font-medium text-text-main">Status</span>
            <select
              value={isActive ? 'active' : 'inactive'}
              onChange={event => setValue('is_active', event.target.value === 'active')}
              className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
            >
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
          </label>

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
              Save Super-Major
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default EducationSuperMajorFormModal;
