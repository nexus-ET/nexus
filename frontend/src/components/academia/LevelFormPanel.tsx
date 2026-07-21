import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Loader2, X } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiFetch } from '../../utils/api';
import { isDuplicateLevelName } from '../../utils/frameworkNameUniqueness';
import {
  emptyLevelFormValues,
  levelSchema,
  type LevelFormValues,
} from '../../schemas/levelSchema';
import type { LevelRecord } from '../../types/level';

interface LevelFormPanelProps {
  level: LevelRecord | null;
  mode: 'create' | 'edit';
  onCancel: () => void;
  onSaved: () => void;
}

const LevelFormPanel: React.FC<LevelFormPanelProps> = ({
  level,
  mode,
  onCancel,
  onSaved,
}) => {
  const queryClient = useQueryClient();
  const levelsQuery = useQuery({
    queryKey: ['academia-levels'],
    queryFn: () => apiFetch<LevelRecord[]>('academia/levels'),
  });
  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors },
  } = useForm<LevelFormValues>({
    resolver: zodResolver(levelSchema),
    defaultValues: emptyLevelFormValues,
    mode: 'onSubmit',
  });

  useEffect(() => {
    if (mode === 'edit' && level) {
      reset({
        name: level.name,
        code: level.code,
        description: level.description ?? null,
      });
      return;
    }
    reset(emptyLevelFormValues);
  }, [level, mode, reset]);

  const mutation = useMutation({
    mutationFn: async (values: LevelFormValues) => {
      const payload = {
        name: values.name,
        code: values.code,
        description: values.description || null,
      };
      if (mode === 'edit' && level) {
        return apiFetch<LevelRecord>(`academia/levels/${level.id}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        });
      }
      return apiFetch<LevelRecord>('academia/levels', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['academia-levels'] });
      await queryClient.invalidateQueries({ queryKey: ['levels'] });
      onSaved();
    },
  });

  const onSubmit = handleSubmit(values => {
    if (isDuplicateLevelName(values.name, levelsQuery.data ?? [], level?.id ?? null)) {
      setError('name', { message: 'A level with this name already exists.' });
      return;
    }
    mutation.mutate(values);
  });

  return (
    <div className="rounded-2xl border border-border-subtle bg-surface-bg/40">
      <div className="flex items-center justify-between border-b border-border-subtle px-5 py-4">
        <div>
          <h3 className="text-lg font-bold text-text-main">
            {mode === 'edit' ? 'Edit Level' : 'Create Level'}
          </h3>
          <p className="text-sm text-text-muted">
            Master academic levels such as Undergraduate or Graduate.
          </p>
        </div>
        {mode === 'edit' ? (
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md p-1 text-text-muted hover:bg-card hover:text-text-main"
            aria-label="Close form"
          >
            <X size={18} />
          </button>
        ) : null}
      </div>

      <form onSubmit={onSubmit} className="space-y-4 p-5">
        <label className="block space-y-1 text-sm">
          <span className="font-medium text-text-main">Name *</span>
          <input
            {...register('name')}
            placeholder="e.g. Undergraduate"
            className="w-full rounded-xl border border-border-subtle bg-card px-3 py-2 text-sm outline-none focus:border-accent"
          />
          {errors.name ? <p className="text-sm text-alert">{errors.name.message}</p> : null}
        </label>

        <label className="block space-y-1 text-sm">
          <span className="font-medium text-text-main">Code *</span>
          <input
            {...register('code')}
            placeholder="e.g. UNDERGRAD"
            className="w-full rounded-xl border border-border-subtle bg-card px-3 py-2 text-sm uppercase outline-none focus:border-accent"
          />
          {errors.code ? <p className="text-sm text-alert">{errors.code.message}</p> : null}
        </label>

        <label className="block space-y-1 text-sm">
          <span className="font-medium text-text-main">Description</span>
          <textarea
            {...register('description')}
            rows={3}
            placeholder="Short overview of this academic level..."
            className="w-full rounded-xl border border-border-subtle bg-card px-3 py-2 text-sm outline-none focus:border-accent"
          />
          {errors.description ? (
            <p className="text-sm text-alert">{errors.description.message}</p>
          ) : null}
        </label>

        {mutation.isError ? (
          <p className="text-sm text-alert">
            {mutation.error instanceof Error ? mutation.error.message : 'Failed to save level'}
          </p>
        ) : null}

        <div className="flex justify-end gap-3 pt-2">
          {mode === 'edit' ? (
            <button
              type="button"
              onClick={onCancel}
              className="rounded-xl border border-border-subtle px-4 py-2 text-sm font-semibold text-text-muted hover:text-text-main"
            >
              Cancel
            </button>
          ) : null}
          <button
            type="submit"
            disabled={mutation.isPending}
            className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg disabled:opacity-50"
          >
            {mutation.isPending ? <Loader2 size={16} className="animate-spin" /> : null}
            {mode === 'edit' ? 'Update Level' : 'Create Level'}
          </button>
        </div>
      </form>
    </div>
  );
};

export default LevelFormPanel;
