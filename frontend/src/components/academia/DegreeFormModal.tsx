import { useCallback, useEffect, useMemo } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Loader2, X } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';

import { apiFetch } from '../../utils/api';
import { fetchAcademiaListItems } from '../../utils/academiaList';
import { isDuplicateProgramName } from '../../utils/frameworkNameUniqueness';
import { useAcademiaLevels } from '../../hooks/useLevels';
import { levelSelectOptions } from '../../constants/levels';
import { ACADEMIC_FRAMEWORK_LABELS } from '../../schemas/academicFrameworkHierarchy';
import {
  emptyProgramFormValues,
  programSchema,
  type ProgramFormValues,
} from '../../schemas/programSchema';
import type { DegreeRecord } from '../../types/academicFramework';
import type {
  EducationMajorRecord,
  ProgramMajorMappingListResponse,
} from '../../types/educationMajor';
import type { InstitutionIntakeRecord } from '../../types/academicCalendar';
import { intakeDisplayName } from '../../types/academicCalendar';
import type { InstitutionRecord } from '../../types/institutions';
import {
  buildMajorColorById,
  buildMajorColorByLabel,
  resolveMajorColor,
} from '../../utils/majorColors';
import SearchableSelect from './SearchableSelect';
import SearchableMultiSelect from './SearchableMultiSelect';
import ActiveStatusField from './ActiveStatusField';
import RichTextEditor from '../ui/rich-text-editor';

interface DegreeFormModalProps {
  open: boolean;
  degree: DegreeRecord | null;
  onClose: () => void;
  onSaved: () => void;
}

const DegreeFormModal: React.FC<DegreeFormModalProps> = ({ open, degree, onClose, onSaved }) => {
  const { levels } = useAcademiaLevels(open);
  const {
    control,
    register,
    handleSubmit,
    reset,
    watch,
    setValue,
    getValues,
    formState: { errors, isSubmitting },
    setError,
  } = useForm<ProgramFormValues>({
    resolver: zodResolver(programSchema),
    defaultValues: emptyProgramFormValues,
    mode: 'onSubmit',
  });

  const isActive = watch('is_active');
  const institutionId = watch('institution_id');
  const intakeIds = watch('intake_ids') ?? [];
  const levelId = watch('level_id');
  const majorIds = watch('major_ids') ?? [];

  const programsForLevelQuery = useQuery({
    queryKey: ['academia-programs-for-duplicate-check', levelId],
    queryFn: () =>
      fetchAcademiaListItems<DegreeRecord>('academia/degrees', {
        level_id: String(levelId),
      }),
    enabled: open && Boolean(levelId),
  });

  const majorsQuery = useQuery({
    queryKey: ['academia-majors-for-program-form'],
    queryFn: () =>
      fetchAcademiaListItems<EducationMajorRecord>('academia/education-majors', {
        active_only: 'true',
        catalog_only: 'true',
      }),
    enabled: open,
  });

  const programMajorMappingsQuery = useQuery({
    queryKey: ['academia-program-major-mappings-for-program-form', degree?.id],
    queryFn: () =>
      apiFetch<ProgramMajorMappingListResponse>('academia/program-major-mappings'),
    enabled: open && Boolean(degree?.id),
  });

  const institutionsQuery = useQuery({
    queryKey: ['academia-institutions-for-program-form'],
    queryFn: () => fetchAcademiaListItems<InstitutionRecord>('academia/institutions'),
    enabled: open,
  });

  const openIntakesQuery = useQuery({
    queryKey: ['academia-open-intakes-for-program', institutionId],
    queryFn: () =>
      apiFetch<InstitutionIntakeRecord[]>(
        `academia/institutions/${institutionId}/intakes/open`
      ),
    enabled: open && Boolean(institutionId),
  });

  const institutions = institutionsQuery.data ?? [];
  const openIntakes = openIntakesQuery.data ?? [];
  const majors = majorsQuery.data ?? [];
  const majorColorByLabel = useMemo(() => buildMajorColorByLabel(majors), [majors]);
  const majorColorById = useMemo(() => buildMajorColorById(majors), [majors]);

  const institutionOptions = useMemo(
    () => institutions.map(item => ({ value: String(item.id), label: item.name })),
    [institutions]
  );

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
    const labels = majorIds
      .map(id => majors.find(major => major.id === id)?.label)
      .filter((label): label is string => Boolean(label));
    if (labels.length > 0) {
      return labels.length === 1 ? labels[0] : `${labels[0]} +${labels.length - 1} more`;
    }
    return `${majorIds.length} major${majorIds.length === 1 ? '' : 's'} selected`;
  }, [majorIds, majors]);

  const resolveMajorIdsForProgram = useCallback(
    (record: DegreeRecord): number[] => {
      const fromRecord = (record.major_ids ?? [])
        .map(Number)
        .filter(id => Number.isInteger(id) && id > 0);
      if (fromRecord.length > 0) return [...new Set(fromRecord)];

      const mapped = (programMajorMappingsQuery.data?.items ?? [])
        .filter(item => String(item.program_id) === String(record.id))
        .map(item => Number(item.education_major_id))
        .filter(id => Number.isInteger(id) && id > 0);
      return [...new Set(mapped)];
    },
    [programMajorMappingsQuery.data?.items]
  );

  useEffect(() => {
    if (!open) return;
    let cancelled = false;

    const hydrate = async () => {
      if (!degree) {
        if (!cancelled) reset(emptyProgramFormValues);
        return;
      }

      let record = degree;
      try {
        record = await apiFetch<DegreeRecord>(`academia/degrees/${degree.id}`);
      } catch {
        record = degree;
      }
      if (cancelled) return;

      const resolvedMajorIds = resolveMajorIdsForProgram(record);
      reset({
        level_id: record.level_id,
        major_ids: resolvedMajorIds,
        code: record.code || '',
        name: record.name || '',
        description: record.description || null,
        is_active: record.is_active ?? true,
        sort_order: record.sort_order ?? 0,
        institution_id: record.institution_id ?? null,
        intake_ids: record.intake_ids ?? [],
      });
    };

    void hydrate();
    return () => {
      cancelled = true;
    };
  }, [degree, open, reset, resolveMajorIdsForProgram]);

  // Re-assert mapped majors once mapping lookup finishes (GET major_ids fallback).
  useEffect(() => {
    if (!open || !degree?.id || programMajorMappingsQuery.isLoading) return;
    const resolved = resolveMajorIdsForProgram({
      ...degree,
      major_ids: degree.major_ids ?? [],
    });
    if (resolved.length === 0) return;
    const current = (getValues('major_ids') ?? []).map(Number);
    if (current.length > 0) return;
    setValue('major_ids', resolved, { shouldDirty: false });
  }, [
    degree,
    getValues,
    open,
    programMajorMappingsQuery.data,
    programMajorMappingsQuery.isLoading,
    resolveMajorIdsForProgram,
    setValue,
  ]);

  useEffect(() => {
    if (!institutionId) {
      setValue('intake_ids', []);
    }
  }, [institutionId, setValue]);

  if (!open) return null;

  const toggleIntake = (intakeId: number) => {
    const next = intakeIds.includes(intakeId)
      ? intakeIds.filter(id => id !== intakeId)
      : [...intakeIds, intakeId];
    setValue('intake_ids', next, { shouldValidate: true });
  };

  const onSubmit = handleSubmit(async values => {
    if (
      isDuplicateProgramName(
        values.name,
        values.level_id,
        programsForLevelQuery.data ?? [],
        degree?.id ?? null
      )
    ) {
      setError('name', {
        message: 'A program with this name already exists for the selected level.',
      });
      return;
    }
    try {
      const resolvedMajorIds = [
        ...new Set(
          (values.major_ids ?? getValues('major_ids') ?? [])
            .map(Number)
            .filter(id => Number.isInteger(id) && id > 0)
        ),
      ];
      const payload = {
        name: values.name.trim(),
        code: values.code?.trim() ? values.code.trim().toUpperCase() : null,
        description: values.description?.trim() || null,
        level_id: values.level_id,
        major_ids: resolvedMajorIds,
        is_active: values.is_active,
        sort_order: values.sort_order ?? 0,
        institution_id: values.institution_id ?? null,
        intake_ids: values.intake_ids ?? [],
      };
      if (degree) {
        await apiFetch(`academia/degrees/${degree.id}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        });
      } else {
        await apiFetch('academia/degrees', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
      }
      onSaved();
      onClose();
    } catch (err) {
      setError('root', {
        message: err instanceof Error ? err.message : 'Failed to save program',
      });
    }
  });

  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-border-subtle bg-card shadow-2xl">
        <div className="flex items-center justify-between border-b border-border-subtle px-5 py-4">
          <div>
            <h3 className="text-lg font-bold text-text-main">
              {degree ? 'Edit Program' : 'Create Program'}
            </h3>
            <p className="text-xs text-text-muted">
              Level → Major → Program → Assign Open intake terms
            </p>
          </div>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-text-muted hover:bg-surface-bg">
            <X size={18} />
          </button>
        </div>
        <form onSubmit={onSubmit} noValidate className="space-y-4 p-5">
          <Controller
            control={control}
            name="level_id"
            render={({ field }) => (
              <SearchableSelect
                label="Level"
                value={field.value ? String(field.value) : ''}
                options={levelSelectOptions(levels)}
                onChange={value => field.onChange(value ? Number(value) : 0)}
                placeholder="Select level..."
                required
              />
            )}
          />
          {errors.level_id ? <p className="text-sm text-alert">{errors.level_id.message}</p> : null}

          <Controller
            control={control}
            name="major_ids"
            render={({ field }) => (
              <SearchableMultiSelect
                label={ACADEMIC_FRAMEWORK_LABELS.major}
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
                disabled={majorsQuery.isLoading}
                hint="Optional. Map this program to one or more catalog majors from the Majors page."
                selectedDisplay={majorSelectedDisplay}
              />
            )}
          />
          {errors.major_ids ? <p className="text-sm text-alert">{errors.major_ids.message}</p> : null}

          <label className="block space-y-1 text-sm">
            <span className="font-medium text-text-main">Program name *</span>
            <input
              {...register('name')}
              placeholder="e.g. Bachelor of Engineering (BEng)"
              className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
            />
            {errors.name ? <p className="text-sm text-alert">{errors.name.message}</p> : null}
          </label>

          <label className="block space-y-1 text-sm">
            <span className="font-medium text-text-main">Code</span>
            <input
              {...register('code')}
              placeholder="Optional — generated from the program name if blank"
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

          <Controller
            control={control}
            name="institution_id"
            render={({ field }) => (
              <SearchableSelect
                label="Institution (for intake assignment)"
                value={field.value ? String(field.value) : ''}
                options={[
                  { value: '', label: 'No institution — catalog only' },
                  ...institutionOptions,
                ]}
                onChange={value => field.onChange(value ? Number(value) : null)}
                placeholder={
                  institutionsQuery.isLoading ? 'Loading institutions...' : 'Select institution...'
                }
              />
            )}
          />

          {institutionId ? (
            <div className="space-y-2 rounded-xl border border-border-subtle bg-surface-bg/50 p-4">
              <div>
                <p className="text-sm font-semibold text-text-main">Assign Available Terms *</p>
                <p className="text-xs text-text-muted">
                  Select at least one Open intake when publishing this program.
                </p>
              </div>
              {openIntakesQuery.isLoading ? (
                <p className="text-sm text-text-muted">Loading open intakes...</p>
              ) : openIntakes.length === 0 ? (
                <p className="text-sm text-alert">
                  No Open intakes found for this institution. Configure the academic calendar first.
                </p>
              ) : (
                <div className="space-y-2">
                  {openIntakes.map(intake => (
                    <label
                      key={intake.id}
                      className="flex cursor-pointer items-start gap-3 rounded-lg border border-border-subtle bg-card px-3 py-2"
                    >
                      <input
                        type="checkbox"
                        checked={intakeIds.includes(intake.id)}
                        onChange={() => toggleIntake(intake.id)}
                        className="mt-1 rounded border-border-subtle"
                      />
                      <span>
                        <span className="block text-sm font-semibold text-text-main">
                          {intakeDisplayName(intake)}
                        </span>
                        <span className="text-xs text-text-muted">
                          {intake.term_name} · {intake.intake_type} · {intake.status}
                        </span>
                      </span>
                    </label>
                  ))}
                </div>
              )}
              {errors.intake_ids ? (
                <p className="text-sm text-alert">{errors.intake_ids.message}</p>
              ) : null}
            </div>
          ) : null}

          <ActiveStatusField
            entityType="program"
            entityId={degree?.id}
            value={isActive}
            initialValue={degree?.is_active ?? true}
            onChange={next => setValue('is_active', next)}
          />

          {errors.root ? <p className="text-sm text-alert">{errors.root.message}</p> : null}

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
              Save
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default DegreeFormModal;
