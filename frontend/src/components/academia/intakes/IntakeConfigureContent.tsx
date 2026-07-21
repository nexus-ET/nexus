import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from 'react';
import { RotateCcw, Search, Trash2, X } from 'lucide-react';

import { apiFetch } from '../../../utils/api';
import type { GlobalAcademicTemplate, InstitutionIntakeRecord } from '../../../types/academicCalendar';
import type { LevelRecord } from '../../../types/level';
import type {
  IntakeConfigurePayload,
  IntakeDateValidationResult,
  IntakeDateFormValues,
  IntakeEntityType,
  IntakeTimelineDateField,
} from '../../../types/hierarchicalIntake';
import { validateIntakeTimeline } from '../../../types/hierarchicalIntake';
import { serializeWizardSnapshot } from '../wizard/form/wizardDirtyTracking';
import { useConfirmation } from '../../../context/ConfirmationContext';
import EmptyListMessage from '../../ui/EmptyListMessage';
import HeadlessScrollArea from '../../HeadlessScrollArea';
import {
  buildFormsForSchedule,
  distinctLevelGroups,
  distinctTemplateIdsForYear,
  groupFormsByLevelKey,
  inferDateScheduleMode,
  intakesBlockingLevelGroups,
  intakesForOtherTemplateOverlappingLevels,
  levelIdsLabel,
  matchCreatedIntakeRow,
  preferredDateScheduleMode,
  sameLevelIds,
  sortLevelGroupsByLevelsOrder,
  templateStructureType,
  type IntakeDateScheduleMode,
} from './intakeCalendarGroups';

export interface IntakeConfigureContentProps {
  institutionId: number;
  entityType: IntakeEntityType;
  entityId: number;
  onUpdated?: () => void;
  onClose?: () => void;
  onDirtyChange?: (dirty: boolean) => void;
  onValidationChange?: (hasConflicts: boolean) => void;
  markCleanRef?: React.MutableRefObject<(() => void) | null>;
}

export interface IntakeConfigureContentHandle {
  /** Returns null on success, or an error message on failure. */
  saveAll: () => Promise<string | null>;
}

const TIMELINE_FIELDS: IntakeTimelineDateField[] = [
  'application_deadline',
  'orientation_date',
  'check_in_date',
  'class_start_date',
];

const hasAnyTimelineDate = (form: IntakeDateFormValues): boolean =>
  TIMELINE_FIELDS.some(field => Boolean(form[field]));

const hasCompleteTimeline = (form: IntakeDateFormValues): boolean =>
  TIMELINE_FIELDS.every(field => Boolean(form[field]));

function formStatusLabel(form: IntakeDateFormValues): string {
  if (form.is_pending) return 'Draft';
  if (form.is_overridden) return 'Custom';
  if (form.parent_intake_id) return 'Inherited';
  return 'Configured';
}

function IntakeTermsBrowser({
  forms,
  templates,
  levels,
  dateValidationById,
  saving,
  deletingIntakeId,
  overrideUnlockedIds,
  onUpdateField,
  onUnlockOverride,
  onResetToParent,
  onDelete,
}: {
  forms: IntakeDateFormValues[];
  templates: GlobalAcademicTemplate[];
  levels: LevelRecord[];
  dateValidationById: Map<number, IntakeDateValidationResult>;
  saving: boolean;
  deletingIntakeId: number | null;
  overrideUnlockedIds: Set<number>;
  onUpdateField: (id: number, field: keyof IntakeDateFormValues, value: string) => void;
  onUnlockOverride: (id: number) => void;
  onResetToParent: (id: number) => void;
  onDelete: (form: IntakeDateFormValues) => void;
}) {
  const calendars = useMemo(() => {
    return sortLevelGroupsByLevelsOrder(groupFormsByLevelKey(forms), levels).map(section => {
      const sample = section.forms[0];
      const template = templates.find(item => item.id === sample?.template_id);
      const years = [...new Set(section.forms.map(form => form.year).filter(Boolean))]
        .map(Number)
        .sort((a, b) => b - a);
      return {
        key: section.key || 'none',
        levelIds: section.levelIds,
        label: levelIdsLabel(section.levelIds, levels),
        templateName: template?.name || 'Not assigned',
        calendarSystem: templateStructureType(template),
        years,
        forms: section.forms,
      };
    });
  }, [forms, levels, templates]);

  const [activeCalendarKey, setActiveCalendarKey] = useState<string>('');
  const [yearFilter, setYearFilter] = useState<string>('all');
  const [query, setQuery] = useState('');
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const normalizedQuery = query.trim().toLowerCase();

  useEffect(() => {
    if (calendars.length === 0) {
      setActiveCalendarKey('');
      return;
    }
    if (!calendars.some(calendar => calendar.key === activeCalendarKey)) {
      setActiveCalendarKey(calendars[0].key);
      setYearFilter('all');
    }
  }, [activeCalendarKey, calendars]);

  const activeCalendar = calendars.find(calendar => calendar.key === activeCalendarKey) || null;

  useEffect(() => {
    setYearFilter('all');
    setQuery('');
  }, [activeCalendarKey]);

  const visibleForms = useMemo(() => {
    const source = activeCalendar?.forms || [];
    return source
      .filter(form => {
        const yearValue = form.year ? String(form.year) : 'No year';
        if (yearFilter !== 'all' && yearValue !== yearFilter) return false;
        if (!normalizedQuery) return true;
        const template = templates.find(item => item.id === form.template_id);
        const haystack = [
          form.name,
          form.term_name,
          form.year,
          template?.name,
          templateStructureType(template),
          formStatusLabel(form),
        ]
          .join(' ')
          .toLowerCase();
        return haystack.includes(normalizedQuery);
      })
      .sort((a, b) => {
        const yearCmp = String(b.year || '').localeCompare(String(a.year || ''), undefined, {
          numeric: true,
        });
        if (yearCmp !== 0) return yearCmp;
        return (a.term_name || a.name).localeCompare(b.term_name || b.name);
      });
  }, [activeCalendar, normalizedQuery, templates, yearFilter]);

  const formsByYear = useMemo(() => {
    const sections: Array<{ year: string; items: IntakeDateFormValues[] }> = [];
    const indexByYear = new Map<string, number>();
    for (const form of visibleForms) {
      const year = form.year ? String(form.year) : 'No year';
      let index = indexByYear.get(year);
      if (index === undefined) {
        index = sections.length;
        indexByYear.set(year, index);
        sections.push({ year, items: [] });
      }
      sections[index].items.push(form);
    }
    return sections;
  }, [visibleForms]);

  useEffect(() => {
    if (visibleForms.length === 0) {
      setSelectedId(null);
      return;
    }
    if (selectedId === null || !visibleForms.some(form => form.id === selectedId)) {
      setSelectedId(visibleForms[0].id);
    }
  }, [selectedId, visibleForms]);

  const selectedForm = visibleForms.find(form => form.id === selectedId) || null;

  const renderTermEditor = (form: IntakeDateFormValues) => {
    const validation = dateValidationById.get(form.id);
    const appliedTemplateName =
      templates.find(template => template.id === form.template_id)?.name || 'Not assigned';
    const hasAnyDates = hasAnyTimelineDate(form);
    const isIncomplete = !hasCompleteTimeline(form);
    const isInherited =
      Boolean(form.parent_intake_id) && !form.is_overridden && !form.is_pending;
    const datesLocked = isInherited && !overrideUnlockedIds.has(form.id);
    const hasConflict = (field: IntakeTimelineDateField) =>
      hasAnyDates && (validation?.conflictingFields.includes(field) ?? false);
    const dateInputClass = (field: IntakeTimelineDateField) =>
      `mt-1 w-full rounded-xl border px-3 py-2 text-sm outline-none ${
        datesLocked
          ? 'border-border-subtle bg-surface-bg text-text-muted'
          : hasConflict(field)
            ? 'border-alert/60 bg-alert/5 focus:border-alert'
            : 'border-border-subtle focus:border-accent'
      }`;

    return (
      <div className="space-y-3 p-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
              {levelIdsLabel(form.level_ids || [], levels)} · {appliedTemplateName}
            </p>
            <h4 className="mt-1 truncate font-semibold text-text-main">{form.name}</h4>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                form.is_pending
                  ? 'bg-sky-100 text-sky-800'
                  : form.is_overridden
                    ? 'bg-amber-100 text-amber-800'
                    : isInherited
                      ? 'bg-slate-100 text-slate-700'
                      : 'bg-emerald-100 text-emerald-800'
              }`}
            >
              {formStatusLabel(form)}
            </span>
            {!form.is_pending ? (
              <button
                type="button"
                disabled={saving || deletingIntakeId !== null}
                onClick={() => onDelete(form)}
                className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-alert hover:bg-alert/10 disabled:opacity-50"
                aria-label={`Delete ${form.term_name || form.name} intake calendar`}
              >
                <Trash2 size={14} />
                {deletingIntakeId === form.id ? 'Deleting...' : 'Delete'}
              </button>
            ) : null}
          </div>
        </div>
        {isInherited ? (
          <p className="text-xs text-text-muted">
            {datesLocked
              ? 'These dates were cascaded from a parent calendar. Use Override to set college-specific dates.'
              : 'Override mode is on. Change the dates below and save to keep a custom calendar. Future parent cascades will skip this term.'}
          </p>
        ) : null}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label className="text-xs font-medium text-text-muted">1. Application deadline *</label>
            <input
              type="date"
              value={form.application_deadline}
              disabled={saving || datesLocked}
              onChange={e => onUpdateField(form.id, 'application_deadline', e.target.value)}
              className={dateInputClass('application_deadline')}
            />
          </div>
          <div>
            <label className="text-xs font-medium text-text-muted">2. Orientation date *</label>
            <input
              type="date"
              value={form.orientation_date}
              disabled={saving || datesLocked}
              onChange={e => onUpdateField(form.id, 'orientation_date', e.target.value)}
              className={dateInputClass('orientation_date')}
            />
          </div>
          <div>
            <label className="text-xs font-medium text-text-muted">3. Check-in date *</label>
            <input
              type="date"
              value={form.check_in_date}
              disabled={saving || datesLocked}
              onChange={e => onUpdateField(form.id, 'check_in_date', e.target.value)}
              className={dateInputClass('check_in_date')}
            />
          </div>
          <div>
            <label className="text-xs font-medium text-text-muted">4. Class start date *</label>
            <input
              type="date"
              value={form.class_start_date}
              disabled={saving || datesLocked}
              onChange={e => onUpdateField(form.id, 'class_start_date', e.target.value)}
              className={dateInputClass('class_start_date')}
            />
          </div>
        </div>
        {isIncomplete ? (
          <div
            role="alert"
            className="rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800"
          >
            Date inputs are incomplete for {form.term_name || form.name}. This setup will not be
            saved.
          </div>
        ) : validation && validation.messages.length > 0 ? (
          <div
            role="alert"
            className="rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800"
          >
            {validation.messages.map(message => (
              <p key={message}>{message}</p>
            ))}
          </div>
        ) : null}
        {datesLocked ? (
          <button
            type="button"
            disabled={saving}
            onClick={() => onUnlockOverride(form.id)}
            className="inline-flex items-center gap-1 rounded-xl border border-border-subtle px-3 py-2 text-sm font-semibold text-text-main disabled:opacity-50"
          >
            Override dates
          </button>
        ) : null}
        {form.is_overridden && form.parent_intake_id ? (
          <button
            type="button"
            disabled={saving}
            onClick={() => onResetToParent(form.id)}
            className="inline-flex items-center gap-1 rounded-xl border border-border-subtle px-3 py-2 text-sm font-semibold text-text-main disabled:opacity-50"
          >
            <RotateCcw size={14} />
            Reset to parent template
          </button>
        ) : null}
      </div>
    );
  };

  if (forms.length === 0) {
    return (
      <EmptyListMessage message="No intake terms to browse yet. Choose levels and a template above." />
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-border-subtle bg-surface-bg/30">
      <div className="space-y-3 border-b border-border-subtle px-3 py-3">
        <div>
          <p className="text-sm font-semibold text-text-main">Edit term dates</p>
          <p className="mt-0.5 text-xs text-text-muted">
            Pick a level calendar, then open a term (Fall, Spring, …) to set dates.
          </p>
        </div>

        {calendars.length > 1 ? (
          <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Level calendars">
            {calendars.map(calendar => {
              const active = calendar.key === activeCalendarKey;
              return (
                <button
                  key={calendar.key}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  onClick={() => setActiveCalendarKey(calendar.key)}
                  className={`rounded-xl px-3 py-2 text-left text-sm transition-colors ${
                    active
                      ? 'bg-accent/15 font-semibold text-accent ring-1 ring-accent/30'
                      : 'bg-card text-text-main hover:bg-accent/5'
                  }`}
                >
                  <span className="block">{calendar.label}</span>
                  <span className="mt-0.5 block text-[11px] font-normal text-text-muted">
                    {calendar.calendarSystem}
                    {calendar.years[0] ? ` · ${calendar.years[0]}` : ''}
                    {` · ${calendar.forms.length} term${calendar.forms.length === 1 ? '' : 's'}`}
                  </span>
                </button>
              );
            })}
          </div>
        ) : activeCalendar ? (
          <div className="rounded-xl border border-border-subtle bg-card px-3 py-2">
            <p className="text-sm font-semibold text-text-main">{activeCalendar.label}</p>
            <p className="text-xs text-text-muted">
              {activeCalendar.calendarSystem} · {activeCalendar.templateName}
            </p>
          </div>
        ) : null}

        <div className="flex flex-wrap items-center gap-2">
          <label className="relative min-w-[180px] flex-1">
            <Search
              size={14}
              className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted"
            />
            <input
              type="search"
              value={query}
              onChange={event => setQuery(event.target.value)}
              placeholder="Search Fall, Spring…"
              className="w-full rounded-lg border border-border-subtle bg-card py-1.5 pl-8 pr-3 text-sm outline-none focus:border-accent"
            />
          </label>
          {(activeCalendar?.years.length || 0) > 1 ? (
            <label className="flex items-center gap-2 text-xs text-text-muted">
              Year
              <select
                value={yearFilter}
                onChange={event => setYearFilter(event.target.value)}
                className="rounded-lg border border-border-subtle bg-card px-2.5 py-1.5 text-sm text-text-main"
              >
                <option value="all">All years</option>
                {activeCalendar?.years.map(year => (
                  <option key={year} value={String(year)}>
                    {year}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
        </div>
      </div>

      {visibleForms.length === 0 ? (
        <div className="px-3 py-6">
          <EmptyListMessage message="No terms in this calendar match your search." />
        </div>
      ) : (
        <div className="grid h-[24rem] grid-cols-1 md:grid-cols-[minmax(0,0.9fr)_minmax(0,1.2fr)]">
          <HeadlessScrollArea className="h-full border-b border-border-subtle md:border-b-0 md:border-r">
            <div className="pb-2">
              {formsByYear.map(section => (
                <div key={section.year}>
                  {formsByYear.length > 1 ? (
                    <div className="sticky top-0 z-10 border-b border-border-subtle bg-surface-bg/95 px-3 py-1.5 backdrop-blur-sm">
                      <p className="text-[11px] font-bold uppercase tracking-wide text-text-muted">
                        {section.year}
                      </p>
                    </div>
                  ) : null}
                  <ul>
                    {section.items.map(form => {
                      const isSelected = form.id === selectedId;
                      const incomplete = !hasCompleteTimeline(form);
                      return (
                        <li key={form.id}>
                          <button
                            type="button"
                            onClick={() => setSelectedId(form.id)}
                            className={`flex w-full items-start gap-2 px-3 py-2.5 text-left transition-colors ${
                              isSelected ? 'bg-accent/10' : 'hover:bg-card/80'
                            }`}
                          >
                            <div className="min-w-0 flex-1">
                              <p className="truncate text-sm font-semibold text-text-main">
                                {form.term_name || form.name}
                              </p>
                              <p className="truncate text-xs text-text-muted">
                                {formStatusLabel(form)}
                                {incomplete ? ' · Needs dates' : ''}
                              </p>
                            </div>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ))}
            </div>
          </HeadlessScrollArea>

          <div className="flex h-full min-h-0 flex-col overflow-hidden bg-card/40">
            {selectedForm ? (
              <HeadlessScrollArea className="min-h-0 flex-1">
                {renderTermEditor(selectedForm)}
              </HeadlessScrollArea>
            ) : (
              <p className="px-3 py-6 text-sm text-text-muted">Select a term to edit dates.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

const IntakeConfigureContent = forwardRef<
  IntakeConfigureContentHandle,
  IntakeConfigureContentProps
>(({
    institutionId,
    entityType,
    entityId,
    onUpdated,
    onClose,
    onDirtyChange,
    onValidationChange,
    markCleanRef,
  }, ref) => {
  const openConfirm = useConfirmation();
  const [templates, setTemplates] = useState<GlobalAcademicTemplate[]>([]);
  const [levels, setLevels] = useState<LevelRecord[]>([]);
  const [savedIntakes, setSavedIntakes] = useState<InstitutionIntakeRecord[]>([]);
  const [templateId, setTemplateId] = useState<number | ''>('');
  const [selectedLevelIds, setSelectedLevelIds] = useState<number[]>([]);
  const [dateScheduleMode, setDateScheduleMode] = useState<IntakeDateScheduleMode>('shared');
  const [year, setYear] = useState(new Date().getFullYear());
  const [cascade, setCascade] = useState(false);
  const [overrideUnlockedIds, setOverrideUnlockedIds] = useState<Set<number>>(
    () => new Set()
  );
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deletingIntakeId, setDeletingIntakeId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const errorRef = useRef<string | null>(null);
  const setPanelError = useCallback((message: string | null) => {
    errorRef.current = message;
    setError(message);
  }, []);
  const [forms, setForms] = useState<IntakeDateFormValues[]>([]);
  const [loadVersion, setLoadVersion] = useState(0);
  const baselineRef = useRef('');
  const hydratingRef = useRef(true);
  const loadRequestRef = useRef(0);
  const templateIdRef = useRef<number | ''>(templateId);
  templateIdRef.current = templateId;

  const dateValidationById = useMemo(
    () =>
      new Map<number, IntakeDateValidationResult>(
        forms.map(form => [form.id, validateIntakeTimeline(form)])
      ),
    [forms]
  );
  const saveableForms = useMemo(
    () =>
      forms.filter(
        form =>
          hasCompleteTimeline(form) &&
          (dateValidationById.get(form.id)?.messages.length || 0) === 0
      ),
    [dateValidationById, forms]
  );
  const incompleteForms = useMemo(
    () => forms.filter(form => !hasCompleteTimeline(form)),
    [forms]
  );
  const hasEnteredDateConflicts = forms.some(
    form =>
      hasAnyTimelineDate(form) &&
      (dateValidationById.get(form.id)?.messages.length || 0) > 0
  );
  const hasLevelConflict =
    forms.length > 0 &&
    (selectedLevelIds.length === 0 || forms.some(form => (form.level_ids || []).length === 0));
  const hasValidationConflicts = hasEnteredDateConflicts || hasLevelConflict;
  const hasPendingForms = forms.some(form => form.is_pending);
  const calendarGroupCount = useMemo(
    () => groupFormsByLevelKey(forms).length,
    [forms]
  );
  const templatesInSelectedYear = useMemo(
    () => distinctTemplateIdsForYear(savedIntakes, year),
    [savedIntakes, year]
  );
  const existingTemplateForYear = useMemo(() => {
    if (templatesInSelectedYear.length === 0) return null;
    const preferred =
      (templateId && templatesInSelectedYear.includes(Number(templateId))
        ? Number(templateId)
        : templatesInSelectedYear[0]) || null;
    if (!preferred) return null;
    return templates.find(item => item.id === preferred) || null;
  }, [templateId, templates, templatesInSelectedYear]);
  const yearTemplateConflict = useMemo(() => {
    if (!templateId) return [] as InstitutionIntakeRecord[];
    return intakesForOtherTemplateOverlappingLevels({
      intakes: savedIntakes,
      year,
      templateId,
      levelIds: selectedLevelIds,
    });
  }, [savedIntakes, selectedLevelIds, templateId, year]);
  const mixedTemplatesForYear = templatesInSelectedYear.length > 1;

  useEffect(() => {
    onValidationChange?.(hasValidationConflicts);
  }, [hasValidationConflicts, onValidationChange]);

  const rebuildForms = useCallback(
    (options: {
      nextTemplateId?: number | '';
      nextMode?: IntakeDateScheduleMode;
      nextLevelIds?: number[];
      nextYear?: number;
      nextTemplates?: GlobalAcademicTemplate[];
      nextSaved?: InstitutionIntakeRecord[];
    } = {}) => {
      const nextTemplateId = options.nextTemplateId ?? templateId;
      const nextMode = options.nextMode ?? dateScheduleMode;
      const nextLevelIds = options.nextLevelIds ?? selectedLevelIds;
      const nextYear = options.nextYear ?? year;
      const nextTemplates = options.nextTemplates ?? templates;
      const nextSaved = options.nextSaved ?? savedIntakes;
      return buildFormsForSchedule({
        templateId: nextTemplateId,
        year: nextYear,
        templates: nextTemplates,
        savedIntakes: nextSaved,
        mode: nextMode,
        selectedLevelIds: nextLevelIds,
        levels,
      });
    },
    [dateScheduleMode, levels, savedIntakes, selectedLevelIds, templateId, templates, year]
  );

  const getDirtySnapshot = useCallback(
    () => ({
      forms,
      templateId,
      selectedLevelIds,
      dateScheduleMode,
      year,
      cascade,
    }),
    [cascade, dateScheduleMode, forms, selectedLevelIds, templateId, year]
  );

  useEffect(() => {
    if (markCleanRef) {
      markCleanRef.current = () => {
        baselineRef.current = serializeWizardSnapshot(getDirtySnapshot());
        hydratingRef.current = false;
        onDirtyChange?.(false);
      };
    }
    return () => {
      if (markCleanRef) {
        markCleanRef.current = null;
      }
    };
  }, [getDirtySnapshot, markCleanRef, onDirtyChange]);

  useEffect(() => {
    return () => {
      onDirtyChange?.(false);
    };
  }, [onDirtyChange]);

  useEffect(() => {
    if (loading) {
      hydratingRef.current = true;
      return;
    }
    hydratingRef.current = true;
    const captureBaseline = () => {
      baselineRef.current = serializeWizardSnapshot(getDirtySnapshot());
      onDirtyChange?.(false);
    };
    captureBaseline();
    // Re-baseline after paint so post-load form sync (tabs/sort) does not look like edits.
    const frameId = window.requestAnimationFrame(() => {
      captureBaseline();
      hydratingRef.current = false;
    });
    return () => window.cancelAnimationFrame(frameId);
  }, [getDirtySnapshot, loadVersion, loading, onDirtyChange]);

  useEffect(() => {
    if (loading || hydratingRef.current || !baselineRef.current) return;
    const dirty = serializeWizardSnapshot(getDirtySnapshot()) !== baselineRef.current;
    onDirtyChange?.(dirty);
  }, [getDirtySnapshot, loading, onDirtyChange]);

  const loadData = useCallback(async () => {
    const requestId = ++loadRequestRef.current;
    setLoading(true);
    setPanelError(null);
    try {
      const [templateRows, levelRows, intakeRows] = await Promise.all([
        apiFetch<GlobalAcademicTemplate[]>('academia/academic-templates'),
        apiFetch<LevelRecord[]>('academia/levels'),
        apiFetch<InstitutionIntakeRecord[]>(
          `academia/institutions/${institutionId}/intakes/by-entity?entity_type=${entityType}&entity_id=${entityId}&year=${year}`
        ),
      ]);
      if (requestId !== loadRequestRef.current) return;
      const nextTemplates = Array.isArray(templateRows) ? templateRows : [];
      const nextLevels = Array.isArray(levelRows) ? levelRows : [];
      const nextIntakes = Array.isArray(intakeRows) ? intakeRows : [];
      setTemplates(nextTemplates);
      setLevels(nextLevels);
      setSavedIntakes(nextIntakes);
      const yearTemplateIds = distinctTemplateIdsForYear(nextIntakes, year);
      let activeTemplateId = templateIdRef.current;
      if (
        (!activeTemplateId || !yearTemplateIds.includes(Number(activeTemplateId))) &&
        yearTemplateIds.length === 1
      ) {
        activeTemplateId = yearTemplateIds[0];
        setTemplateId(activeTemplateId);
        templateIdRef.current = activeTemplateId;
      }
      const matchingIntakes = activeTemplateId
        ? nextIntakes.filter(row => Number(row.template_id) === Number(activeTemplateId))
        : nextIntakes;
      const levelGroups = distinctLevelGroups(matchingIntakes);
      const nextLevelIds =
        levelGroups.length > 0
          ? [...new Set(levelGroups.flat())].sort((a, b) => a - b)
          : [];
      const nextMode = inferDateScheduleMode(levelGroups);
      setSelectedLevelIds(nextLevelIds);
      setDateScheduleMode(nextMode);
      setCascade(matchingIntakes.some(row => Boolean(row.cascade_to_children)));
      setOverrideUnlockedIds(new Set());
      setForms(
        buildFormsForSchedule({
          templateId: activeTemplateId,
          year,
          templates: nextTemplates,
          savedIntakes: nextIntakes,
          mode: nextMode,
          selectedLevelIds: nextLevelIds,
          levels: nextLevels,
        })
      );
    } catch (err) {
      if (requestId !== loadRequestRef.current) return;
      setPanelError(err instanceof Error ? err.message : 'Failed to load intake configuration.');
    } finally {
      if (requestId === loadRequestRef.current) {
        setLoading(false);
        setLoadVersion(version => version + 1);
      }
    }
  }, [entityId, entityType, institutionId, year]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const applyTemplateSelection = useCallback(
    (nextTemplateId: number | '', nextSaved: InstitutionIntakeRecord[] = savedIntakes) => {
      setTemplateId(nextTemplateId);
      templateIdRef.current = nextTemplateId;
      setPanelError(null);
      const matchingIntakes = nextTemplateId
        ? nextSaved.filter(row => Number(row.template_id) === Number(nextTemplateId))
        : nextSaved;
      const levelGroups = distinctLevelGroups(matchingIntakes);
      const seededLevels =
        selectedLevelIds.length > 0
          ? selectedLevelIds
          : levelGroups.length > 0
            ? [...new Set(levelGroups.flat())].sort((a, b) => a - b)
            : [];
      const nextMode =
        levelGroups.length > 1 ? inferDateScheduleMode(levelGroups) : dateScheduleMode;
      setSelectedLevelIds(seededLevels);
      setDateScheduleMode(nextMode);
      setCascade(matchingIntakes.some(row => Boolean(row.cascade_to_children)));
      setOverrideUnlockedIds(new Set());
      setForms(
        buildFormsForSchedule({
          templateId: nextTemplateId,
          year,
          templates,
          savedIntakes: nextSaved,
          mode: nextMode,
          selectedLevelIds: seededLevels,
          levels,
        })
      );
    },
    [dateScheduleMode, levels, savedIntakes, selectedLevelIds, templates, year]
  );

  const deleteIntakesForYearTemplates = useCallback(
    async (intakeRows: InstitutionIntakeRecord[]) => {
      for (const row of intakeRows) {
        if (!row?.id) continue;
        await apiFetch(`academia/institutions/${institutionId}/intakes/${row.id}`, {
          method: 'DELETE',
        });
      }
    },
    [institutionId]
  );

  const handleTemplateChange = async (nextTemplateId: number | '') => {
    if (nextTemplateId === templateId) return;

    if (nextTemplateId) {
      const conflicting = intakesForOtherTemplateOverlappingLevels({
        intakes: savedIntakes,
        year,
        templateId: nextTemplateId,
        levelIds: selectedLevelIds,
      });
      if (conflicting.length > 0) {
        const existingIds = distinctTemplateIdsForYear(conflicting, year);
        const existingNames = existingIds
          .map(id => templates.find(item => item.id === id)?.name || `Template #${id}`)
          .join(', ');
        const nextName =
          templates.find(item => item.id === nextTemplateId)?.name || 'the selected template';
        const levelLabel = levelIdsLabel(selectedLevelIds, levels);
        const confirmed = await openConfirm({
          title: `Replace calendar for ${levelLabel}?`,
          message: [
            `${levelLabel} already uses ${existingNames} for ${year}.`,
            '',
            'The same level cannot use two calendar systems in one year.',
            '',
            `Replace those level calendar(s) with "${nextName}"?`,
            'Calendars for other levels in this year will be kept.',
          ].join('\n'),
          confirmLabel: 'Replace level calendar',
          variant: 'danger',
        });
        if (!confirmed) return;

        setSaving(true);
        setPanelError(null);
        try {
          await deleteIntakesForYearTemplates(conflicting);
          const refreshed = await apiFetch<InstitutionIntakeRecord[]>(
            `academia/institutions/${institutionId}/intakes/by-entity?entity_type=${entityType}&entity_id=${entityId}&year=${year}`
          );
          const nextSaved = Array.isArray(refreshed) ? refreshed : [];
          setSavedIntakes(nextSaved);
          applyTemplateSelection(nextTemplateId, nextSaved);
          onUpdated?.();
        } catch (err) {
          setPanelError(
            err instanceof Error ? err.message : 'Failed to replace the existing level calendar.'
          );
        } finally {
          setSaving(false);
        }
        return;
      }
    }

    applyTemplateSelection(nextTemplateId);
  };

  const handleLevelIdsChange = (nextLevelIds: number[]) => {
    setSelectedLevelIds(nextLevelIds);
    setPanelError(null);
    const matchingForYear = templateId
      ? savedIntakes.filter(
          row =>
            Number(row.template_id) === Number(templateId) && Number(row.year) === Number(year)
        )
      : [];
    const nextMode = preferredDateScheduleMode({
      selectedLevelIds: nextLevelIds,
      existingLevelGroups: distinctLevelGroups(matchingForYear),
      requestedMode: dateScheduleMode,
    });
    setDateScheduleMode(nextMode);
    setForms(
      rebuildForms({
        nextLevelIds,
        nextMode,
      })
    );
  };

  const handleDateScheduleModeChange = (nextMode: IntakeDateScheduleMode) => {
    if (nextMode === 'shared' && templateId) {
      const matchingForYear = savedIntakes.filter(
        row =>
          Number(row.template_id) === Number(templateId) && Number(row.year) === Number(year)
      );
      const existingGroups = distinctLevelGroups(matchingForYear);
      const selected = [...selectedLevelIds].filter(id => id > 0);
      const wouldReplaceSeparateCalendars = existingGroups.some(group => {
        const groupSet = new Set(group);
        const overlap = selected.some(id => groupSet.has(id));
        return overlap && !sameLevelIds(group, selected);
      });
      if (wouldReplaceSeparateCalendars) {
        setPanelError(
          'This year already has separate level calendars. Keep “Different dates for each level” ' +
            'to add another level (for example Undergraduate alongside Graduate) without deleting ' +
            'the existing calendar. Choose “Same dates for all levels” only after those separate ' +
            'calendars are removed.'
        );
        return;
      }
    }
    setDateScheduleMode(nextMode);
    setPanelError(null);
    setForms(rebuildForms({ nextMode }));
  };

  const resolveYearToSelectedTemplate = async () => {
    if (!templateId) {
      setPanelError('Select the template you want to keep for this year first.');
      return;
    }
    const conflicting = intakesForOtherTemplateOverlappingLevels({
      intakes: savedIntakes,
      year,
      templateId,
      levelIds: selectedLevelIds,
    });
    if (conflicting.length === 0) return;

    const keepName =
      templates.find(item => item.id === templateId)?.name || 'the selected template';
    const removeIds = distinctTemplateIdsForYear(conflicting, year);
    const removeNames = removeIds
      .map(id => templates.find(item => item.id === id)?.name || `Template #${id}`)
      .join(', ');
    const levelLabel = levelIdsLabel(selectedLevelIds, levels);
    const confirmed = await openConfirm({
      title: `Replace ${levelLabel} calendars?`,
      message: [
        `This will delete ${removeNames} calendars for ${levelLabel} in ${year}.`,
        '',
        `Those levels will then use "${keepName}". Calendars for other levels stay unchanged.`,
      ].join('\n'),
      confirmLabel: 'Replace level calendars',
      variant: 'danger',
    });
    if (!confirmed) return;

    setSaving(true);
    setPanelError(null);
    try {
      await deleteIntakesForYearTemplates(conflicting);
      const refreshed = await apiFetch<InstitutionIntakeRecord[]>(
        `academia/institutions/${institutionId}/intakes/by-entity?entity_type=${entityType}&entity_id=${entityId}&year=${year}`
      );
      const nextSaved = Array.isArray(refreshed) ? refreshed : [];
      setSavedIntakes(nextSaved);
      applyTemplateSelection(templateId, nextSaved);
      onUpdated?.();
    } catch (err) {
      setPanelError(
        err instanceof Error ? err.message : 'Failed to replace overlapping level calendars.'
      );
    } finally {
      setSaving(false);
    }
  };

  const unlockOverride = (intakeId: number) => {
    setOverrideUnlockedIds(prev => {
      const next = new Set(prev);
      next.add(intakeId);
      return next;
    });
  };

  const updateFormField = (id: number, field: keyof IntakeDateFormValues, value: string) => {
    setForms(prev =>
      prev.map(form => (form.id === id ? { ...form, [field]: value } : form))
    );
  };

  const persistForms = useCallback(
    async (formsToSave: IntakeDateFormValues[]): Promise<boolean> => {
      if (formsToSave.length === 0) return true;

      const invalid = formsToSave.find(
        form => validateIntakeTimeline(form).messages.length > 0
      );
      if (invalid) {
        const messages = validateIntakeTimeline(invalid).messages;
        setPanelError(
          `Fix dates for ${invalid.term_name || invalid.name}: ${messages.join(' ')}`
        );
        return false;
      }
      if (
        selectedLevelIds.length === 0 ||
        formsToSave.some(form => (form.level_ids || []).length === 0)
      ) {
        setPanelError('Select at least one level before saving.');
        return false;
      }

      const levelsBeingSaved = [
        ...new Set(formsToSave.flatMap(form => (form.level_ids || []).map(Number)).filter(id => id > 0)),
      ];
      const conflictingTemplates = templateId
        ? intakesForOtherTemplateOverlappingLevels({
            intakes: savedIntakes,
            year,
            templateId,
            levelIds: levelsBeingSaved,
          })
        : [];
      if (conflictingTemplates.length > 0) {
        const existingIds = distinctTemplateIdsForYear(conflictingTemplates, year);
        const existingNames = existingIds
          .map(id => templates.find(item => item.id === id)?.name || `Template #${id}`)
          .join(', ');
        setPanelError(
          `Selected levels already use ${existingNames} for ${year}. ` +
            'Uncheck those levels, or replace that level’s calendar when changing templates. ' +
            'Other levels may keep a different calendar system in the same year.'
        );
        return false;
      }

      if (dateScheduleMode === 'shared' && templateId) {
        const sharedLevels = [...selectedLevelIds].filter(id => id > 0);
        const existingForTemplate = savedIntakes.filter(
          row =>
            Number(row.template_id) === Number(templateId) && Number(row.year) === Number(year)
        );
        const conflictingGroups = distinctLevelGroups(existingForTemplate).filter(group => {
          const groupSet = new Set(group);
          const overlap = sharedLevels.some(id => groupSet.has(id));
          return overlap && !sameLevelIds(group, sharedLevels);
        });
        if (conflictingGroups.length > 0) {
          setPanelError(
            'This year already has separate level calendars. Switch to “Different dates for each level” ' +
              'to add another level without deleting the existing ones.'
          );
          return false;
        }
      }

      setSaving(true);
      setPanelError(null);
      try {
        const groups = groupFormsByLevelKey(formsToSave);
        const rowsToUpdate: IntakeDateFormValues[] = [];
        const claimedIntakeIds = new Set<number>();

        let existingRows = await apiFetch<InstitutionIntakeRecord[]>(
          `academia/institutions/${institutionId}/intakes/by-entity?entity_type=${entityType}&entity_id=${entityId}&year=${year}`
        );
        if (!Array.isArray(existingRows)) existingRows = [];

        // Only strip true shared/partial-overlap blockers when saving per-level calendars.
        // Never delete a non-overlapping sibling level calendar (e.g. keep Graduate when adding UG).
        if (templateId && dateScheduleMode === 'per_level') {
          const blocking = intakesBlockingLevelGroups({
            rows: existingRows,
            templateId: Number(templateId),
            year,
            entityType,
            entityId,
            targetLevelGroups: groups.map(group => group.levelIds),
          });
          for (const row of blocking) {
            if (!row?.id) continue;
            await apiFetch(`academia/institutions/${institutionId}/intakes/${row.id}`, {
              method: 'DELETE',
            });
          }
          if (blocking.length > 0) {
            existingRows = await apiFetch<InstitutionIntakeRecord[]>(
              `academia/institutions/${institutionId}/intakes/by-entity?entity_type=${entityType}&entity_id=${entityId}&year=${year}`
            );
            if (!Array.isArray(existingRows)) existingRows = [];
          }
        }

        for (const group of groups) {
          const levelIds = [...group.levelIds].filter(id => id > 0);
          if (levelIds.length === 0) continue;

          let groupForms = group.forms;
          const pendingForms = groupForms.filter(form => form.is_pending);
          if (pendingForms.length > 0) {
            if (!templateId) {
              setPanelError('Select an academic template before saving.');
              return false;
            }

            // Reuse exact term+level rows before calling configure.
            groupForms = groupForms.map(form => {
              if (!form.is_pending) return form;
              const existing = matchCreatedIntakeRow({
                rows: existingRows,
                termName: form.term_name || '',
                levelIds,
                templateId: Number(templateId),
                entityType,
                entityId,
                year,
                claimedIds: claimedIntakeIds,
              });
              if (!existing) return form;
              claimedIntakeIds.add(existing.id);
              return {
                ...form,
                id: existing.id,
                is_pending: false,
                level_ids: [...levelIds],
              };
            });

            const stillPending = groupForms.filter(form => form.is_pending);
            if (stillPending.length > 0) {
              const termNames = stillPending
                .map(form => (form.term_name || '').trim())
                .filter(Boolean);
              if (termNames.length === 0) {
                setPanelError('Selected template terms are missing term names.');
                return false;
              }
              const payload: IntakeConfigurePayload = {
                entity_type: entityType,
                entity_id: entityId,
                template_id: Number(templateId),
                level_ids: levelIds,
                term_names: [...new Set(termNames)],
                year,
                cascade_to_children: entityType === 'college' ? false : cascade,
              };

              let createdRows: InstitutionIntakeRecord[] = [];
              try {
                createdRows = await apiFetch<InstitutionIntakeRecord[]>(
                  `academia/institutions/${institutionId}/intakes/configure`,
                  {
                    method: 'POST',
                    body: JSON.stringify(payload),
                  }
                );
              } catch (err) {
                const message = err instanceof Error ? err.message : '';
                const isOverlapConflict =
                  message.toLowerCase().includes('overlapping level') ||
                  message.toLowerCase().includes('already exist');
                if (!isOverlapConflict) throw err;
                createdRows = await apiFetch<InstitutionIntakeRecord[]>(
                  `academia/institutions/${institutionId}/intakes/by-entity?entity_type=${entityType}&entity_id=${entityId}&year=${year}`
                );
              }

              const createdList = Array.isArray(createdRows) ? createdRows : [];
              existingRows = [
                ...existingRows.filter(row => !createdList.some(created => created.id === row.id)),
                ...createdList,
              ];

              groupForms = groupForms.map(form => {
                if (!form.is_pending) return form;
                const created = matchCreatedIntakeRow({
                  rows: createdList.length ? createdList : existingRows,
                  termName: form.term_name || '',
                  levelIds,
                  templateId: Number(templateId),
                  entityType,
                  entityId,
                  year,
                  claimedIds: claimedIntakeIds,
                });
                if (!created) {
                  throw new Error(
                    `Could not create ${form.term_name || form.name} for ${levelIdsLabel(
                      levelIds,
                      levels
                    )}. Delete any shared Rolling calendar for this year, then save again.`
                  );
                }
                claimedIntakeIds.add(created.id);
                return {
                  ...form,
                  id: created.id,
                  is_pending: false,
                  level_ids: [...levelIds],
                };
              });
            }
          } else {
            for (const form of groupForms) {
              if (form.id > 0) claimedIntakeIds.add(form.id);
            }
          }

          rowsToUpdate.push(...groupForms);
        }

        if (rowsToUpdate.length === 0) {
          setPanelError('No intake terms were ready to save.');
          return false;
        }

        // Sequential updates avoid cascade races when multiple level calendars share a term name.
        for (const form of rowsToUpdate) {
          await apiFetch(`academia/institutions/${institutionId}/intakes/${form.id}`, {
            method: 'PUT',
            body: JSON.stringify({
              application_deadline: form.application_deadline || null,
              check_in_date: form.check_in_date || null,
              orientation_date: form.orientation_date || null,
              class_start_date: form.class_start_date || null,
              start_date: form.class_start_date || null,
              level_ids: form.level_ids,
              cascade_to_children: entityType === 'college' ? false : cascade,
            }),
          });
        }
        await loadData();
        onUpdated?.();
        return true;
      } catch (err) {
        setPanelError(err instanceof Error ? err.message : 'Failed to save intake dates.');
        return false;
      } finally {
        setSaving(false);
      }
    },
    [
      cascade,
      dateScheduleMode,
      entityId,
      entityType,
      institutionId,
      levels,
      loadData,
      onUpdated,
      savedIntakes,
      selectedLevelIds,
      setPanelError,
      templateId,
      templates,
      year,
    ]
  );

  const saveAll = useCallback(async (): Promise<string | null> => {
    if (forms.length === 0) {
      setPanelError(null);
      return null;
    }
    if (selectedLevelIds.length === 0 || forms.some(form => (form.level_ids || []).length === 0)) {
      const message = 'Select at least one level before saving.';
      setPanelError(message);
      return message;
    }
    // Every selected level calendar must be fully dated — never silently save only the first complete one.
    if (incompleteForms.length > 0) {
      const message = `Finish intake dates for every selected level before saving: ${incompleteForms
        .map(
          form =>
            `${form.term_name || form.name} (${levelIdsLabel(form.level_ids || [], levels)})`
        )
        .join(', ')}.`;
      setPanelError(message);
      return message;
    }
    if (hasEnteredDateConflicts) {
      const message = 'Fix intake date conflicts before saving.';
      setPanelError(message);
      return message;
    }
    if (saveableForms.length === 0) {
      setPanelError(null);
      return null;
    }
    const saved = await persistForms(saveableForms);
    if (saved) {
      setPanelError(null);
      return null;
    }
    return errorRef.current || 'Failed to save intake dates.';
  }, [
    forms,
    hasEnteredDateConflicts,
    incompleteForms,
    levels,
    persistForms,
    saveableForms,
    selectedLevelIds.length,
    setPanelError,
  ]);

  const saveIntakeDates = async () => {
    await saveAll();
  };

  useImperativeHandle(ref, () => ({ saveAll }), [saveAll]);

  const resetToParent = async (intakeId: number) => {
    setSaving(true);
    setPanelError(null);
    try {
      await apiFetch(
        `academia/institutions/${institutionId}/intakes/${intakeId}/reset`,
        { method: 'POST' }
      );
      await loadData();
      onUpdated?.();
    } catch (err) {
      setPanelError(err instanceof Error ? err.message : 'Failed to reset intake.');
    } finally {
      setSaving(false);
    }
  };

  const deleteMappedIntake = async (form: IntakeDateFormValues) => {
    if (form.is_pending || form.id <= 0) return;
    const confirmed = await openConfirm({
      title: 'Delete mapped calendar?',
      message: `Delete the mapped calendar "${form.term_name || form.name}" for ${levelIdsLabel(
        form.level_ids || [],
        levels
      )}? Any calendars cascaded from it will also be deleted.`,
      confirmLabel: 'Delete',
      variant: 'danger',
    });
    if (!confirmed) return;

    setDeletingIntakeId(form.id);
    setPanelError(null);
    try {
      await apiFetch(
        `academia/institutions/${institutionId}/intakes/${form.id}`,
        { method: 'DELETE' }
      );
      await loadData();
      onUpdated?.();
    } catch (err) {
      setPanelError(err instanceof Error ? err.message : 'Failed to delete intake calendar.');
    } finally {
      setDeletingIntakeId(null);
    }
  };

  if (loading) {
    return <p className="text-sm text-text-muted">Loading calendar configuration...</p>;
  }

  return (
    <div className="space-y-6">
      {error ? <p className="text-sm text-alert">{error}</p> : null}

      <section className="rounded-2xl border border-border-subtle bg-card p-4 space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h4 className="font-semibold text-text-main">Template setup</h4>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={saving || saveableForms.length === 0 || selectedLevelIds.length === 0}
              onClick={() => void saveIntakeDates()}
              className="rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-text-dark-bg disabled:opacity-50"
            >
              {saving ? 'Saving...' : 'Save dates'}
            </button>
            {onClose ? (
              <button
                type="button"
                onClick={onClose}
                className="inline-flex items-center gap-1 rounded-lg border border-border-subtle px-2.5 py-1.5 text-xs font-semibold text-text-muted hover:bg-surface-bg"
              >
                <X size={14} />
                Close
              </button>
            ) : null}
          </div>
        </div>
        <label className="block text-sm text-text-muted">Academic year</label>
        <input
          type="number"
          min={2000}
          max={2100}
          value={year}
          onChange={e => setYear(Number(e.target.value))}
          className="w-full rounded-xl border border-border-subtle px-3 py-2 text-sm"
        />
        {existingTemplateForYear && !mixedTemplatesForYear ? (
          <p className="rounded-xl border border-border-subtle bg-surface-bg/60 px-3 py-2 text-xs text-text-muted">
            Year {year} already has a{' '}
            <span className="font-semibold text-text-main">
              {templateStructureType(existingTemplateForYear)}
            </span>{' '}
            calendar ({existingTemplateForYear.name}). You can still choose another template for a
            different level (for example Trimester for Graduate while Undergraduate stays on
            Semester).
          </p>
        ) : null}
        {mixedTemplatesForYear ? (
          <p className="rounded-xl border border-border-subtle bg-surface-bg/60 px-3 py-2 text-xs text-text-muted">
            Year {year} uses more than one calendar system across levels
            {templatesInSelectedYear
              .map(id => templates.find(item => item.id === id)?.name)
              .filter(Boolean)
              .join(', ')
              ? ` (${templatesInSelectedYear
                  .map(id => templates.find(item => item.id === id)?.name || `Template #${id}`)
                  .join(', ')})`
              : ''}
            . That is allowed when each level has its own template. Select a template and the
            level(s) you want to edit.
          </p>
        ) : null}
        {yearTemplateConflict.length > 0 && templateId ? (
          <div
            role="alert"
            className="space-y-2 rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900"
          >
            <p>
              The selected level(s) already use another template for {year}. Replace only those
              level calendars to switch systems, or uncheck levels that should keep their current
              template.
            </p>
            <button
              type="button"
              disabled={saving}
              onClick={() => void resolveYearToSelectedTemplate()}
              className="rounded-lg border border-amber-400 bg-white px-3 py-1.5 text-xs font-semibold text-amber-900 hover:bg-amber-100 disabled:opacity-50"
            >
              Replace selected levels with current template
            </button>
          </div>
        ) : null}
        <fieldset
          className={`rounded-xl border px-3 py-2 ${
            hasLevelConflict
              ? 'border-alert/60 bg-alert/5'
              : 'border-border-subtle'
          }`}
          aria-describedby={hasLevelConflict ? 'intake-levels-error' : undefined}
        >
          <legend className="px-1 text-sm text-text-muted">Levels *</legend>
          <div className="grid gap-2 sm:grid-cols-2">
            {levels.map(level => (
              <label key={level.id} className="flex items-start gap-2 text-sm text-text-main">
                <input
                  type="checkbox"
                  checked={selectedLevelIds.includes(level.id)}
                  disabled={saving}
                  onChange={event =>
                    handleLevelIdsChange(
                      event.target.checked
                        ? [...selectedLevelIds, level.id]
                        : selectedLevelIds.filter(id => id !== level.id)
                    )
                  }
                  className="mt-0.5"
                />
                <span>
                  {level.name} <span className="text-text-muted">({level.code})</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>
        {hasLevelConflict ? (
          <p id="intake-levels-error" className="text-xs font-medium text-alert">
            Select at least one level.
          </p>
        ) : null}
        {selectedLevelIds.length > 1 ? (
          <fieldset className="rounded-xl border border-border-subtle px-3 py-2">
            <legend className="px-1 text-sm text-text-muted">Date schedule *</legend>
            <div className="space-y-2">
              <label className="flex items-start gap-2 text-sm text-text-main">
                <input
                  type="radio"
                  name="intake-date-schedule"
                  checked={dateScheduleMode === 'shared'}
                  disabled={saving}
                  onChange={() => handleDateScheduleModeChange('shared')}
                  className="mt-0.5"
                />
                <span>
                  Same dates for all selected levels
                  <span className="mt-0.5 block text-xs text-text-muted">
                    One calendar shared by {levelIdsLabel(selectedLevelIds, levels)}.
                  </span>
                </span>
              </label>
              <label className="flex items-start gap-2 text-sm text-text-main">
                <input
                  type="radio"
                  name="intake-date-schedule"
                  checked={dateScheduleMode === 'per_level'}
                  disabled={saving}
                  onChange={() => handleDateScheduleModeChange('per_level')}
                  className="mt-0.5"
                />
                <span>
                  Different dates for each level
                  <span className="mt-0.5 block text-xs text-text-muted">
                    Separate calendars per level for this year. You can add another level later
                    without deleting calendars already saved for this year.
                  </span>
                </span>
              </label>
            </div>
          </fieldset>
        ) : null}
        {calendarGroupCount > 1 ? (
          <p className="text-xs text-text-muted">
            Editing {calendarGroupCount} level calendars for this template. Complete dates for each
            group before saving.
          </p>
        ) : null}
        <label className="block text-sm text-text-muted">Global academic template</label>
        <select
          value={templateId}
          disabled={saving}
          onChange={e =>
            void handleTemplateChange(e.target.value ? Number(e.target.value) : '')
          }
          className="w-full rounded-xl border border-border-subtle px-3 py-2 text-sm"
        >
          <option value="">Select template</option>
          {templates.map(template => (
            <option key={template.id} value={template.id}>
              {template.name}
            </option>
          ))}
        </select>
        {entityType !== 'college' ? (
          <label className="flex items-center gap-2 text-sm text-text-main">
            <input type="checkbox" checked={cascade} onChange={e => setCascade(e.target.checked)} />
            {entityType === 'institution'
              ? 'Cascade to all schools / colleges'
              : 'Cascade to child entities'}
          </label>
        ) : null}
        {hasPendingForms ? (
          <p className="text-xs text-text-muted">
            Template terms are shown as a draft. Nothing is saved until you click Save dates.
          </p>
        ) : null}
        {incompleteForms.length > 0 ? (
          <p className="rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800">
            Incomplete date setup:{' '}
            {incompleteForms
              .map(
                form =>
                  `${form.term_name || form.name} (${levelIdsLabel(form.level_ids || [], levels)})`
              )
              .join(', ')}
            . Only complete date setups will be saved.
          </p>
        ) : null}
      </section>

      {forms.length === 0 ? (
        <EmptyListMessage
          message={
            templateId
              ? 'This template has no intake terms configured.'
              : `No intakes configured for ${year} yet.`
          }
        />
      ) : (
        <IntakeTermsBrowser
          forms={forms}
          templates={templates}
          levels={levels}
          dateValidationById={dateValidationById}
          saving={saving}
          deletingIntakeId={deletingIntakeId}
          overrideUnlockedIds={overrideUnlockedIds}
          onUpdateField={updateFormField}
          onUnlockOverride={unlockOverride}
          onResetToParent={id => void resetToParent(id)}
          onDelete={form => void deleteMappedIntake(form)}
        />
      )}
    </div>
  );
});

IntakeConfigureContent.displayName = 'IntakeConfigureContent';
export default IntakeConfigureContent;
