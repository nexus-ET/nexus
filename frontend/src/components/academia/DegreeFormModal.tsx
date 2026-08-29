import { useCallback, useEffect, useMemo } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Loader2, X } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';

import { apiFetch } from '../../utils/api';
import { fetchAcademiaListItems } from '../../utils/academiaList';
import { useAcademiaLevels } from '../../hooks/useLevels';
import { levelSelectOptions } from '../../constants/levels';
import { ACADEMIC_FRAMEWORK_LABELS } from '../../schemas/academicFrameworkHierarchy';
import {
  emptyProgramFormValues,
  programSchema,
  type ProgramFormValues,
} from '../../schemas/programSchema';
import type { DegreeRecord } from '../../types/academicFramework';
import type { CountryRecord } from '../../types/country';
import type { EducationMajorRecord, ProgramMajorMappingListResponse } from '../../types/educationMajor';
import type { EducationSubMajorRecord } from '../../types/educationSubMajor';
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
    formState: { errors, isSubmitting, dirtyFields },
    setError,
  } = useForm<ProgramFormValues>({
    resolver: zodResolver(programSchema),
    defaultValues: emptyProgramFormValues,
    mode: 'onSubmit',
  });

  const isActive = watch('is_active');
  const countryId = watch('country_id');
  const institutionId = watch('institution_id');
  const levelId = watch('level_id');
  const majorIds = watch('major_ids') ?? [];
  const subMajorIds = watch('sub_major_ids') ?? [];
  const programUrl = watch('program_url');

  const majorsQuery = useQuery({
    queryKey: ['academia-majors-for-program-form'],
    queryFn: () =>
      fetchAcademiaListItems<EducationMajorRecord>('academia/education-majors', {
        active_only: 'true',
        catalog_only: 'true',
      }),
    enabled: open,
  });

  const subMajorsQuery = useQuery({
    queryKey: ['academia-sub-majors-for-program-form'],
    queryFn: () => fetchAcademiaListItems<EducationSubMajorRecord>('academia/education-sub-majors'),
    enabled: open,
  });

  const programMajorMappingsQuery = useQuery({
    queryKey: ['academia-program-major-mappings-for-program-form', degree?.id],
    queryFn: () =>
      apiFetch<ProgramMajorMappingListResponse>('academia/program-major-mappings'),
    enabled: open && Boolean(degree?.id),
  });

  const countriesQuery = useQuery({
    queryKey: ['academia-countries-for-program-form'],
    queryFn: () =>
      fetchAcademiaListItems<CountryRecord>('academia/countries', {
        sort_by: 'name',
        sort_dir: 'asc',
      }),
    enabled: open,
  });

  const institutionsQuery = useQuery({
    queryKey: ['academia-institutions-for-program-form', countryId],
    queryFn: () => {
      const extra: Record<string, string | string[] | undefined> = {
        sort_by: 'name',
        sort_order: 'asc',
      };
      if (countryId) extra.country_id = String(countryId);
      return fetchAcademiaListItems<InstitutionRecord>('academia/institutions/summary', extra);
    },
    enabled: open && Boolean(countryId),
  });

  const countries = countriesQuery.data ?? [];
  const institutions = institutionsQuery.data ?? [];
  const majors = majorsQuery.data ?? [];
  const subMajors = subMajorsQuery.data ?? [];
  const majorColorByLabel = useMemo(() => buildMajorColorByLabel(majors), [majors]);
  const majorColorById = useMemo(() => buildMajorColorById(majors), [majors]);

  const countryOptions = useMemo(
    () => countries.map(item => ({ value: String(item.id), label: item.name })),
    [countries]
  );

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

  const selectedMajorIdSet = useMemo(
    () => new Set(majorIds.map(Number).filter(id => Number.isInteger(id) && id > 0)),
    [majorIds]
  );

  const subMajorOptions = useMemo(() => {
    const visible =
      selectedMajorIdSet.size === 0
        ? []
        : subMajors.filter(item => selectedMajorIdSet.has(Number(item.major_id)));
    return [...visible]
      .sort((left, right) =>
        left.name.localeCompare(right.name, undefined, { sensitivity: 'base' })
      )
      .map(item => {
        const parentId = Number(item.major_id);
        return {
          value: String(item.id),
          label:
            selectedMajorIdSet.size === 1 || !item.major_label
              ? item.name
              : `${item.name} (${item.major_label})`,
          color: resolveMajorColor(
            {
              id: parentId,
              label: item.major_label || '',
              color: item.major_color,
            },
            majorColorByLabel,
            majorColorById
          ),
        };
      });
  }, [majorColorById, majorColorByLabel, selectedMajorIdSet, subMajors]);

  const subMajorSelectedDisplay = useMemo(() => {
    if (subMajorIds.length === 0) return undefined;
    const labels = subMajorIds
      .map(id => subMajors.find(item => Number(item.id) === Number(id))?.name)
      .filter((label): label is string => Boolean(label));
    if (labels.length > 0) {
      return labels.length === 1 ? labels[0] : `${labels[0]} +${labels.length - 1} more`;
    }
    return `${subMajorIds.length} sub-major${subMajorIds.length === 1 ? '' : 's'} selected`;
  }, [subMajorIds, subMajors]);

  const majorSelectedDisplay = useMemo(() => {
    if (majorIds.length === 0) return undefined;
    const labels = majorIds
      .map(id => majors.find(major => Number(major.id) === Number(id))?.label)
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
      const resolvedSubMajorIds = [
        ...new Set(
          (record.sub_major_ids ?? [])
            .map(Number)
            .filter(id => Number.isInteger(id) && id > 0)
        ),
      ];
      reset({
        country_id: record.country_id ?? 0,
        level_id: record.level_id,
        major_ids: resolvedMajorIds,
        sub_major_ids: resolvedSubMajorIds,
        code: record.code || '',
        name: record.name || '',
        description: record.description || null,
        program_url: record.program_url || null,
        is_active: record.is_active ?? true,
        sort_order: record.sort_order ?? 0,
        institution_id: record.institution_id ?? record.institution_ids?.[0] ?? 0,
        college_id: record.college_id ?? null,
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

  useEffect(() => {
    if (!open || !countryId || !institutionId) return;
    const match = institutions.some(item => Number(item.id) === Number(institutionId));
    if (institutionsQuery.isLoading) return;
    if (institutions.length && !match) {
      setValue('institution_id', 0, { shouldDirty: true });
      setValue('intake_ids', []);
    }
  }, [countryId, institutionId, institutions, institutionsQuery.isLoading, open, setValue]);

  useEffect(() => {
    if (!open) return;
    // Do not drop hydrated sub-majors while majors are still loading on edit.
    if (degree && majorIds.length === 0) return;
    const allowedMajors = new Set(majorIds.map(Number));
    const current = (getValues('sub_major_ids') ?? []).map(Number);
    const next = current.filter(id => {
      const row = subMajors.find(item => Number(item.id) === Number(id));
      return Boolean(row && allowedMajors.has(Number(row.major_id)));
    });
    if (next.length === current.length) return;
    setValue('sub_major_ids', next, { shouldDirty: false });
  }, [degree, getValues, majorIds, open, setValue, subMajors]);

  if (!open) return null;

  const onSubmit = handleSubmit(async values => {
    try {
      const resolvedInstitutionId = [
        values.institution_id,
        degree?.institution_id,
        degree?.institution_ids?.[0],
      ]
        .map(Number)
        .find(id => Number.isInteger(id) && id > 0);
      const resolvedCountryId = [values.country_id, degree?.country_id]
        .map(Number)
        .find(id => Number.isInteger(id) && id > 0);
      if (!resolvedInstitutionId) {
        setError('institution_id', { message: 'Institution is required' });
        return;
      }
      const resolvedMajorIds = [
        ...new Set(
          (values.major_ids ?? getValues('major_ids') ?? [])
            .map(Number)
            .filter(id => Number.isInteger(id) && id > 0)
        ),
      ];
      const resolvedSubMajorIds = [
        ...new Set(
          (values.sub_major_ids ?? getValues('sub_major_ids') ?? [])
            .map(Number)
            .filter(id => Number.isInteger(id) && id > 0)
        ),
      ];
      const identity = {
        name: values.name.trim(),
        code: values.code?.trim() ? values.code.trim().toUpperCase() : null,
        description: values.description?.trim() || null,
        program_url: values.program_url?.trim() || null,
        level_id: values.level_id,
      };
      const payload: Record<string, unknown> = {
        major_ids: resolvedMajorIds,
        sub_major_ids: resolvedSubMajorIds,
        is_active: values.is_active,
        sort_order: values.sort_order ?? 0,
        country_id: resolvedCountryId ?? null,
        institution_id: resolvedInstitutionId,
        college_id: values.college_id ?? null,
        intake_ids: values.intake_ids ?? [],
      };
      if (degree) {
        const nameChanged = identity.name !== (degree.name || '').trim();
        const levelChanged = Number(values.level_id) !== Number(degree.level_id);
        if (nameChanged) payload.name = identity.name;
        if (levelChanged) payload.level_id = identity.level_id;
        if (identity.code && identity.code !== (degree.code || '')) payload.code = identity.code;
        if (dirtyFields.description) payload.description = identity.description;
        if (dirtyFields.program_url) payload.program_url = identity.program_url;
        await apiFetch(`academia/degrees/${degree.id}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        });
      } else {
        await apiFetch('academia/degrees', {
          method: 'POST',
          body: JSON.stringify({ ...payload, ...identity }),
        });
      }
      onSaved();
      onClose();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to save program';
      if (!degree && message.includes('already exists for the selected level')) {
        setError('name', { message });
      } else {
        setError('root', { message });
      }
    }
  });

  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="max-h-[90vh] w-full max-w-6xl overflow-y-auto rounded-2xl border border-border-subtle bg-card shadow-2xl">
        <div className="flex items-center justify-between border-b border-border-subtle px-5 py-4">
          <div>
            <h3 className="text-lg font-bold text-text-main">
              {degree ? 'Edit Program' : 'Create Program'}
            </h3>
            <p className="text-xs text-text-muted">
              Level → Country → Institution → Major → Program
            </p>
          </div>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-text-muted hover:bg-surface-bg">
            <X size={18} />
          </button>
        </div>
        <form onSubmit={onSubmit} noValidate className="grid grid-cols-1 gap-x-3 gap-y-2.5 p-5 md:grid-cols-3">
          <div>
            <Controller
              control={control}
              name="country_id"
              render={({ field }) => (
                <SearchableSelect
                  label="Country"
                  value={field.value ? String(field.value) : ''}
                  options={countryOptions}
                  onChange={value => field.onChange(value ? Number(value) : 0)}
                  placeholder={
                    countriesQuery.isLoading ? 'Loading countries...' : 'Select country...'
                  }
                  required
                />
              )}
            />
            {errors.country_id ? <p className="text-sm text-alert">{errors.country_id.message}</p> : null}
          </div>

          <div>
            <Controller
              control={control}
              name="institution_id"
              render={({ field }) => (
                <SearchableSelect
                  label="Institution"
                  value={field.value ? String(field.value) : ''}
                  options={institutionOptions}
                  onChange={value => field.onChange(value ? Number(value) : 0)}
                  placeholder={
                    !countryId
                      ? 'Select a country first'
                      : institutionsQuery.isLoading
                        ? 'Loading institutions...'
                        : institutionOptions.length === 0
                          ? 'No institutions for this country'
                          : 'Select institution...'
                  }
                  disabled={!countryId || institutionsQuery.isLoading}
                  required
                />
              )}
            />
            {errors.institution_id ? (
              <p className="text-sm text-alert">{errors.institution_id.message}</p>
            ) : null}
          </div>

          <div>
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
          </div>

          <div>
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
                  preferDropUp
                />
              )}
            />
            {errors.major_ids ? <p className="text-sm text-alert">{errors.major_ids.message}</p> : null}
          </div>

          <div>
            <Controller
              control={control}
              name="sub_major_ids"
              render={({ field }) => (
                <SearchableMultiSelect
                  label={ACADEMIC_FRAMEWORK_LABELS.subMajor}
                  values={(field.value ?? []).map(String)}
                  options={subMajorOptions}
                  onChange={values =>
                    field.onChange(
                      values
                        .map(Number)
                        .filter(id => Number.isInteger(id) && id > 0)
                    )
                  }
                  placeholder={
                    majorIds.length === 0
                      ? 'Select a major first'
                      : subMajorsQuery.isLoading
                        ? 'Loading sub-majors...'
                        : subMajorOptions.length === 0
                          ? 'No sub-majors for selected majors'
                          : 'Select one or more sub-majors'
                  }
                  disabled={majorIds.length === 0 || subMajorsQuery.isLoading}
                  hint="Optional. Select any number of sub-majors under the chosen majors."
                  selectedDisplay={
                    subMajorIds.length > 1
                      ? `${subMajorIds.length} selected`
                      : subMajorSelectedDisplay
                  }
                  preferDropUp
                />
              )}
            />
            {errors.sub_major_ids ? (
              <p className="text-sm text-alert">{errors.sub_major_ids.message}</p>
            ) : null}
          </div>

          <label className="block space-y-1 text-sm">
            <span className="flex items-center justify-between gap-2 font-medium text-text-main">
              <span>Program URL</span>
              {programUrl && /^https?:\/\//i.test(programUrl) ? (
                <a
                  href={programUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs font-medium text-accent hover:underline"
                >
                  View Website
                </a>
              ) : null}
            </span>
            <input
              {...register('program_url')}
              type="url"
              placeholder="https://..."
              className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
            />
            {errors.program_url ? (
              <p className="text-sm text-alert">{errors.program_url.message}</p>
            ) : null}
          </label>

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

          <ActiveStatusField
            entityType="program"
            entityId={degree?.id}
            value={isActive}
            initialValue={degree?.is_active ?? true}
            onChange={next => setValue('is_active', next)}
          />

          <div className="md:col-span-3">
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
          </div>

          {errors.root ? <p className="text-sm text-alert md:col-span-3">{errors.root.message}</p> : null}

          <div className="flex justify-end gap-3 pt-2 md:col-span-3">
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
