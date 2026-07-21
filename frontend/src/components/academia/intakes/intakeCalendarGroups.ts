import type { GlobalAcademicTemplate, InstitutionIntakeRecord } from '../../../types/academicCalendar';
import type { IntakeDateFormValues } from '../../../types/hierarchicalIntake';
import type { LevelRecord } from '../../../types/level';

export type IntakeDateScheduleMode = 'shared' | 'per_level';

export function levelIdsKey(levelIds: number[] | null | undefined): string {
  return [...(levelIds || [])]
    .map(Number)
    .filter(id => id > 0)
    .sort((a, b) => a - b)
    .join(',');
}

export function sameLevelIds(
  left: number[] | null | undefined,
  right: number[] | null | undefined
): boolean {
  return levelIdsKey(left) === levelIdsKey(right);
}

export function levelIdsLabel(
  levelIds: number[],
  levels: Array<Pick<LevelRecord, 'id' | 'name' | 'code'>>
): string {
  const orderIndex = new Map(levels.map((level, index) => [Number(level.id), index]));
  const labels = [...levelIds]
    .map(Number)
    .filter(id => id > 0)
    .sort((left, right) => {
      const leftRank = orderIndex.get(left) ?? left;
      const rightRank = orderIndex.get(right) ?? right;
      return leftRank - rightRank;
    })
    .map(id => levels.find(level => level.id === id))
    .filter((level): level is Pick<LevelRecord, 'id' | 'name' | 'code'> => Boolean(level))
    .map(level => level.name || level.code || `Level ${level.id}`);
  if (labels.length === 0) return 'No levels';
  if (labels.length === 1) return labels[0];
  if (labels.length === 2) return `${labels[0]} & ${labels[1]}`;
  return `${labels.slice(0, -1).join(', ')} & ${labels[labels.length - 1]}`;
}

export function mapIntakeToForm(row: InstitutionIntakeRecord): IntakeDateFormValues {
  return {
    id: row.id,
    name: row.display_name || row.name,
    template_id: row.template_id,
    term_name: row.term_name,
    year: row.year,
    application_deadline: row.application_deadline || '',
    check_in_date: row.check_in_date || '',
    orientation_date: row.orientation_date || '',
    class_start_date: row.class_start_date || row.start_date || '',
    is_overridden: row.is_overridden ?? false,
    parent_intake_id: row.parent_intake_id,
    is_pending: false,
    level_ids: [...(row.level_ids || [])],
  };
}

export function mapTemplateToPendingForms(
  template: GlobalAcademicTemplate,
  year: number,
  levelIds: number[],
  pendingBase = 0
): IntakeDateFormValues[] {
  return (template.default_intake_configs || []).map((config, index) => ({
    id: -(pendingBase * 100 + index + 1),
    name: `${config.term_name} ${year}`,
    template_id: template.id,
    term_name: config.term_name,
    year,
    application_deadline: '',
    check_in_date: '',
    orientation_date: '',
    class_start_date: '',
    is_overridden: false,
    parent_intake_id: null,
    is_pending: true,
    level_ids: [...levelIds],
  }));
}

/** Distinct level-id sets present on saved intakes for a template. */
export function distinctLevelGroups(
  intakes: InstitutionIntakeRecord[]
): number[][] {
  const seen = new Map<string, number[]>();
  for (const row of intakes) {
    const ids = [...(row.level_ids || [])].filter(id => id > 0);
    if (ids.length === 0) continue;
    const key = levelIdsKey(ids);
    if (!seen.has(key)) seen.set(key, ids.sort((a, b) => a - b));
  }
  return [...seen.values()];
}

export function inferDateScheduleMode(levelGroups: number[][]): IntakeDateScheduleMode {
  if (levelGroups.length <= 1) return 'shared';
  return 'per_level';
}

/**
 * Pick shared vs per-level when the user changes level checkboxes.
 * If this year already has calendar(s) that are not exactly one shared set matching
 * the new selection, use per-level so another level can be added without deleting
 * the existing Graduate/Undergraduate (etc.) calendar.
 */
export function preferredDateScheduleMode(options: {
  selectedLevelIds: number[];
  existingLevelGroups: number[][];
  requestedMode?: IntakeDateScheduleMode;
}): IntakeDateScheduleMode {
  const selected = [...options.selectedLevelIds].filter(id => id > 0).sort((a, b) => a - b);
  if (selected.length <= 1) return 'shared';

  const groups = options.existingLevelGroups;
  if (groups.length === 0) {
    return options.requestedMode ?? 'shared';
  }

  const matchesSingleShared =
    groups.length === 1 && sameLevelIds(groups[0], selected);
  if (matchesSingleShared) {
    return options.requestedMode ?? 'shared';
  }

  return 'per_level';
}

/**
 * Build editable term forms for the selected template / mode / levels.
 * Matches saved rows by term name + exact level-id set.
 */
export function buildFormsForSchedule(options: {
  templateId: number | '';
  year: number;
  templates: GlobalAcademicTemplate[];
  savedIntakes: InstitutionIntakeRecord[];
  mode: IntakeDateScheduleMode;
  selectedLevelIds: number[];
  levels?: Array<Pick<LevelRecord, 'id'>>;
}): IntakeDateFormValues[] {
  const { templateId, year, templates, savedIntakes, mode, selectedLevelIds, levels } = options;
  if (!templateId) {
    return savedIntakes.map(mapIntakeToForm);
  }

  const matching = savedIntakes.filter(
    row =>
      Number(row.template_id) === Number(templateId) && Number(row.year) === Number(year)
  );
  const template = templates.find(item => item.id === templateId);
  if (!template) return matching.map(mapIntakeToForm);

  const selectedRaw = [...selectedLevelIds].map(Number).filter(id => id > 0);
  const selected =
    levels && levels.length > 0
      ? sortLevelIdsByLevelsOrder(selectedRaw, levels)
      : [...selectedRaw].sort((a, b) => a - b);
  if (selected.length === 0) return [];

  const groups: number[][] =
    mode === 'shared' ? [selected] : selected.map(id => [id]);

  const forms: IntakeDateFormValues[] = [];
  groups.forEach((levelIds, groupIndex) => {
    const pending = mapTemplateToPendingForms(template, year, levelIds, groupIndex + 1);
    for (const draft of pending) {
      const saved = matching.find(
        row =>
          (row.term_name || '').trim() === (draft.term_name || '').trim() &&
          sameLevelIds(row.level_ids, levelIds)
      );
      forms.push(saved ? mapIntakeToForm(saved) : draft);
    }
  });
  return forms;
}

function sortLevelIdsByLevelsOrder(
  levelIds: number[],
  levels: Array<Pick<LevelRecord, 'id'>>
): number[] {
  const orderIndex = new Map(levels.map((level, index) => [Number(level.id), index]));
  return [...levelIds].sort((left, right) => {
    const leftRank = orderIndex.get(Number(left)) ?? Number(left);
    const rightRank = orderIndex.get(Number(right)) ?? Number(right);
    return leftRank - rightRank;
  });
}

export function templateStructureType(
  template: Pick<GlobalAcademicTemplate, 'name' | 'default_intake_configs'> | null | undefined
): string {
  const name = (template?.name || '').trim();
  const lower = name.toLowerCase();
  if (lower.includes('trimester')) return 'Trimester';
  if (lower.includes('quarter')) return 'Quarter';
  if (lower.includes('semester')) return 'Semester';
  if (lower.includes('rolling')) return 'Rolling';
  const termCount = template?.default_intake_configs?.length || 0;
  if (termCount >= 4) return 'Quarter';
  if (termCount === 3) return 'Trimester';
  if (termCount === 2) return 'Semester';
  return name || 'Not assigned';
}

export function distinctTemplateIdsForYear(
  intakes: InstitutionIntakeRecord[],
  year: number
): number[] {
  const ids = new Set<number>();
  for (const row of intakes) {
    if (Number(row.year) !== Number(year)) continue;
    const templateId = Number(row.template_id) || 0;
    if (templateId > 0) ids.add(templateId);
  }
  return [...ids].sort((a, b) => a - b);
}

export function intakesForOtherTemplateInYear(
  intakes: InstitutionIntakeRecord[],
  year: number,
  templateId: number | ''
): InstitutionIntakeRecord[] {
  if (!templateId) return [];
  return intakes.filter(
    row =>
      Number(row.year) === Number(year) &&
      Number(row.template_id) > 0 &&
      Number(row.template_id) !== Number(templateId)
  );
}

function levelsOverlap(
  left: number[] | null | undefined,
  right: number[] | null | undefined
): boolean {
  const rightSet = new Set([...(right || [])].map(Number).filter(id => id > 0));
  return [...(left || [])].map(Number).some(id => id > 0 && rightSet.has(id));
}

/**
 * Other-template rows for this year that overlap the selected levels.
 * Non-overlapping levels may keep a different calendar system (Semester vs Trimester).
 */
export function intakesForOtherTemplateOverlappingLevels(options: {
  intakes: InstitutionIntakeRecord[];
  year: number;
  templateId: number | '';
  levelIds: number[];
}): InstitutionIntakeRecord[] {
  const { intakes, year, templateId, levelIds } = options;
  const selected = [...levelIds].map(Number).filter(id => id > 0);
  if (!templateId || selected.length === 0) return [];
  return intakesForOtherTemplateInYear(intakes, year, templateId).filter(row =>
    levelsOverlap(row.level_ids, selected)
  );
}

export function groupFormsByLevelKey(
  forms: IntakeDateFormValues[]
): Array<{ key: string; levelIds: number[]; forms: IntakeDateFormValues[] }> {
  const sections: Array<{ key: string; levelIds: number[]; forms: IntakeDateFormValues[] }> = [];
  const indexByKey = new Map<string, number>();
  for (const form of forms) {
    const key = levelIdsKey(form.level_ids) || 'none';
    let index = indexByKey.get(key);
    if (index === undefined) {
      index = sections.length;
      indexByKey.set(key, index);
      sections.push({ key, levelIds: [...(form.level_ids || [])], forms: [] });
    }
    sections[index].forms.push(form);
  }
  return sections;
}

/** Sort level-calendar groups to match the Levels list order (API / checkbox order). */
export function sortLevelGroupsByLevelsOrder<
  T extends { levelIds: number[] },
>(groups: T[], levels: Array<Pick<LevelRecord, 'id'>>): T[] {
  const orderIndex = new Map(levels.map((level, index) => [Number(level.id), index]));
  const rank = (levelIds: number[]) => {
    const ids = [...levelIds].map(Number).filter(id => id > 0);
    if (ids.length === 0) return Number.MAX_SAFE_INTEGER;
    let best = Number.MAX_SAFE_INTEGER;
    for (const id of ids) {
      const index = orderIndex.get(id);
      if (index !== undefined && index < best) best = index;
    }
    return best === Number.MAX_SAFE_INTEGER ? Math.min(...ids) : best;
  };
  return [...groups].sort((left, right) => {
    const byLevel = rank(left.levelIds) - rank(right.levelIds);
    if (byLevel !== 0) return byLevel;
    return levelIdsKey(left.levelIds).localeCompare(levelIdsKey(right.levelIds));
  });
}

/**
 * Resolve a pending draft form to a newly configured (or existing) intake row.
 * Must match term + exact level set — never fall back to term-only, because Rolling
 * (and any shared term name) would otherwise map Grad/Doctoral onto the Undergrad row.
 */
export function matchCreatedIntakeRow(options: {
  rows: InstitutionIntakeRecord[];
  termName: string;
  levelIds: number[];
  templateId: number;
  entityType: string;
  entityId: number;
  year: number;
  claimedIds?: Set<number>;
}): InstitutionIntakeRecord | undefined {
  const {
    rows,
    termName,
    levelIds,
    templateId,
    entityType,
    entityId,
    year,
    claimedIds,
  } = options;
  const term = (termName || '').trim();
  const scoped = rows.filter(row => {
    if (claimedIds?.has(row.id)) return false;
    if (Number(row.template_id) !== Number(templateId)) return false;
    if (Number(row.year) !== Number(year)) return false;
    if (row.entity_type && row.entity_type !== entityType) return false;
    if (row.entity_id != null && Number(row.entity_id) !== Number(entityId)) return false;
    return (row.term_name || '').trim() === term;
  });

  const exact = scoped.find(row => sameLevelIds(row.level_ids, levelIds));
  if (exact) return exact;

  // Legacy rows with empty level_ids: only safe when exactly one unclaimed term match remains.
  const legacyEmpty = scoped.filter(row => !(row.level_ids || []).length);
  if (legacyEmpty.length === 1 && scoped.length === 1) {
    return legacyEmpty[0];
  }
  return undefined;
}

/**
 * Rows that block creating the requested per-level (or shared) calendars:
 * they overlap a target level set but are not an exact match for any target set
 * (typical leftover "same dates for all levels" calendar).
 */
export function intakesBlockingLevelGroups(options: {
  rows: InstitutionIntakeRecord[];
  templateId: number;
  year: number;
  entityType: string;
  entityId: number;
  targetLevelGroups: number[][];
}): InstitutionIntakeRecord[] {
  const { rows, templateId, year, entityType, entityId, targetLevelGroups } = options;
  const targets = targetLevelGroups
    .map(group => [...group].map(Number).filter(id => id > 0))
    .filter(group => group.length > 0);
  if (targets.length === 0) return [];

  return rows.filter(row => {
    if (Number(row.template_id) !== Number(templateId)) return false;
    if (Number(row.year) !== Number(year)) return false;
    if (row.entity_type && row.entity_type !== entityType) return false;
    if (row.entity_id != null && Number(row.entity_id) !== Number(entityId)) return false;
    const rowLevels = [...(row.level_ids || [])].map(Number).filter(id => id > 0);
    if (targets.some(group => sameLevelIds(rowLevels, group))) return false;
    return targets.some(group => levelsOverlap(rowLevels, group));
  });
}
