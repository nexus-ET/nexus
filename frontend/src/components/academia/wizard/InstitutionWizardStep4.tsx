import {
  Fragment,
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from 'react';
import { Loader2, Pencil, Plus, Search, Unlink } from 'lucide-react';

import { fetchAcademiaListItems } from '../../../utils/academiaList';
import { apiFetch } from '../../../utils/api';
import { useAcademiaLevels } from '../../../hooks/useLevels';
import { levelSelectOptions } from '../../../constants/levels';
import { ACADEMIC_FRAMEWORK_LABELS, ACADEMIC_FRAMEWORK_STEP_LABELS } from '../../../schemas/academicFrameworkHierarchy';
import {
  courseOfferingToApiPayload,
  hydrateWizardCourseOffering,
  wizardCoursesStepSchema,
  type WizardCourseOfferingItem,
} from '../../../schemas/wizard/step4-courses';
import type { CourseRecord, DegreeRecord } from '../../../types/academicFramework';
import type { EducationMajorRecord, ProgramMajorMappingListResponse } from '../../../types/educationMajor';
import SearchableSelect from '../SearchableSelect';
import SearchableMultiSelect from '../SearchableMultiSelect';
import FrameworkTablePagination from '../FrameworkTablePagination';
import FrameworkSortableHeader from '../FrameworkSortableHeader';
import WizardFieldError from './form/WizardFieldError';
import type { WizardStepHandle } from './form/wizardStepRef';
import {
  getWizardListStepSnapshot,
  useWizardListStepDefaultsSync,
  useWizardStepSnapshot,
} from './form/wizardDirtyTracking';
import { wizardSectionClass, wizardSectionTitleClass } from './form/wizardFormStyles';
import WizardCourseEditPanel, {
  type WizardCourseEditValues,
} from './WizardCourseEditPanel';
import { useConfirmation } from '../../../context/ConfirmationContext';
import EmptyListMessage from '../../ui/EmptyListMessage';
import TextPromptModal from '../../TextPromptModal';
import {
  createEmptyWizardCollegeDraft,
  hydrateWizardCollege,
  type WizardCollegeItem,
} from '../../../schemas/wizard/step3-colleges';
import WizardAcademicsHierarchyTree from './WizardAcademicsHierarchyTree';
import {
  cloneOfferingForCollege,
  collegeScopeKey,
  expandInstitutionUnlinkIndices,
  filterOfferingsForScope,
  getCollegeOwnedUnlinkIndices,
  getUnlinkableIndicesForDisplayedScope,
  groupProgramsForOfferings,
  institutionScopeKey,
  majorGroupHeading,
  offeringMatchesCollege,
  offeringScopeKey,
  stampOfferingScope,
  type GroupedProgramLink,
  type WizardAcademicsEntityScope,
  scopeKey,
} from './wizardAcademicsScope';

interface SavedCourseOffering extends WizardCourseOfferingItem {
  display_label?: string;
}

type EditingAcademicGroup = {
  scope: WizardAcademicsEntityScope;
  replaceIndices: number[];
  sourceIndices: number[];
  label: string;
};

interface InstitutionWizardStep4Props {
  defaultCourses: WizardCourseOfferingItem[];
  layout?: 'flat' | 'hierarchy';
  colleges?: WizardCollegeItem[];
  institutionName?: string;
  defaultCollegeOverrides?: string[];
  onPersistCourses?: (
    courses: ReturnType<typeof courseOfferingToApiPayload>[],
    meta?: { collegeAcademicOverrides: string[] }
  ) => Promise<void>;
  onAddCollege?: (college: WizardCollegeItem) => void;
  onRemoveCollege?: (collegeLocalId: string) => void;
}

type LinkedPanelSortColumn = 'level' | 'program' | 'major' | 'course';

const LINKED_ACADEMICS_PAGE_SIZES = [10, 25, 50] as const;
const DEFAULT_LINKED_ACADEMICS_PAGE_SIZE = 10;

function dedupeById<T extends { id: number | string }>(items: T[]): T[] {
  const seen = new Set<number | string>();
  return items.filter(item => {
    if (seen.has(item.id)) return false;
    seen.add(item.id);
    return true;
  });
}

function majorIdentityKey(major: EducationMajorRecord): string {
  return major.label.trim().toLowerCase();
}

function dedupeMajorsByLabel(majors: EducationMajorRecord[]): EducationMajorRecord[] {
  const byLabel = new Map<string, EducationMajorRecord>();
  for (const major of majors) {
    const key = majorIdentityKey(major);
    if (!byLabel.has(key)) {
      byLabel.set(key, major);
    }
  }
  return Array.from(byLabel.values());
}

function expandMajorIdsForKeys(
  majorInstances: EducationMajorRecord[],
  selectedMajorKeys: string[]
): number[] {
  if (selectedMajorKeys.length === 0) return [];
  const keySet = new Set(selectedMajorKeys);
  return dedupeById(
    majorInstances.filter(major => keySet.has(majorIdentityKey(major)))
  ).map(major => major.id);
}

/** One Programs-dropdown option per program×major mapping. */
function encodeProgramMajorValue(programId: string, majorId: number): string {
  return `${normalizeProgramId(programId)}|${Math.max(0, majorId)}`;
}

function parseProgramMajorValue(value: string): { programId: string; majorId: number } {
  const [rawProgramId = '', rawMajorId = '0'] = String(value).split('|');
  return {
    programId: normalizeProgramId(rawProgramId),
    majorId: Number(rawMajorId) || 0,
  };
}

type ProgramMajorOption = {
  value: string;
  label: string;
  programId: string;
  majorId: number;
};

type CascadeSource = 'program' | null;

function buildDisplayLabel(parts: {
  levelName?: string | null;
  programName?: string | null;
  majorName?: string | null;
  courseName?: string | null;
}): string {
  return [parts.levelName, parts.programName, parts.majorName, parts.courseName]
    .filter(Boolean)
    .join(' > ');
}

function hydrateSavedOffering(raw: WizardCourseOfferingItem): SavedCourseOffering {
  const saved = raw as SavedCourseOffering;
  return {
    ...hydrateWizardCourseOffering(raw),
    display_label: saved.display_label,
  };
}

function offeringProgramUrl(offering: { program_url?: string | null }): string {
  return (offering.program_url || '').trim();
}

function isPositiveIntId(value: string | number | null | undefined): boolean {
  const parsed = Number(String(value ?? '').trim());
  return Number.isInteger(parsed) && parsed > 0;
}

function offeringNeedsEnrichment(offering: SavedCourseOffering): boolean {
  const hasCourse = Number(offering.course_id) > 0;
  const hasStaleScopeLabel =
    Boolean(offering.display_label) &&
    !hasCourse &&
    offering.display_label.includes('Course #0');
  // Program URLs are backfilled on draft load (one SQL). Do not N+1 GET degrees/{id}.
  return !offering.display_label || hasStaleScopeLabel;
}

type EnrichmentMaps = {
  courses: Map<number, CourseRecord>;
  programs: Map<string, DegreeRecord>;
  majors: Map<number, EducationMajorRecord>;
};

async function loadEnrichmentMaps(
  offerings: SavedCourseOffering[]
): Promise<EnrichmentMaps> {
  const needing = offerings.filter(offeringNeedsEnrichment);
  if (needing.length === 0) {
    return { courses: new Map(), programs: new Map(), majors: new Map() };
  }

  const courseIds = new Set<number>();
  const majorIds = new Set<number>();

  for (const offering of needing) {
    if (Number(offering.major_id) > 0) {
      majorIds.add(offering.major_id);
    }
    const hasCourse = Number(offering.course_id) > 0;
    const hasLabel = Boolean(offering.display_label);
    // Payload labels already have names; do not N+1 GET education_courses
    // (wizard course_id is often a target_courses id after catalog rebuild).
    if (hasCourse && !hasLabel && isPositiveIntId(offering.course_id)) {
      courseIds.add(offering.course_id);
    }
  }

  const [courseEntries, majorEntries] = await Promise.all([
    Promise.all(
      [...courseIds].map(async id => {
        try {
          return [id, await apiFetch<CourseRecord>(`academia/courses/${id}`)] as const;
        } catch {
          return [id, null] as const;
        }
      })
    ),
    Promise.all(
      [...majorIds].map(async id => {
        try {
          return [
            id,
            await apiFetch<EducationMajorRecord>(`academia/education-majors/${id}`),
          ] as const;
        } catch {
          return [id, null] as const;
        }
      })
    ),
  ]);
  return {
    courses: new Map(
      courseEntries.filter((entry): entry is [number, CourseRecord] => entry[1] !== null)
    ),
    programs: new Map(),
    majors: new Map(
      majorEntries.filter((entry): entry is [number, EducationMajorRecord] => entry[1] !== null)
    ),
  };
}

function enrichOfferingsWithMaps(
  offerings: WizardCourseOfferingItem[],
  levels: { id: number; name: string }[],
  maps: EnrichmentMaps
): SavedCourseOffering[] {
  const levelMap = new Map(levels.map(level => [level.id, level.name]));

  const withProgramUrl = (
    next: SavedCourseOffering,
    program?: DegreeRecord
  ): SavedCourseOffering => {
    if (offeringProgramUrl(next)) return next;
    const url = program?.program_url?.trim() || null;
    return url ? { ...next, program_url: url } : next;
  };

  return offerings.map(offering => {
    const saved = offering as SavedCourseOffering;
    const hasCourse = Number(offering.course_id) > 0;
    const hasStaleScopeLabel =
      Boolean(saved.display_label) &&
      !hasCourse &&
      saved.display_label.includes('Course #0');
    const knownProgram = String(offering.program_id || '').trim()
      ? maps.programs.get(normalizeProgramId(offering.program_id))
      : undefined;

    if (saved.display_label && !hasStaleScopeLabel) {
      return withProgramUrl(hydrateSavedOffering(offering), knownProgram);
    }

    if (hasCourse) {
      const course = maps.courses.get(offering.course_id);
      if (course) {
        const programId =
          offering.program_id?.trim() || String(course.degree_id || '');
        const program = programId ? maps.programs.get(normalizeProgramId(programId)) : undefined;
        let resolvedLevelId = offering.level_id || program?.level_id || 0;

        return withProgramUrl(
          {
            ...hydrateWizardCourseOffering({
              ...offering,
              level_id: resolvedLevelId,
              program_id: programId,
              major_id: offering.major_id || course.major_id || 0,
              program_url: offering.program_url || program?.program_url || null,
            }),
            display_label:
              course.hierarchy_breadcrumb ||
              buildDisplayLabel({
                levelName: levelMap.get(resolvedLevelId) || course.degree_name,
                programName: program?.name || course.degree_name || course.program_name,
                majorName: course.major_name,
                courseName: course.name || course.label,
              }),
          },
          program
        );
      }
    }

    let levelId = Number(offering.level_id) || 0;
    let programId = offering.program_id?.trim() || '';
    let majorId = Number(offering.major_id) || 0;
    let levelName = levelId > 0 ? levelMap.get(levelId) ?? null : null;
    let programName: string | null = null;
    let majorName: string | null = null;

    const major = majorId > 0 ? maps.majors.get(majorId) : undefined;
    if (major) {
      majorName = major.label;
      if (!programId && major.program_id) {
        programId = String(major.program_id);
      }
      if (!levelId && major.level_id) {
        levelId = major.level_id;
        levelName = levelMap.get(levelId) ?? major.level_name ?? null;
      }
    }

    const program = programId ? maps.programs.get(normalizeProgramId(programId)) : undefined;
    if (program) {
      programName = program.name;
      if (!levelId && program.level_id) {
        levelId = program.level_id;
        levelName = levelMap.get(levelId) ?? program.level_name ?? null;
      }
    }

    return withProgramUrl(
      {
        ...hydrateWizardCourseOffering({
          ...offering,
          level_id: levelId,
          program_id: programId,
          major_id: majorId,
          program_url: offering.program_url || program?.program_url || null,
        }),
        display_label:
          buildDisplayLabel({
            levelName,
            programName,
            majorName,
          }) ||
          levelName ||
          programName ||
          majorName ||
          (hasCourse ? `Course #${offering.course_id}` : 'Academic scope'),
      },
      program
    );
  });
}

async function enrichCourseOfferingLabels(
  offerings: WizardCourseOfferingItem[],
  levels: { id: number; name: string }[]
): Promise<{ offerings: SavedCourseOffering[]; maps: EnrichmentMaps }> {
  const hydrated = offerings.map(hydrateSavedOffering);
  if (!hydrated.some(offeringNeedsEnrichment)) {
    return {
      offerings: hydrated,
      maps: { courses: new Map(), programs: new Map(), majors: new Map() },
    };
  }

  const maps = await loadEnrichmentMaps(hydrated);
  return {
    offerings: enrichOfferingsWithMaps(hydrated, levels, maps),
    maps,
  };
}

function mapsToPanelContext(maps: EnrichmentMaps): {
  programLookup: Map<string, DegreeRecord>;
  majorInstances: EducationMajorRecord[];
  catalogLookup: Map<number, CourseRecord>;
} {
  const programLookup = new Map<string, DegreeRecord>();
  for (const [key, program] of maps.programs.entries()) {
    programLookup.set(normalizeProgramId(key), program);
    programLookup.set(String(program.id), program);
  }
  return {
    programLookup,
    majorInstances: [...maps.majors.values()],
    catalogLookup: maps.courses,
  };
}

function isBlankLevelOnlyScope(offering: WizardCourseOfferingItem): boolean {
  return (
    Number(offering.course_id) === 0 &&
    Number(offering.major_id) === 0 &&
    !normalizeProgramId(offering.program_id) &&
    Number(offering.level_id) > 0
  );
}

function isLinkedAcademicItem(offering: WizardCourseOfferingItem): boolean {
  if (isBlankLevelOnlyScope(offering)) return false;
  return (
    Number(offering.course_id) > 0 ||
    Boolean(normalizeProgramId(offering.program_id)) ||
    Number(offering.major_id) > 0
  );
}

function academicEntryKey(offering: WizardCourseOfferingItem): string {
  if (Number(offering.course_id) > 0) {
    return `course:${offering.course_id}|${normalizeProgramId(offering.program_id)}|${offering.major_id}`;
  }
  return `scope:${offering.level_id}|${offering.program_id}|${offering.major_id}`;
}

function normalizeProgramId(id: string | number | null | undefined): string {
  if (id === null || id === undefined) return '';
  return String(id).trim().toLowerCase();
}

function courseCatalogMajorIdsOf(course: CourseRecord): number[] {
  const ids = [...(course.major_ids ?? [])];
  if (course.major_id && !ids.includes(course.major_id)) {
    ids.push(course.major_id);
  }
  return ids;
}

function isCourseAffiliationOnPanel(
  courseId: number,
  programId: string,
  majorId: number,
  linkedItems: WizardCourseOfferingItem[]
): boolean {
  const normalized = normalizeProgramId(programId);
  if (!courseId || !normalized || majorId <= 0) return false;
  return linkedItems.some(
    item =>
      isLinkedAcademicItem(item) &&
      Number(item.course_id) === courseId &&
      Number(item.major_id) === majorId &&
      normalizeProgramId(item.program_id) === normalized
  );
}

/** Scope-only link (no course) for this program×major. */
function isProgramMajorScopeOnPanel(
  programId: string,
  majorId: number,
  linkedItems: WizardCourseOfferingItem[]
): boolean {
  const normalized = normalizeProgramId(programId);
  if (!normalized || majorId <= 0) return false;
  return linkedItems.some(
    item =>
      isLinkedAcademicItem(item) &&
      Number(item.course_id) === 0 &&
      Number(item.major_id) === majorId &&
      normalizeProgramId(item.program_id) === normalized
  );
}

/** True when every catalog course for this major is already linked under the program. */
function areAllCatalogCoursesLinkedForPair(
  programId: string,
  majorId: number,
  catalogCourses: CourseRecord[],
  linkedItems: WizardCourseOfferingItem[]
): boolean {
  const normalized = normalizeProgramId(programId);
  if (!normalized || majorId <= 0) return false;
  const coursesForMajor = catalogCourses.filter(course =>
    courseCatalogMajorIdsOf(course).includes(majorId)
  );
  if (coursesForMajor.length === 0) return false;
  return coursesForMajor.every(course =>
    isCourseAffiliationOnPanel(course.id, normalized, majorId, linkedItems)
  );
}

/** Pending program×major affiliations for a course under the current selection/context. */
function getPendingCourseAffiliations(
  course: CourseRecord,
  options: {
    selectedProgramMajorValues: string[];
    majorInstances: EducationMajorRecord[];
    linkedItems: WizardCourseOfferingItem[];
    relevantMajorIds: number[];
  }
): Array<{ programId: string; majorId: number }> {
  const courseMajorIds = new Set(courseCatalogMajorIdsOf(course));
  if (courseMajorIds.size === 0) return [];

  const relevantMajorIds = new Set(
    options.relevantMajorIds.filter(id => courseMajorIds.has(id))
  );
  const pending: Array<{ programId: string; majorId: number }> = [];
  const seen = new Set<string>();

  const pushIfPending = (programId: string, majorId: number) => {
    const normalized = normalizeProgramId(programId);
    if (!normalized || majorId <= 0 || !courseMajorIds.has(majorId)) return;
    if (relevantMajorIds.size > 0 && !relevantMajorIds.has(majorId)) return;
    if (isCourseAffiliationOnPanel(course.id, normalized, majorId, options.linkedItems)) {
      return;
    }
    const key = `${normalized}|${majorId}`;
    if (seen.has(key)) return;
    seen.add(key);
    pending.push({ programId: normalized, majorId });
  };

  for (const value of options.selectedProgramMajorValues) {
    const { programId, majorId } = parseProgramMajorValue(value);
    if (majorId > 0) {
      pushIfPending(programId, majorId);
      continue;
    }
    if (!programId) continue;
    for (const major of options.majorInstances) {
      if (normalizeProgramId(major.program_id) === programId) {
        pushIfPending(programId, major.id);
      }
    }
  }

  // When selection is empty/cleared after a sibling major was linked, still surface
  // pending affiliations for other relevant majors (e.g. Civil after Mechanical).
  if (pending.length === 0) {
    for (const major of options.majorInstances) {
      if (!courseMajorIds.has(major.id)) continue;
      if (relevantMajorIds.size > 0 && !relevantMajorIds.has(major.id)) continue;
      const programId = normalizeProgramId(major.program_id);
      if (programId) pushIfPending(programId, major.id);
    }
  }

  return pending;
}

function isProgramScopeOnPanel(
  programId: string,
  linkedItems: WizardCourseOfferingItem[]
): boolean {
  const normalized = normalizeProgramId(programId);
  if (!normalized) return false;
  return linkedItems.some(
    item =>
      isLinkedAcademicItem(item) &&
      Number(item.course_id) === 0 &&
      Number(item.major_id) === 0 &&
      normalizeProgramId(item.program_id) === normalized
  );
}

function isMajorInstanceScopeOnPanel(
  major: EducationMajorRecord,
  linkedItems: WizardCourseOfferingItem[]
): boolean {
  return isProgramMajorPairOnPanel(major.program_id, major.id, linkedItems);
}

/** True when any linked scope or course already covers this program×major pair. */
function isProgramMajorPairOnPanel(
  programId: string,
  majorId: number,
  linkedItems: WizardCourseOfferingItem[]
): boolean {
  const normalized = normalizeProgramId(programId);
  if (!normalized || majorId <= 0) return false;
  return linkedItems.some(
    item =>
      isLinkedAcademicItem(item) &&
      normalizeProgramId(item.program_id) === normalized &&
      Number(item.major_id) === majorId
  );
}

function isProgramMajorValueUnavailable(
  programId: string,
  majorId: number,
  linkedItems: WizardCourseOfferingItem[],
  scopeKeys: Set<string>,
  catalogCourses: CourseRecord[] = []
): boolean {
  const normalizedProgramId = normalizeProgramId(programId);
  if (!normalizedProgramId) return false;

  if (isProgramScopeOnPanel(normalizedProgramId, linkedItems)) {
    return true;
  }
  if (scopeKeysIncludeProgramScope(scopeKeys, normalizedProgramId)) {
    return true;
  }

  if (majorId > 0) {
    // Scope-only link fully consumes this program×major option.
    if (isProgramMajorScopeOnPanel(normalizedProgramId, majorId, linkedItems)) {
      return true;
    }
    if (scopeKeysIncludeMajorScope(scopeKeys, normalizedProgramId, majorId)) {
      return true;
    }
    // Linking one course must not hide sibling catalog courses for the same pair.
    // Only hide once every catalog course for this major is linked under the program.
    if (
      areAllCatalogCoursesLinkedForPair(
        normalizedProgramId,
        majorId,
        catalogCourses,
        linkedItems
      )
    ) {
      return true;
    }
    return false;
  }

  // Program-only option: unavailable once any offering for this program is linked.
  return linkedItems.some(
    item =>
      isLinkedAcademicItem(item) &&
      normalizeProgramId(item.program_id) === normalizedProgramId
  );
}

function scopeGroupKey(offering: WizardCourseOfferingItem): string {
  return `scope-group:${offering.level_id}|${normalizeProgramId(offering.program_id)}`;
}

function mergeMajorNames(...names: string[]): string {
  const seen = new Set<string>();
  const ordered: string[] = [];
  for (const name of names) {
    const trimmed = name.trim();
    if (!trimmed || trimmed === '—') continue;
    const key = trimmed.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    ordered.push(trimmed);
  }
  return ordered.length > 0 ? ordered.join(', ') : '—';
}

function scopeKeysIncludeProgramScope(scopeKeys: Set<string>, programId: string): boolean {
  const normalized = normalizeProgramId(programId);
  if (!normalized) return false;
  for (const key of scopeKeys) {
    if (!key.startsWith('scope:')) continue;
    const parts = key.slice('scope:'.length).split('|');
    if (parts.length < 3) continue;
    if (normalizeProgramId(parts[1]) === normalized && parts[2] === '0') {
      return true;
    }
  }
  return false;
}

function scopeKeysIncludeMajorScope(
  scopeKeys: Set<string>,
  programId: string,
  majorId: number
): boolean {
  const normalized = normalizeProgramId(programId);
  if (!normalized || majorId <= 0) return false;
  for (const key of scopeKeys) {
    if (!key.startsWith('scope:')) continue;
    const parts = key.slice('scope:'.length).split('|');
    if (parts.length < 3) continue;
    if (normalizeProgramId(parts[1]) === normalized && parts[2] === String(majorId)) {
      return true;
    }
  }
  return false;
}

function linkedRowKey(course: SavedCourseOffering, index: number): string {
  return course.local_id || `${academicEntryKey(course)}@${index}`;
}

function parseDisplayLabelParts(displayLabel?: string | null): string[] {
  return displayLabel?.split('>').map(part => part.trim()).filter(Boolean) ?? [];
}

function resolveLinkedAcademicRow(
  offering: SavedCourseOffering,
  context: {
    levels: { id: number; name: string }[];
    programLookup: Map<string, DegreeRecord>;
    majorInstances: EducationMajorRecord[];
    catalogLookup: Map<number, CourseRecord>;
  }
) {
  const labelParts = parseDisplayLabelParts(offering.display_label);
  const hasCourse = Number(offering.course_id) > 0;

  if (labelParts.length > 0) {
    const levelName =
      context.levels.find(level => level.id === offering.level_id)?.name?.trim() ||
      labelParts[0] ||
      '—';

    if (!hasCourse) {
      return {
        levelName,
        programName: labelParts[1] ?? '—',
        majorName: labelParts[2] ?? '—',
        courseName: '—',
      };
    }

    return {
      levelName,
      programName: labelParts[1] ?? '—',
      majorName: labelParts[2] ?? '—',
      courseName: labelParts[3] ?? labelParts.at(-1) ?? `Course #${offering.course_id}`,
    };
  }

  const levelName =
    context.levels.find(level => level.id === offering.level_id)?.name?.trim() ||
    '—';

  if (!hasCourse) {
    const programName =
      (offering.program_id?.trim()
        ? context.programLookup.get(normalizeProgramId(offering.program_id))?.name?.trim() ||
          context.programLookup.get(offering.program_id)?.name?.trim()
        : undefined) || '—';
    const majorName =
      (offering.major_id
        ? context.majorInstances.find(item => item.id === offering.major_id)?.label?.trim()
        : undefined) || '—';

    return { levelName, programName, majorName, courseName: '—' };
  }

  const program = offering.program_id?.trim()
    ? context.programLookup.get(normalizeProgramId(offering.program_id)) ||
      context.programLookup.get(offering.program_id)
    : undefined;
  const programName = program?.name?.trim() || (offering.program_id?.trim() ? '—' : '—');
  const major = offering.major_id
    ? context.majorInstances.find(item => item.id === offering.major_id)
    : undefined;
  const majorName = major?.label?.trim() || (offering.major_id ? '—' : '—');

  const catalogCourse = context.catalogLookup.get(offering.course_id);
  const courseName =
    catalogCourse?.name ||
    catalogCourse?.label ||
    `Course #${offering.course_id}`;

  return { levelName, programName, majorName, courseName };
}

function lookupProgramRecord(
  offering: WizardCourseOfferingItem,
  context: {
    programLookup: Map<string, DegreeRecord>;
  }
): DegreeRecord | undefined {
  const programId = offering.program_id?.trim();
  if (!programId) return undefined;
  return (
    context.programLookup.get(normalizeProgramId(programId)) ||
    context.programLookup.get(programId)
  );
}

/**
 * Majors to list this offering under. One-major offerings stay in that group;
 * program-scope rows (no major_id) expand to every mapped major when known.
 */
function resolveOfferingMajorGroups(
  offering: SavedCourseOffering,
  row: { majorName: string },
  context: {
    programLookup: Map<string, DegreeRecord>;
    majorInstances: EducationMajorRecord[];
    catalogLookup: Map<number, CourseRecord>;
  }
): Array<{ id: number; name: string }> {
  const offeringMajorId = Number(offering.major_id) || 0;
  if (offeringMajorId > 0) {
    const fromInstance = context.majorInstances.find(item => item.id === offeringMajorId);
    const catalogCourse =
      Number(offering.course_id) > 0 ? context.catalogLookup.get(offering.course_id) : undefined;
    const name =
      (row.majorName && row.majorName !== '—' ? row.majorName : '') ||
      fromInstance?.label?.trim() ||
      catalogCourse?.major_name?.trim() ||
      '';
    return [{ id: offeringMajorId, name: majorGroupHeading(name) }];
  }

  const program = lookupProgramRecord(offering, context);
  const groups: Array<{ id: number; name: string }> = [];
  const seen = new Set<string>();
  const push = (id: number, name: string) => {
    const heading = majorGroupHeading(name);
    const key = `${id}|${heading.toLowerCase()}`;
    if (seen.has(key)) return;
    seen.add(key);
    groups.push({ id, name: heading });
  };

  const ids = [...(program?.major_ids ?? [])];
  const names = [...(program?.major_names ?? [])];
  if (ids.length > 0) {
    ids.forEach((id, index) => {
      const fromInstance = context.majorInstances.find(item => item.id === id);
      push(id, names[index] || fromInstance?.label || '');
    });
  } else if (names.length > 0) {
    names.forEach(name => push(0, name));
  }

  const programId = normalizeProgramId(offering.program_id);
  if (groups.length === 0 && programId) {
    for (const major of context.majorInstances) {
      if (normalizeProgramId(major.program_id) === programId) {
        push(major.id, major.label);
      }
    }
  }

  const catalogCourse =
    Number(offering.course_id) > 0 ? context.catalogLookup.get(offering.course_id) : undefined;
  if (groups.length === 0 && catalogCourse) {
    const catalogIds = courseCatalogMajorIdsOf(catalogCourse);
    if (catalogIds.length > 0) {
      catalogIds.forEach((id, index) => {
        const fromInstance = context.majorInstances.find(item => item.id === id);
        push(
          id,
          catalogCourse.major_names?.[index] ||
            catalogCourse.major_name ||
            fromInstance?.label ||
            ''
        );
      });
    } else if (catalogCourse.major_names?.length) {
      catalogCourse.major_names.forEach(name => push(0, name));
    } else if (catalogCourse.major_name) {
      push(Number(catalogCourse.major_id) || 0, catalogCourse.major_name);
    }
  }

  if (groups.length === 0) {
    return [{ id: 0, name: majorGroupHeading(row.majorName) }];
  }
  return groups;
}

const InstitutionWizardStep4 = forwardRef<
  WizardStepHandle<WizardCourseOfferingItem[]>,
  InstitutionWizardStep4Props
>(({
  defaultCourses,
  layout = 'flat',
  colleges = [],
  institutionName = 'University',
  defaultCollegeOverrides = [],
  onPersistCourses,
  onAddCollege,
  onRemoveCollege,
}, ref) => {
  const isHierarchy = layout === 'hierarchy';
  const openConfirm = useConfirmation();
  const { levels } = useAcademiaLevels();
  const [courses, setCourses] = useState<SavedCourseOffering[]>([]);
  const [listError, setListError] = useState<string | null>(null);
  const [selectionError, setSelectionError] = useState<string | null>(null);
  const lastValidationErrorRef = useRef<string | null>(null);
  const [fullyMappedCourseProgramLabels, setFullyMappedCourseProgramLabels] = useState<string[]>(
    []
  );
  const [addCollegeOpen, setAddCollegeOpen] = useState(false);

  const [levelId, setLevelId] = useState<number>(0);
  const [selectedProgramMajorValues, setSelectedProgramMajorValues] = useState<string[]>([]);
  const [selectedCourseIds, setSelectedCourseIds] = useState<number[]>([]);

  const [programs, setPrograms] = useState<DegreeRecord[]>([]);
  const [programMajorOptions, setProgramMajorOptions] = useState<ProgramMajorOption[]>([]);
  const [majorInstances, setMajorInstances] = useState<EducationMajorRecord[]>([]);
  const [majors, setMajors] = useState<EducationMajorRecord[]>([]);
  const [catalogCourses, setCatalogCourses] = useState<CourseRecord[]>([]);
  const [loadingPrograms, setLoadingPrograms] = useState(false);
  const [loadingMajors, setLoadingMajors] = useState(false);
  const [loadingCatalog, setLoadingCatalog] = useState(false);

  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [selectedLinkedRowKeys, setSelectedLinkedRowKeys] = useState<Set<string>>(new Set());
  const [panelSearch, setPanelSearch] = useState('');
  const [panelSortBy, setPanelSortBy] = useState<LinkedPanelSortColumn>('level');
  const [panelSortDir, setPanelSortDir] = useState<'asc' | 'desc'>('asc');
  const [panelPage, setPanelPage] = useState(1);
  const [panelPageSize, setPanelPageSize] = useState(DEFAULT_LINKED_ACADEMICS_PAGE_SIZE);
  const [panelEnrichment, setPanelEnrichment] = useState<{
    programLookup: Map<string, DegreeRecord>;
    majorInstances: EducationMajorRecord[];
    catalogLookup: Map<number, CourseRecord>;
  }>({
    programLookup: new Map(),
    majorInstances: [],
    catalogLookup: new Map(),
  });
  const [panelEnriching, setPanelEnriching] = useState(false);
  const [activeScopeKey, setActiveScopeKey] = useState(institutionScopeKey());
  const [cascadeToColleges, setCascadeToColleges] = useState(true);
  const [collegeOverrides, setCollegeOverrides] = useState<Set<string>>(
    () => new Set(defaultCollegeOverrides)
  );
  const cascadeSourceRef = useRef<CascadeSource>(null);
  const preserveCourseSelectionRef = useRef(false);
  const preserveSelectionOnNextLoadRef = useRef(false);
  const [editingAcademicGroup, setEditingAcademicGroup] = useState<EditingAcademicGroup | null>(
    null
  );

  useEffect(() => {
    setCollegeOverrides(new Set(defaultCollegeOverrides));
  }, [defaultCollegeOverrides]);

  const activeScope = useMemo((): WizardAcademicsEntityScope => {
    if (activeScopeKey.startsWith('college:')) {
      const collegeLocalId = activeScopeKey.slice('college:'.length);
      const college = colleges.find(item => (item.local_id || item.name) === collegeLocalId);
      return {
        type: 'college',
        collegeLocalId,
        collegeName: college?.name || 'College',
        collegeId: college?.id ?? null,
      };
    }
    return { type: 'institution' };
  }, [activeScopeKey, colleges]);

  const programLookup = useMemo(
    () => new Map(programs.map(program => [normalizeProgramId(program.id), program])),
    [programs]
  );
  const majorLookup = useMemo(
    () => new Map(majors.map(major => [major.id, major])),
    [majors]
  );
  const catalogLookup = useMemo(
    () => new Map(catalogCourses.map(course => [course.id, course])),
    [catalogCourses]
  );

  const selectedProgramIds = useMemo(
    () => [
      ...new Set(
        selectedProgramMajorValues
          .map(value => parseProgramMajorValue(value).programId)
          .filter(Boolean)
      ),
    ],
    [selectedProgramMajorValues]
  );

  const selectedMajorKeys = useMemo(() => {
    const keys: string[] = [];
    for (const value of selectedProgramMajorValues) {
      const { majorId } = parseProgramMajorValue(value);
      if (majorId <= 0) continue;
      const major =
        majorInstances.find(item => item.id === majorId) || majors.find(item => item.id === majorId);
      if (major) keys.push(majorIdentityKey(major));
      else keys.push(String(majorId));
    }
    return [...new Set(keys)];
  }, [majorInstances, majors, selectedProgramMajorValues]);

  const selectedMajorIds = useMemo(
    () => [
      ...new Set(
        selectedProgramMajorValues
          .map(value => parseProgramMajorValue(value).majorId)
          .filter(id => id > 0)
      ),
    ],
    [selectedProgramMajorValues]
  );

  const linkedAcademicItems = useMemo(
    () => courses.filter(isLinkedAcademicItem),
    [courses]
  );

  const effectiveLinkedAcademicItems = useMemo(() => {
    if (!isHierarchy) return linkedAcademicItems;
    return filterOfferingsForScope(linkedAcademicItems, activeScope, {
      collegeOverrides,
      includeInherited:
        activeScope.type === 'college' &&
        !collegeOverrides.has(activeScope.collegeLocalId),
    });
  }, [activeScope, collegeOverrides, isHierarchy, linkedAcademicItems]);

  const linkedCourseIds = useMemo(
    () =>
      new Set(
        effectiveLinkedAcademicItems
          .filter(course => Number(course.course_id) > 0)
          .map(course => course.course_id)
      ),
    [effectiveLinkedAcademicItems]
  );

  const linkedScopeKeys = useMemo(
    () =>
      new Set(
        effectiveLinkedAcademicItems
          .filter(item => Number(item.course_id) === 0)
          .map(academicEntryKey)
      ),
    [effectiveLinkedAcademicItems]
  );

  const editExcludedIndexSet = useMemo(() => {
    if (!editingAcademicGroup) return null;
    return new Set([
      ...editingAcademicGroup.replaceIndices,
      ...editingAcademicGroup.sourceIndices,
    ]);
  }, [editingAcademicGroup]);

  /** Linked items used by selectors while editing (current group treated as not yet linked). */
  const linkedItemsForSelectors = useMemo(() => {
    if (!editExcludedIndexSet || editExcludedIndexSet.size === 0) {
      return effectiveLinkedAcademicItems;
    }
    const effectiveSet = new Set(effectiveLinkedAcademicItems);
    return courses.filter(
      (offering, index) => !editExcludedIndexSet.has(index) && effectiveSet.has(offering)
    );
  }, [courses, editExcludedIndexSet, effectiveLinkedAcademicItems]);

  const linkedScopeKeysForSelectors = useMemo(
    () =>
      new Set(
        linkedItemsForSelectors
          .filter(item => Number(item.course_id) === 0)
          .map(academicEntryKey)
      ),
    [linkedItemsForSelectors]
  );

  /** Majors that drive the Course catalog: current selection plus already-linked scopes. */
  const courseCatalogMajorIds = useMemo(() => {
    const ids = new Set<number>();

    for (const majorId of selectedMajorIds) {
      ids.add(majorId);
    }

    // Program-only selections: include every mapped major under those programs.
    for (const value of selectedProgramMajorValues) {
      const { programId, majorId } = parseProgramMajorValue(value);
      if (majorId > 0 || !programId) continue;
      for (const major of majorInstances) {
        if (normalizeProgramId(major.program_id) === programId) {
          ids.add(major.id);
        }
      }
    }

    // Keep courses available for selected majors and for already-linked majors that
    // still have pending multi-major course affiliations.
    for (const item of effectiveLinkedAcademicItems) {
      if (levelId > 0 && Number(item.level_id) > 0 && Number(item.level_id) !== levelId) {
        continue;
      }
      const majorId = Number(item.major_id) || 0;
      if (majorId > 0) {
        ids.add(majorId);
        continue;
      }
      const programId = normalizeProgramId(item.program_id);
      if (!programId) continue;
      for (const major of majorInstances) {
        if (normalizeProgramId(major.program_id) === programId) {
          ids.add(major.id);
        }
      }
    }

    return [...ids];
  }, [
    levelId,
    effectiveLinkedAcademicItems,
    majorInstances,
    selectedMajorIds,
    selectedProgramMajorValues,
  ]);

  // Intentionally do not reset Level/Program/Course when switching university ↔ college.
  // Selectors must stay visible and retain their values on every entity panel.

  const isMajorUnavailable = useCallback(
    (
      major: EducationMajorRecord,
      options?: {
        scopeKeys?: Set<string>;
        linkedCourses?: Set<number>;
        linkedItems?: WizardCourseOfferingItem[];
      }
    ) => {
      const scopeKeys = options?.scopeKeys ?? linkedScopeKeys;
      const linkedItems = options?.linkedItems ?? effectiveLinkedAcademicItems;
      const programId = normalizeProgramId(major.program_id);

      // Program-only scope covers every major under the program.
      if (isProgramScopeOnPanel(programId, linkedItems)) {
        return true;
      }
      if (scopeKeysIncludeProgramScope(scopeKeys, programId)) {
        return true;
      }
      // This program×major pair is already on the list (scope or course row).
      if (isProgramMajorPairOnPanel(programId, major.id, linkedItems)) {
        return true;
      }
      if (scopeKeysIncludeMajorScope(scopeKeys, programId, major.id)) {
        return true;
      }

      return false;
    },
    [effectiveLinkedAcademicItems, linkedScopeKeys]
  );

  const isProgramUnavailable = useCallback(
    (
      programId: string,
      options?: {
        scopeKeys?: Set<string>;
        linkedCourses?: Set<number>;
        linkedItems?: WizardCourseOfferingItem[];
      }
    ) => {
      const scopeKeys = options?.scopeKeys ?? linkedScopeKeys;
      const linkedCourses = options?.linkedCourses ?? linkedCourseIds;
      const linkedItems = options?.linkedItems ?? effectiveLinkedAcademicItems;
      const normalizedProgramId = normalizeProgramId(programId);

      // Whole program is only blocked when a program-only scope is linked.
      if (isProgramScopeOnPanel(normalizedProgramId, linkedItems)) {
        return true;
      }
      if (scopeKeysIncludeProgramScope(scopeKeys, normalizedProgramId)) {
        return true;
      }

      const instances = majorInstances.filter(
        major => normalizeProgramId(major.program_id) === normalizedProgramId
      );
      const programCourses = catalogCourses.filter(
        course => normalizeProgramId(course.degree_id) === normalizedProgramId
      );

      if (instances.length === 0 && programCourses.length === 0) {
        return false;
      }

      const majorsDone =
        instances.length === 0 ||
        instances.every(major =>
          isMajorUnavailable(major, { scopeKeys, linkedCourses, linkedItems })
        );
      const coursesDone =
        programCourses.length === 0 ||
        programCourses.every(course => linkedCourses.has(course.id));

      return majorsDone && coursesDone;
    },
    [
      catalogCourses,
      isMajorUnavailable,
      effectiveLinkedAcademicItems,
      linkedCourseIds,
      linkedScopeKeys,
      majorInstances,
    ]
  );

  const syncDropdownsAfterListChange = useCallback(
    (linkedItems: SavedCourseOffering[], reason: 'add' | 'unlink') => {
      // Never hide/reset Level/Program/Course controls after list changes.
      // Only drop selections that are no longer addable for the current level.
      if (reason === 'unlink') {
        return;
      }

      const scopeKeys = new Set(
        linkedItems
          .filter(item => Number(item.course_id) === 0)
          .map(academicEntryKey)
      );

      const remainingProgramMajorValues = selectedProgramMajorValues.filter(value => {
        const { programId, majorId } = parseProgramMajorValue(value);
        return !isProgramMajorValueUnavailable(
          programId,
          majorId,
          linkedItems,
          scopeKeys,
          catalogCourses
        );
      });
      const syncAffiliationContext = {
        selectedProgramMajorValues: remainingProgramMajorValues,
        majorInstances,
        linkedItems,
        relevantMajorIds: courseCatalogMajorIds,
      };
      const remainingCourseIds = catalogCourses
        .filter(
          course => getPendingCourseAffiliations(course, syncAffiliationContext).length > 0
        )
        .map(course => course.id);
      const remainingSelectedCourseIds = selectedCourseIds.filter(courseId =>
        remainingCourseIds.includes(courseId)
      );

      preserveCourseSelectionRef.current = true;
      setSelectedProgramMajorValues(remainingProgramMajorValues);
      setSelectedCourseIds(
        remainingSelectedCourseIds.length > 0 ? remainingSelectedCourseIds : []
      );
    },
    [
      catalogCourses,
      courseCatalogMajorIds,
      majorInstances,
      selectedCourseIds,
      selectedProgramMajorValues,
    ]
  );

  const loadPrograms = useCallback(async (
    nextLevelId: number,
    options?: { preserveSelection?: boolean }
  ) => {
    setLoadingPrograms(true);
    setLoadingMajors(true);
    try {
      const data = await fetchAcademiaListItems<DegreeRecord>('academia/degrees', {
        level_id: String(nextLevelId),
        active_only: 'true',
      });
      setPrograms(data);

      const mappings = await apiFetch<ProgramMajorMappingListResponse>(
        'academia/program-major-mappings'
      );
      const programIds = new Set(data.map(program => normalizeProgramId(program.id)));
      const mapped = (mappings.items || []).filter(item =>
        programIds.has(normalizeProgramId(item.program_id))
      );

      const instances: EducationMajorRecord[] = mapped.map(item => ({
        id: item.education_major_id,
        label: item.major_label,
        code: item.major_code ?? null,
        color: item.major_color ?? null,
        program_id: String(item.program_id),
        program_name: item.program_name ?? null,
        level_id: item.level_id ?? null,
        level_name: item.level_name ?? null,
        is_other: false,
        sort_order: 0,
        is_active: true,
      }));
      const deduped = dedupeMajorsByLabel(instances);
      setMajorInstances(instances);
      setMajors(deduped);

      const nextOptions: ProgramMajorOption[] = [];
      for (const program of data) {
        const programId = String(program.id);
        const programMappings = mapped.filter(
          item => normalizeProgramId(item.program_id) === normalizeProgramId(programId)
        );
        if (programMappings.length === 0) {
          nextOptions.push({
            value: encodeProgramMajorValue(programId, 0),
            label: program.name,
            programId,
            majorId: 0,
          });
          continue;
        }
        for (const mapping of programMappings) {
          nextOptions.push({
            value: encodeProgramMajorValue(programId, mapping.education_major_id),
            label: `${program.name} — ${mapping.major_label}`,
            programId,
            majorId: mapping.education_major_id,
          });
        }
      }
      setProgramMajorOptions(nextOptions);
      if (!options?.preserveSelection) {
        setSelectedProgramMajorValues([]);
      }
    } catch {
      setPrograms([]);
      setProgramMajorOptions([]);
      setMajorInstances([]);
      setMajors([]);
      setSelectedProgramMajorValues([]);
    } finally {
      setLoadingPrograms(false);
      setLoadingMajors(false);
    }
  }, []);

  useEffect(() => {
    if (!levelId) {
      setPrograms(prev => (prev.length === 0 ? prev : []));
      setProgramMajorOptions(prev => (prev.length === 0 ? prev : []));
      setSelectedProgramMajorValues(prev => (prev.length === 0 ? prev : []));
      setMajorInstances(prev => (prev.length === 0 ? prev : []));
      setMajors(prev => (prev.length === 0 ? prev : []));
      return;
    }
    const preserve = preserveSelectionOnNextLoadRef.current;
    preserveSelectionOnNextLoadRef.current = false;
    void loadPrograms(levelId, { preserveSelection: preserve });
  }, [levelId, loadPrograms]);

  useEffect(() => {
    if (courseCatalogMajorIds.length === 0) {
      setCatalogCourses(prev => (prev.length === 0 ? prev : []));
      setSelectedCourseIds(prev => (prev.length === 0 ? prev : []));
      setLoadingCatalog(false);
      return;
    }

    let cancelled = false;
    setLoadingCatalog(true);

    void Promise.all(
      courseCatalogMajorIds.map(majorId =>
        fetchAcademiaListItems<CourseRecord>('academia/courses', {
          major_id: String(majorId),
        })
      )
    )
      .then(results => {
        if (cancelled) return;
        setCatalogCourses(dedupeById(results.flat()));
      })
      .catch(() => {
        if (!cancelled) {
          setCatalogCourses([]);
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingCatalog(false);
      });

    return () => {
      cancelled = true;
    };
  }, [courseCatalogMajorIds]);

  const courseAffiliationContext = useMemo(
    () => ({
      selectedProgramMajorValues,
      majorInstances,
      linkedItems: linkedItemsForSelectors,
      relevantMajorIds: courseCatalogMajorIds,
    }),
    [
      courseCatalogMajorIds,
      linkedItemsForSelectors,
      majorInstances,
      selectedProgramMajorValues,
    ]
  );

  const addableCourseIds = useMemo(
    () =>
      catalogCourses
        .filter(
          course =>
            (editingAcademicGroup != null && selectedCourseIds.includes(course.id)) ||
            getPendingCourseAffiliations(course, courseAffiliationContext).length > 0
        )
        .map(course => course.id),
    [catalogCourses, courseAffiliationContext, editingAcademicGroup, selectedCourseIds]
  );

  useEffect(() => {
    if (catalogCourses.length === 0) {
      if (preserveCourseSelectionRef.current || editingAcademicGroup) {
        return;
      }
      setSelectedCourseIds(prev => (prev.length === 0 ? prev : []));
      return;
    }

    // Keep only still-valid explicit selections. Do not auto-select catalog courses —
    // courses are optional; empty selection means add program/major scopes instead.
    setSelectedCourseIds(prev => {
      const addable = addableCourseIds;
      if (addable.length === 0) {
        if (preserveCourseSelectionRef.current || editingAcademicGroup) {
          return prev;
        }
        return prev.length === 0 ? prev : [];
      }

      if (preserveCourseSelectionRef.current) {
        preserveCourseSelectionRef.current = false;
      }

      const next = prev.filter(id => addable.includes(id));
      if (next.length === prev.length && next.every((id, index) => id === prev[index])) {
        return prev;
      }
      return next;
    });
  }, [addableCourseIds, catalogCourses.length, editingAcademicGroup]);

  useEffect(() => {
    setSelectedProgramMajorValues(prev => {
      const next = prev.filter(value => {
        const { programId, majorId } = parseProgramMajorValue(value);
        return !isProgramMajorValueUnavailable(
          programId,
          majorId,
          linkedItemsForSelectors,
          linkedScopeKeysForSelectors,
          catalogCourses
        );
      });
      return next.length === prev.length ? prev : next;
    });
    setSelectedCourseIds(prev => {
      const next = prev.filter(courseId => addableCourseIds.includes(courseId));
      if (next.length === prev.length && next.every((id, index) => id === prev[index])) {
        return prev;
      }
      return next;
    });
  }, [addableCourseIds, catalogCourses, linkedItemsForSelectors, linkedScopeKeysForSelectors]);

  const getSnapshot = useCallback(
    () =>
      getWizardListStepSnapshot(
        courses.filter(isLinkedAcademicItem),
        courseOfferingToApiPayload,
        {
          editingIndex: null,
          getDraft: () => ({}),
          emptyDraftTemplate: {},
        }
      ),
    [courses]
  );
  const { markClean, isDirty } = useWizardStepSnapshot(getSnapshot);

  useWizardListStepDefaultsSync(
    defaultCourses,
    () => {
      // Sync the linked list from the draft only. Do not wipe Level/Program/Course
      // selectors — auto-save after unlink rehydrates defaults and used to clear them.
      setEditingIndex(null);
      setFullyMappedCourseProgramLabels([]);

      const linked = defaultCourses.filter(isLinkedAcademicItem).map(hydrateSavedOffering);

      if (!linked.some(offeringNeedsEnrichment)) {
        setCourses(linked);
        setPanelEnrichment(mapsToPanelContext({ courses: new Map(), programs: new Map(), majors: new Map() }));
        setPanelEnriching(false);
        return;
      }

      setPanelEnriching(true);
      void enrichCourseOfferingLabels(linked, levels)
        .then(({ offerings, maps }) => {
          setCourses(offerings);
          setPanelEnrichment(mapsToPanelContext(maps));
        })
        .catch(() => {
          setCourses(linked);
          setPanelEnrichment(
            mapsToPanelContext({ courses: new Map(), programs: new Map(), majors: new Map() })
          );
        })
        .finally(() => {
          setPanelEnriching(false);
        });
    },
    markClean
  );

  const createOfferingsFromCatalog = useCallback(
    (course: CourseRecord): SavedCourseOffering[] => {
      const pendingAffiliations = getPendingCourseAffiliations(
        course,
        courseAffiliationContext
      );
      if (pendingAffiliations.length === 0) return [];

      const offerings: SavedCourseOffering[] = [];
      for (const affiliation of pendingAffiliations) {
        const major =
          majorInstances.find(
            item =>
              item.id === affiliation.majorId &&
              normalizeProgramId(item.program_id) === affiliation.programId
          ) ||
          majorInstances.find(item => item.id === affiliation.majorId) ||
          majorLookup.get(affiliation.majorId);

        const program =
          programLookup.get(affiliation.programId) ||
          programs.find(
            item => normalizeProgramId(item.id) === affiliation.programId
          );
        const canonicalProgramId = program
          ? String(program.id)
          : affiliation.programId;
        const resolvedLevelId = levelId || program?.level_id || major?.level_id || 0;
        if (!resolvedLevelId || !canonicalProgramId.trim()) continue;

        const levelName = levels.find(item => item.id === resolvedLevelId)?.name;
        offerings.push({
          ...hydrateWizardCourseOffering({
            level_id: resolvedLevelId,
            program_id: canonicalProgramId,
            major_id: affiliation.majorId,
            course_id: course.id,
            course_code: course.code || null,
            credits: null,
            syllabus_outline: null,
            program_url: program?.program_url?.trim() || null,
          }),
          display_label: buildDisplayLabel({
            levelName,
            programName: program?.name || course.degree_name || null,
            majorName: major?.label || course.major_name || null,
            courseName: course.name || course.label,
          }),
        });
      }
      return offerings;
    },
    [
      courseAffiliationContext,
      levelId,
      levels,
      majorInstances,
      majorLookup,
      programLookup,
      programs,
    ]
  );

  const linkedAcademics = useMemo(
    () => courses.filter(isLinkedAcademicItem),
    [courses]
  );

  const linkedRowEntries = useMemo(
    () =>
      courses
        .map((course, index) => ({ course, index, key: linkedRowKey(course, index) }))
        .filter(entry => isLinkedAcademicItem(entry.course)),
    [courses]
  );

  const panelRowContext = useMemo(
    () => ({
      levels,
      programLookup: new Map([
        ...panelEnrichment.programLookup.entries(),
        ...programLookup.entries(),
      ]),
      majorInstances: (() => {
        const seen = new Set<string>();
        const merged: EducationMajorRecord[] = [];
        for (const item of [...panelEnrichment.majorInstances, ...majorInstances]) {
          const key = `${item.id}|${normalizeProgramId(item.program_id)}`;
          if (seen.has(key)) continue;
          seen.add(key);
          merged.push(item);
        }
        return merged;
      })(),
      catalogLookup: new Map([
        ...panelEnrichment.catalogLookup.entries(),
        ...catalogLookup.entries(),
      ]),
    }),
    [catalogLookup, levels, majorInstances, panelEnrichment, programLookup]
  );

  const linkedProgramIdsKey = useMemo(
    () =>
      [
        ...new Set(
          courses
            .filter(isLinkedAcademicItem)
            .map(item => normalizeProgramId(item.program_id))
            .filter(Boolean)
        ),
      ]
        .sort()
        .join(','),
    [courses]
  );

  useEffect(() => {
    if (!isHierarchy || !linkedProgramIdsKey) return;
    let cancelled = false;
    void apiFetch<ProgramMajorMappingListResponse>('academia/program-major-mappings')
      .then(mappings => {
        if (cancelled) return;
        const wanted = new Set(linkedProgramIdsKey.split(','));
        const instances: EducationMajorRecord[] = (mappings.items || [])
          .filter(item => wanted.has(normalizeProgramId(item.program_id)))
          .map(item => ({
            id: item.education_major_id,
            label: item.major_label,
            code: item.major_code ?? null,
            color: item.major_color ?? null,
            program_id: String(item.program_id),
            program_name: item.program_name ?? null,
            level_id: item.level_id ?? null,
            level_name: item.level_name ?? null,
            is_other: false,
            sort_order: 0,
            is_active: true,
          }));
        if (instances.length === 0) return;
        setPanelEnrichment(prev => {
          const existing = new Set(
            prev.majorInstances.map(
              item => `${item.id}|${normalizeProgramId(item.program_id)}`
            )
          );
          const extra = instances.filter(
            item => !existing.has(`${item.id}|${normalizeProgramId(item.program_id)}`)
          );
          if (extra.length === 0) return prev;
          return { ...prev, majorInstances: [...prev.majorInstances, ...extra] };
        });
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [isHierarchy, linkedProgramIdsKey]);

  const resolvedPanelRows = useMemo(() => {
    type ResolvedEntry = {
      course: SavedCourseOffering;
      index: number;
      key: string;
      indices: number[];
      row: ReturnType<typeof resolveLinkedAcademicRow>;
      courseItems: Array<{ name: string; index: number; courseId?: number }>;
    };

    const grouped: ResolvedEntry[] = [];
    const scopeGroupIndex = new Map<string, number>();
    const courseGroupIndex = new Map<string, number>();

    for (const entry of linkedRowEntries) {
      const row = resolveLinkedAcademicRow(entry.course, panelRowContext);
      const hasCourse = Number(entry.course.course_id) > 0;
      const isScopeMajor =
        !hasCourse && Number(entry.course.major_id) > 0;

      if (hasCourse) {
        const groupKey = `course-group:${entry.course.level_id}|${normalizeProgramId(
          entry.course.program_id
        )}|${Number(entry.course.major_id) || 0}`;
        const existingIdx = courseGroupIndex.get(groupKey);
        if (existingIdx === undefined) {
          courseGroupIndex.set(groupKey, grouped.length);
          grouped.push({
            ...entry,
            key: groupKey,
            indices: [entry.index],
            row,
            courseItems: [
              {
                name: row.courseName,
                index: entry.index,
                courseId: Number(entry.course.course_id) || undefined,
              },
            ],
          });
          continue;
        }

        const group = grouped[existingIdx];
        group.indices.push(entry.index);
        group.courseItems.push({
          name: row.courseName,
          index: entry.index,
          courseId: Number(entry.course.course_id) || undefined,
        });
        group.row = {
          ...group.row,
          courseName: mergeMajorNames(group.row.courseName, row.courseName),
        };
        continue;
      }

      if (!isScopeMajor) {
        grouped.push({
          ...entry,
          indices: [entry.index],
          row,
          courseItems: [],
        });
        continue;
      }

      const groupKey = scopeGroupKey(entry.course);
      const existingIdx = scopeGroupIndex.get(groupKey);
      if (existingIdx === undefined) {
        scopeGroupIndex.set(groupKey, grouped.length);
        grouped.push({
          ...entry,
          key: groupKey,
          indices: [entry.index],
          row,
          courseItems: [],
        });
        continue;
      }

      const group = grouped[existingIdx];
      group.indices.push(entry.index);
      group.row = {
        ...group.row,
        majorName: mergeMajorNames(group.row.majorName, row.majorName),
      };
    }

    return grouped;
  }, [linkedRowEntries, panelRowContext]);

  useEffect(() => {
    const validKeys = new Set(resolvedPanelRows.map(entry => entry.key));
    setSelectedLinkedRowKeys(prev => {
      const next = new Set([...prev].filter(key => validKeys.has(key)));
      return next.size === prev.size ? prev : next;
    });
  }, [resolvedPanelRows]);

  const allLinkedRowsSelected =
    resolvedPanelRows.length > 0 &&
    resolvedPanelRows.every(entry => selectedLinkedRowKeys.has(entry.key));
  const someLinkedRowsSelected = resolvedPanelRows.some(entry =>
    selectedLinkedRowKeys.has(entry.key)
  );

  const filteredPanelRows = useMemo(() => {
    const needle = panelSearch.trim().toLowerCase();
    let rows = resolvedPanelRows;
    if (needle) {
      rows = rows.filter(({ row }) =>
        [row.levelName, row.programName, row.majorName, row.courseName].some(value =>
          value.toLowerCase().includes(needle)
        )
      );
    }

    const columnKey =
      panelSortBy === 'level'
        ? 'levelName'
        : panelSortBy === 'program'
          ? 'programName'
          : panelSortBy === 'major'
            ? 'majorName'
            : 'courseName';

    return [...rows].sort((left, right) => {
      const comparison = left.row[columnKey].localeCompare(right.row[columnKey], undefined, {
        sensitivity: 'base',
      });
      return panelSortDir === 'asc' ? comparison : -comparison;
    });
  }, [panelSearch, panelSortBy, panelSortDir, resolvedPanelRows]);

  const panelTotalPages = Math.max(1, Math.ceil(filteredPanelRows.length / panelPageSize));

  const paginatedPanelRows = useMemo(() => {
    const start = (panelPage - 1) * panelPageSize;
    return filteredPanelRows.slice(start, start + panelPageSize);
  }, [filteredPanelRows, panelPage, panelPageSize]);

  useEffect(() => {
    setPanelPage(1);
  }, [panelSearch, panelSortBy, panelSortDir, panelPageSize, resolvedPanelRows.length]);

  useEffect(() => {
    if (panelPage > panelTotalPages) {
      setPanelPage(panelTotalPages);
    }
  }, [panelPage, panelTotalPages]);

  const togglePanelSort = useCallback((column: LinkedPanelSortColumn) => {
    setPanelSortBy(current => {
      if (current === column) {
        setPanelSortDir(dir => (dir === 'asc' ? 'desc' : 'asc'));
        return current;
      }
      setPanelSortDir('asc');
      return column;
    });
  }, []);

  const toggleLinkedRowSelection = useCallback((key: string) => {
    setSelectedLinkedRowKeys(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const toggleSelectAllLinkedRows = useCallback(() => {
    setSelectedLinkedRowKeys(prev => {
      if (
        resolvedPanelRows.length > 0 &&
        resolvedPanelRows.every(entry => prev.has(entry.key))
      ) {
        return new Set();
      }
      return new Set(resolvedPanelRows.map(entry => entry.key));
    });
  }, [resolvedPanelRows]);

  const performUnlinkAtIndices = useCallback(
    (
      indices: number[],
      options?: {
        collegeAcademicOverrides?: string[];
        /** When true, still persist even if no rows were removed (override-only change). */
        forcePersist?: boolean;
      }
    ) => {
      if (indices.length === 0 && !options?.forcePersist) return;

      const indexSet = new Set(indices);
      const removedKeys = resolvedPanelRows
        .filter(entry => entry.indices.some(index => indexSet.has(index)))
        .map(entry => entry.key);

      const nextCourses =
        indices.length === 0
          ? courses
          : courses.filter((_, index) => !indexSet.has(index));
      if (indices.length > 0) {
        setCourses(nextCourses);
        setFullyMappedCourseProgramLabels([]);
        setSelectedLinkedRowKeys(prev => {
          const next = new Set(prev);
          for (const key of removedKeys) next.delete(key);
          return next;
        });

        setEditingIndex(current => {
          if (current === null) return null;
          if (indexSet.has(current)) return null;
          const shift = indices.filter(index => index < current).length;
          return shift > 0 ? current - shift : current;
        });
      }

      if (onPersistCourses) {
        const payload = nextCourses
          .filter(isLinkedAcademicItem)
          .map(courseOfferingToApiPayload);
        void onPersistCourses(payload, {
          collegeAcademicOverrides:
            options?.collegeAcademicOverrides ?? [...collegeOverrides],
        });
      }
    },
    [collegeOverrides, courses, onPersistCourses, resolvedPanelRows]
  );

  const handleUnlinkCourse = async (
    course: SavedCourseOffering,
    indices: number[],
    majorLabel?: string
  ) => {
    const label =
      majorLabel && majorLabel !== '—'
        ? `${course.display_label?.split('>')[0]?.trim() || 'Program'} / ${majorLabel}`
        : course.display_label || `Course #${course.course_id}`;
    const confirmed = await openConfirm({
      title: 'Unlink academic?',
      message: `Unlink "${label}" from this institution?\n\nYou can link it again later from the course selector.`,
      confirmLabel: 'Unlink',
      variant: 'warning',
    });
    if (!confirmed) return;

    performUnlinkAtIndices(indices);
  };

  const handleUnlinkSingleCourse = async (index: number, courseName: string) => {
    const confirmed = await openConfirm({
      title: 'Unlink course?',
      message: `Unlink "${courseName}" from this program?\n\nYou can link it again later from the course selector.`,
      confirmLabel: 'Unlink',
      variant: 'warning',
    });
    if (!confirmed) return;

    performUnlinkAtIndices([index]);
  };

  const handleBulkUnlinkSelected = async () => {
    const selectedEntries = resolvedPanelRows.filter(entry =>
      selectedLinkedRowKeys.has(entry.key)
    );
    if (selectedEntries.length === 0) return;

    const confirmed = await openConfirm({
      title: 'Unlink selected academics?',
      message:
        selectedEntries.length === 1
          ? 'Unlink the selected academic from this institution?'
          : `Unlink ${selectedEntries.length} selected academics from this institution?`,
      confirmLabel: 'Unlink',
      variant: 'warning',
    });
    if (!confirmed) return;

    performUnlinkAtIndices(selectedEntries.flatMap(entry => entry.indices));
  };

  const getUnlinkableIndicesForScope = useCallback(
    (scope: WizardAcademicsEntityScope | null, candidateIndices?: number[]): number[] => {
      if (!scope || !isHierarchy) {
        const linkedIndices = courses
          .map((offering, index) => ({ offering, index }))
          .filter(({ offering }) => isLinkedAcademicItem(offering))
          .map(({ index }) => index);
        if (!candidateIndices?.length) return linkedIndices;
        const candidateSet = new Set(candidateIndices);
        return linkedIndices.filter(index => candidateSet.has(index));
      }
      return getUnlinkableIndicesForDisplayedScope(
        courses,
        scope,
        collegeOverrides,
        candidateIndices
      );
    },
    [collegeOverrides, courses, isHierarchy]
  );

  const buildUnlinkScopeMessage = useCallback(
    (
      scope: WizardAcademicsEntityScope,
      indices: number[],
      options?: {
        plural?: boolean;
        programLabel?: string;
        enablingOverride?: boolean;
      }
    ): string => {
      const scopeLabel =
        scope.type === 'college' ? scope.collegeName : institutionName || 'University';
      const count = Math.max(indices.length, options?.enablingOverride ? 1 : 0);

      if (options?.programLabel) {
        if (options.enablingOverride) {
          return `Unlink "${options.programLabel}" from ${scopeLabel}?\n\nThis college will stop inheriting that university academic. The university mapping itself will stay in place.`;
        }
        return `Unlink "${options.programLabel}" from ${scopeLabel}?\n\nYou can link it again later from the selectors below.`;
      }

      if (options?.enablingOverride) {
        return `Remove linked academics shown for ${scopeLabel}?\n\nThis college will use a custom academic list and will no longer inherit university academics. University mappings will not be removed.`;
      }

      return `Remove all ${count} linked program and course mapping${
        count === 1 ? '' : 's'
      } from ${scopeLabel}? You can link them again from the selectors below.`;
    },
    [institutionName]
  );

  const handleUnlinkAllLinkedAcademics = useCallback(async () => {
    const indices = getUnlinkableIndicesForScope(null);
    if (indices.length === 0) return;

    const confirmed = await openConfirm({
      title: 'Unlink all academics?',
      message: `Remove all ${indices.length} linked program and course mapping${
        indices.length === 1 ? '' : 's'
      } from this institution? You can link them again from the selectors below.`,
      confirmLabel: 'Unlink all',
      variant: 'warning',
    });
    if (!confirmed) return;

    performUnlinkAtIndices(indices);
  }, [getUnlinkableIndicesForScope, openConfirm, performUnlinkAtIndices]);

  const resolveUnlinkIndicesForScope = useCallback(
    (scope: WizardAcademicsEntityScope, candidateIndices?: number[]): number[] => {
      if (scope.type === 'college') {
        return getCollegeOwnedUnlinkIndices(
          courses,
          scope.collegeLocalId,
          candidateIndices,
          scope.collegeId
        );
      }
      let indices = getUnlinkableIndicesForScope(scope, candidateIndices);
      indices = expandInstitutionUnlinkIndices(courses, indices, collegeOverrides);
      return indices;
    },
    [collegeOverrides, courses, getUnlinkableIndicesForScope]
  );

  const enableCollegeOverride = useCallback((collegeLocalId: string): string[] => {
    const next = new Set(collegeOverrides);
    next.add(collegeLocalId);
    const list = [...next];
    setCollegeOverrides(next);
    return list;
  }, [collegeOverrides]);

  const handleUnlinkAllInScope = useCallback(
    async (scope: WizardAcademicsEntityScope) => {
      const enablingOverride =
        scope.type === 'college' && !collegeOverrides.has(scope.collegeLocalId);
      const indices = resolveUnlinkIndicesForScope(scope);
      if (indices.length === 0 && !enablingOverride) return;

      const confirmed = await openConfirm({
        title: 'Unlink all academics?',
        message: buildUnlinkScopeMessage(scope, indices, { enablingOverride }),
        confirmLabel: 'Unlink all',
        variant: 'warning',
      });
      if (!confirmed) return;

      const overrides =
        scope.type === 'college'
          ? enableCollegeOverride(scope.collegeLocalId)
          : [...collegeOverrides];

      performUnlinkAtIndices(indices, {
        collegeAcademicOverrides: overrides,
        forcePersist: enablingOverride && indices.length === 0,
      });
    },
    [
      buildUnlinkScopeMessage,
      collegeOverrides,
      enableCollegeOverride,
      openConfirm,
      performUnlinkAtIndices,
      resolveUnlinkIndicesForScope,
    ]
  );

  const handleSaveCourseEdit = (index: number, values: WizardCourseEditValues) => {
    setCourses(prev =>
      prev.map((item, itemIndex) =>
        itemIndex === index
          ? {
              ...item,
              course_code: values.course_code || null,
              credits: values.credits ?? null,
              syllabus_outline: values.syllabus_outline || null,
            }
          : item
      )
    );
    setListError(null);
    return true;
  };

  useImperativeHandle(ref, () => ({
    validate: async () => {
      if (editingIndex !== null) {
        const message = 'Save or close the open course edit panel before continuing.';
        lastValidationErrorRef.current = message;
        setListError(message);
        return false;
      }
      const linkedAcademicsList = courses.filter(isLinkedAcademicItem);
      const parsed = wizardCoursesStepSchema.safeParse(linkedAcademicsList);
      if (!parsed.success) {
        const message =
          parsed.error.issues[0]?.message || 'Fix course offering errors before continuing.';
        lastValidationErrorRef.current = message;
        setListError(message);
        return false;
      }
      lastValidationErrorRef.current = null;
      setListError(null);
      return true;
    },
    getValues: () => courses.filter(isLinkedAcademicItem).map(courseOfferingToApiPayload),
    reset: values => {
      setCourses(values.map(item => hydrateWizardCourseOffering(item)));
      setEditingIndex(null);
      markClean();
    },
    isDirty,
    markClean: () => {
      setEditingIndex(null);
      markClean();
    },
    getValidationError: () => lastValidationErrorRef.current,
    getCollegeAcademicOverrides: () => [...collegeOverrides],
  }));

  const isProgramMajorOptionUnavailable = useCallback(
    (option: ProgramMajorOption) =>
      isProgramMajorValueUnavailable(
        option.programId,
        option.majorId,
        linkedItemsForSelectors,
        linkedScopeKeysForSelectors,
        catalogCourses
      ),
    [catalogCourses, linkedItemsForSelectors, linkedScopeKeysForSelectors]
  );

  const availableProgramOptions = useMemo(() => {
    const available = programMajorOptions
      .filter(option => !isProgramMajorOptionUnavailable(option))
      .map(option => ({ value: option.value, label: option.label }));
    if (!editingAcademicGroup) return available;
    const availableValues = new Set(available.map(option => option.value));
    for (const value of selectedProgramMajorValues) {
      if (availableValues.has(value)) continue;
      const option = programMajorOptions.find(item => item.value === value);
      if (option) {
        available.push({ value: option.value, label: option.label });
        availableValues.add(option.value);
      }
    }
    return available;
  }, [
    editingAcademicGroup,
    isProgramMajorOptionUnavailable,
    programMajorOptions,
    selectedProgramMajorValues,
  ]);

  const availableLevelOptions = useMemo(() => levelSelectOptions(levels), [levels]);

  const allProgramsMappedForSelectedLevel =
    levelId > 0 &&
    !loadingPrograms &&
    !loadingMajors &&
    programMajorOptions.length > 0 &&
    availableProgramOptions.length === 0;

  const visibleSelectedProgramMajorValues = useMemo(
    () =>
      selectedProgramMajorValues.filter(value =>
        availableProgramOptions.some(option => option.value === value)
      ),
    [availableProgramOptions, selectedProgramMajorValues]
  );

  const handleProgramChange = useCallback(
    (values: string[]) => {
      cascadeSourceRef.current = 'program';
      setFullyMappedCourseProgramLabels([]);
      const allowed = new Set(availableProgramOptions.map(option => option.value));
      setSelectedProgramMajorValues(values.filter(value => allowed.has(value)));
    },
    [availableProgramOptions]
  );

  const catalogCourseOptions = useMemo(
    () =>
      catalogCourses
        .filter(
          item =>
            selectedCourseIds.includes(item.id) ||
            getPendingCourseAffiliations(item, courseAffiliationContext).length > 0
        )
        .map(item => ({
          value: String(item.id),
          label: item.name || item.label || item.hierarchy_breadcrumb || `Course #${item.id}`,
        })),
    [catalogCourses, courseAffiliationContext, selectedCourseIds]
  );

  const selectableCourseIds = useMemo(
    () => selectedCourseIds.filter(courseId => addableCourseIds.includes(courseId)),
    [addableCourseIds, selectedCourseIds]
  );

  const buildScopeAcademics = useCallback((): SavedCourseOffering[] => {
    const levelName = levels.find(item => item.id === levelId)?.name ?? null;
    const items: SavedCourseOffering[] = [];

    for (const value of selectedProgramMajorValues) {
      const { programId, majorId } = parseProgramMajorValue(value);
      if (!programId) continue;
      const program =
        programLookup.get(programId) ||
        programs.find(item => normalizeProgramId(item.id) === programId);
      const resolvedLevelId = levelId || program?.level_id || 0;
      if (!resolvedLevelId) continue;
      const major =
        majorId > 0
          ? majorInstances.find(item => item.id === majorId) ||
            majors.find(item => item.id === majorId)
          : undefined;
      items.push({
        ...hydrateWizardCourseOffering({
          level_id: resolvedLevelId,
          program_id: program ? String(program.id) : programId,
          major_id: majorId,
          course_id: 0,
          program_url: program?.program_url?.trim() || null,
        }),
        display_label: buildDisplayLabel({
          levelName: levels.find(item => item.id === resolvedLevelId)?.name ?? levelName,
          programName: program?.name ?? null,
          majorName: major?.label ?? null,
        }),
      });
    }

    return items;
  }, [
    levelId,
    levels,
    majorInstances,
    majors,
    programLookup,
    programs,
    selectedProgramMajorValues,
  ]);

  const pendingCourseIdsToAdd = useMemo(() => {
    return selectableCourseIds.filter(courseId => {
      const course = catalogLookup.get(courseId);
      if (!course) return false;
      return getPendingCourseAffiliations(course, courseAffiliationContext).length > 0;
    });
  }, [catalogLookup, courseAffiliationContext, selectableCourseIds]);

  const pendingScopeItemsToAdd = useMemo(() => {
    const existingKeys = new Set(
      courses
        .filter(isLinkedAcademicItem)
        .filter(item => {
          if (!isHierarchy) return true;
          if (activeScope.type === 'institution') {
            return offeringScopeKey(item) === institutionScopeKey();
          }
          return offeringMatchesCollege(item, activeScope);
        })
        .map(academicEntryKey)
    );

    // Program×major pairs that will get real course rows in this Add — skip duplicate scopes.
    const pairsCoveredByPendingCourses = new Set<string>();
    for (const courseId of pendingCourseIdsToAdd) {
      const course = catalogLookup.get(courseId);
      if (!course) continue;
      for (const affiliation of getPendingCourseAffiliations(course, courseAffiliationContext)) {
        pairsCoveredByPendingCourses.add(
          `${normalizeProgramId(affiliation.programId)}|${affiliation.majorId}`
        );
      }
    }

    return buildScopeAcademics().filter(item => {
      if (!item.program_id?.trim()) return false;
      if (
        !item.program_id?.trim() &&
        Number(item.major_id) === 0 &&
        Number(item.course_id) === 0
      ) {
        return false;
      }
      const majorId = Number(item.major_id) || 0;
      if (
        majorId > 0 &&
        pairsCoveredByPendingCourses.has(
          `${normalizeProgramId(item.program_id)}|${majorId}`
        )
      ) {
        return false;
      }
      return !existingKeys.has(academicEntryKey(item));
    });
  }, [
    activeScope,
    buildScopeAcademics,
    catalogLookup,
    courseAffiliationContext,
    courses,
    isHierarchy,
    pendingCourseIdsToAdd,
  ]);

  const canAddAcademics =
    !loadingCatalog &&
    !loadingMajors &&
    (pendingCourseIdsToAdd.length > 0 || pendingScopeItemsToAdd.length > 0);

  const programSelectedDisplay = useMemo(() => {
    const count = visibleSelectedProgramMajorValues.length;
    if (count === 0) return undefined;
    return `${count} program${count === 1 ? '' : 's'} selected`;
  }, [visibleSelectedProgramMajorValues]);

  const courseSelectedDisplay = useMemo(() => {
    const count = selectableCourseIds.length;
    if (count === 0) return undefined;
    return `${count} course${count === 1 ? '' : 's'} selected`;
  }, [selectableCourseIds]);

  const appendScopedOfferings = useCallback(
    (
      rawOfferings: SavedCourseOffering[],
      targetScope: WizardAcademicsEntityScope = activeScope
    ): SavedCourseOffering[] => {
      if (!isHierarchy) {
        return [...courses, ...rawOfferings];
      }

      let nextOverrides = collegeOverrides;
      if (
        targetScope.type === 'college' &&
        !collegeOverrides.has(targetScope.collegeLocalId)
      ) {
        nextOverrides = new Set([...collegeOverrides, targetScope.collegeLocalId]);
        setCollegeOverrides(nextOverrides);
      }

      const stamped = rawOfferings.map(item => stampOfferingScope(item, targetScope));
      const cascaded: SavedCourseOffering[] = [];

      if (targetScope.type === 'institution' && cascadeToColleges && colleges.length > 0) {
        for (const college of colleges) {
          const collegeLocalId = college.local_id || college.name;
          if (!nextOverrides.has(collegeLocalId)) {
            for (const offering of stamped) {
              cascaded.push(cloneOfferingForCollege(offering, college));
            }
          }
        }
      }

      return [...courses, ...stamped, ...cascaded];
    },
    [
      activeScope,
      cascadeToColleges,
      collegeOverrides,
      colleges,
      courses,
      isHierarchy,
    ]
  );

  const clearAcademicEdit = useCallback(() => {
    setEditingAcademicGroup(null);
  }, []);

  const cancelAcademicEdit = useCallback(() => {
    setEditingAcademicGroup(null);
    setSelectionError(null);
    setFullyMappedCourseProgramLabels([]);
    setLevelId(0);
    setSelectedProgramMajorValues([]);
    setSelectedCourseIds([]);
    setMajorInstances([]);
    setMajors([]);
    setProgramMajorOptions([]);
    setCatalogCourses([]);
    cascadeSourceRef.current = null;
  }, []);

  const handleEditProgramGroup = useCallback(
    (scope: WizardAcademicsEntityScope, group: GroupedProgramLink) => {
      const replaceIndices = resolveUnlinkIndicesForScope(scope, group.indices);
      const sourceOfferings = group.indices
        .map(index => courses[index])
        .filter((item): item is SavedCourseOffering => Boolean(item));
      if (sourceOfferings.length === 0) return;

      const nextLevelId =
        sourceOfferings.find(item => Number(item.level_id) > 0)?.level_id || 0;
      const programMajorValues = Array.from(
        new Set(
          sourceOfferings
            .map(item => {
              const programId = normalizeProgramId(item.program_id);
              if (!programId) return '';
              return encodeProgramMajorValue(programId, Number(item.major_id) || 0);
            })
            .filter(Boolean)
        )
      );
      const courseIds = Array.from(
        new Set(
          sourceOfferings
            .map(item => Number(item.course_id) || 0)
            .filter(courseId => courseId > 0)
        )
      );

      const label = [
        group.programName,
        group.majorName && group.majorName !== '—' ? group.majorName : '',
      ]
        .filter(Boolean)
        .join(' — ');

      setEditingAcademicGroup({
        scope,
        replaceIndices,
        sourceIndices: [...group.indices],
        label,
      });
      setActiveScopeKey(scopeKey(scope));
      setSelectionError(null);
      setFullyMappedCourseProgramLabels([]);
      preserveSelectionOnNextLoadRef.current = true;
      preserveCourseSelectionRef.current = true;
      setLevelId(nextLevelId);
      setSelectedProgramMajorValues(programMajorValues);
      setSelectedCourseIds(courseIds);

      if (nextLevelId > 0) {
        void loadPrograms(nextLevelId, { preserveSelection: true }).then(() => {
          setSelectedProgramMajorValues(programMajorValues);
          setSelectedCourseIds(courseIds);
        });
      }

      window.requestAnimationFrame(() => {
        document
          .querySelector('[data-wizard-academics-selectors]')
          ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    },
    [courses, loadPrograms, resolveUnlinkIndicesForScope]
  );

  const handleAddAcademicsToList = (targetScope: WizardAcademicsEntityScope = activeScope) => {
    setSelectionError(null);
    const editTargetScope = editingAcademicGroup?.scope ?? targetScope;
    if (isHierarchy) {
      setActiveScopeKey(scopeKey(editTargetScope));
    }

    if (loadingCatalog || loadingMajors) {
      setSelectionError('Academics are still loading. Please wait a moment and try again.');
      return;
    }

    if (!canAddAcademics) {
      setSelectionError(
        editingAcademicGroup
          ? 'Select a program or course before updating this academic mapping.'
          : 'Select a program or course before adding academics to the list.'
      );
      return;
    }

    const skipIndices = editingAcademicGroup
      ? new Set(editingAcademicGroup.replaceIndices)
      : null;
    const coursesBase = skipIndices
      ? courses.filter((_, index) => !skipIndices.has(index))
      : courses;

    const existingKeys = new Set(
      coursesBase
        .filter(isLinkedAcademicItem)
        .filter(item => {
          if (!isHierarchy) return true;
          if (editTargetScope.type === 'institution') {
            return offeringScopeKey(item) === institutionScopeKey();
          }
          return offeringMatchesCollege(item, editTargetScope);
        })
        .map(academicEntryKey)
    );

    const finishUpdate = (next: SavedCourseOffering[]) => {
      const nextLinkedItems = next.filter(isLinkedAcademicItem);
      const completedProgramLabels = selectedProgramMajorValues.flatMap(value => {
        const { programId, majorId } = parseProgramMajorValue(value);
        if (
          majorId <= 0 ||
          !areAllCatalogCoursesLinkedForPair(
            programId,
            majorId,
            catalogCourses,
            nextLinkedItems
          )
        ) {
          return [];
        }
        const option = programMajorOptions.find(item => item.value === value);
        return [option?.label || `Program ${programId}`];
      });
      setCourses(next);
      setFullyMappedCourseProgramLabels([...new Set(completedProgramLabels)]);
      clearAcademicEdit();
      syncDropdownsAfterListChange(nextLinkedItems, 'add');
      if (levelId > 0) {
        void loadPrograms(levelId, { preserveSelection: true });
      }
      setListError(null);
    };

    const appendOntoBase = (rawOfferings: SavedCourseOffering[]): SavedCourseOffering[] => {
      if (!isHierarchy) {
        return [...coursesBase, ...rawOfferings];
      }

      let nextOverrides = collegeOverrides;
      if (
        editTargetScope.type === 'college' &&
        !collegeOverrides.has(editTargetScope.collegeLocalId)
      ) {
        nextOverrides = new Set([...collegeOverrides, editTargetScope.collegeLocalId]);
        setCollegeOverrides(nextOverrides);
      }

      const stamped = rawOfferings.map(item => stampOfferingScope(item, editTargetScope));
      const cascaded: SavedCourseOffering[] = [];

      if (editTargetScope.type === 'institution' && cascadeToColleges && colleges.length > 0) {
        for (const college of colleges) {
          const collegeLocalId = college.local_id || college.name;
          if (!nextOverrides.has(collegeLocalId)) {
            for (const offering of stamped) {
              cascaded.push(cloneOfferingForCollege(offering, college));
            }
          }
        }
      }

      return [...coursesBase, ...stamped, ...cascaded];
    };

    if (pendingCourseIdsToAdd.length > 0) {
      const nextOfferings = pendingCourseIdsToAdd
        .map(courseId => catalogLookup.get(courseId))
        .filter((course): course is CourseRecord => Boolean(course))
        .flatMap(course => createOfferingsFromCatalog(course))
        .filter(offering => !existingKeys.has(academicEntryKey(offering)));

      const nextScopeItems = pendingScopeItemsToAdd.filter(
        item => !existingKeys.has(academicEntryKey(item))
      );
      const offeringKeys = new Set(nextOfferings.map(academicEntryKey));
      const uniqueScopeItems = nextScopeItems.filter(
        item => !offeringKeys.has(academicEntryKey(item))
      );

      const combined = [...nextOfferings, ...uniqueScopeItems];
      if (combined.length === 0) {
        setSelectionError(
          editingAcademicGroup
            ? 'No changes to apply — selected academics already match the list.'
            : 'Selected academics are already on the list.'
        );
        return;
      }

      finishUpdate(appendOntoBase(combined));
      return;
    }

    const nextScopeItems = pendingScopeItemsToAdd.filter(
      item => !existingKeys.has(academicEntryKey(item))
    );
    if (nextScopeItems.length === 0) {
      setSelectionError(
        editingAcademicGroup
          ? 'No changes to apply — selected academics already match the list.'
          : 'Selected academics are already on the list.'
      );
      return;
    }

    finishUpdate(appendOntoBase(nextScopeItems));
  };

  const groupProgramsForScope = useCallback(
    (_scope: WizardAcademicsEntityScope, offerings: WizardCourseOfferingItem[]) => {
      const offeringSet = new Set(offerings);
      const entries = courses
        .map((offering, index) => ({ offering, index }))
        .filter(({ offering }) => offeringSet.has(offering));
      return groupProgramsForOfferings(entries, offering => {
        const row = resolveLinkedAcademicRow(offering, panelRowContext);
        return {
          ...row,
          programUrl:
            offering.program_url?.trim() ||
            lookupProgramRecord(offering, panelRowContext)?.program_url?.trim() ||
            null,
          majorGroups: resolveOfferingMajorGroups(offering, row, panelRowContext),
        };
      });
    },
    [courses, panelRowContext]
  );

  const handleUnlinkProgramGroup = useCallback(
    async (scope: WizardAcademicsEntityScope, group: { indices: number[]; programName: string; majorName: string }) => {
      const enablingOverride =
        scope.type === 'college' && !collegeOverrides.has(scope.collegeLocalId);
      const indices = resolveUnlinkIndicesForScope(scope, group.indices);
      if (indices.length === 0 && !enablingOverride) return;

      const programLabel = [
        group.programName,
        group.majorName && group.majorName !== '—' ? group.majorName : '',
      ]
        .filter(Boolean)
        .join(' — ');

      const confirmed = await openConfirm({
        title: 'Unlink academic?',
        message: buildUnlinkScopeMessage(scope, indices, {
          programLabel,
          enablingOverride,
        }),
        confirmLabel: 'Unlink',
        variant: 'warning',
      });
      if (!confirmed) return;

      const overrides =
        scope.type === 'college'
          ? enableCollegeOverride(scope.collegeLocalId)
          : [...collegeOverrides];

      performUnlinkAtIndices(indices, {
        collegeAcademicOverrides: overrides,
        forcePersist: enablingOverride && indices.length === 0,
      });
    },
    [
      buildUnlinkScopeMessage,
      collegeOverrides,
      enableCollegeOverride,
      openConfirm,
      performUnlinkAtIndices,
      resolveUnlinkIndicesForScope,
    ]
  );

  const handleToggleCollegeOverride = useCallback(
    (collegeLocalId: string, enabled: boolean) => {
      if (enabled) {
        setCollegeOverrides(prev => new Set([...prev, collegeLocalId]));
        const college = colleges.find(item => (item.local_id || item.name) === collegeLocalId);
        if (!college) return;
        const collegeScope: Extract<WizardAcademicsEntityScope, { type: 'college' }> = {
          type: 'college',
          collegeLocalId,
          collegeName: college.name,
          collegeId: college.id ?? null,
        };
        const institutionOfferings = courses.filter(
          item =>
            isLinkedAcademicItem(item) && offeringScopeKey(item) === institutionScopeKey()
        );
        const existingKeys = new Set(
          courses
            .filter(item => offeringMatchesCollege(item, collegeScope))
            .map(academicEntryKey)
        );
        const toAdd = institutionOfferings
          .map(offering => cloneOfferingForCollege(offering, college))
          .filter(offering => !existingKeys.has(academicEntryKey(offering)));
        if (toAdd.length > 0) {
          setCourses(prev => [...prev, ...toAdd]);
        }
        return;
      }

      setCollegeOverrides(prev => {
        const next = new Set(prev);
        next.delete(collegeLocalId);
        return next;
      });
      const college = colleges.find(item => (item.local_id || item.name) === collegeLocalId);
      const collegeScope: Extract<WizardAcademicsEntityScope, { type: 'college' }> = {
        type: 'college',
        collegeLocalId,
        collegeName: college?.name || '',
        collegeId: college?.id ?? null,
      };
      setCourses(prev => prev.filter(item => !offeringMatchesCollege(item, collegeScope)));
    },
    [colleges, courses]
  );

  const handleCascadeChange = useCallback(
    (enabled: boolean) => {
      setCascadeToColleges(enabled);
      if (!enabled || colleges.length === 0) return;

      const institutionOfferings = courses.filter(
        item =>
          isLinkedAcademicItem(item) && offeringScopeKey(item) === institutionScopeKey()
      );
      const additions: SavedCourseOffering[] = [];
      for (const college of colleges) {
        const collegeLocalId = college.local_id || college.name;
        if (collegeOverrides.has(collegeLocalId)) continue;
        const collegeScope: Extract<WizardAcademicsEntityScope, { type: 'college' }> = {
          type: 'college',
          collegeLocalId,
          collegeName: college.name,
          collegeId: college.id ?? null,
        };
        const existingKeys = new Set(
          courses
            .filter(item => offeringMatchesCollege(item, collegeScope))
            .map(academicEntryKey)
        );
        for (const offering of institutionOfferings) {
          const clone = cloneOfferingForCollege(offering, college);
          if (!existingKeys.has(academicEntryKey(clone))) {
            additions.push(clone);
          }
        }
      }
      if (additions.length > 0) {
        setCourses(prev => [...prev, ...additions]);
      }
    },
    [collegeOverrides, colleges, courses]
  );

  const handleAddCollegeTab = useCallback(() => {
    setAddCollegeOpen(true);
  }, []);

  const validateNewCollegeName = useCallback(
    (name: string) => {
      if (!name.trim()) {
        return 'Enter a valid school or college name.';
      }
      const nameKey = name.trim().toLowerCase();
      if (colleges.some(college => (college.name || '').trim().toLowerCase() === nameKey)) {
        return `A school / college named "${name.trim()}" already exists. Enter a different name.`;
      }
      return null;
    },
    [colleges]
  );

  const handleConfirmAddCollege = useCallback(
    (name: string) => {
      if (validateNewCollegeName(name)) return;
      const college = hydrateWizardCollege({
        ...createEmptyWizardCollegeDraft(),
        name: name.trim(),
      });
      onAddCollege?.(college);
      setActiveScopeKey(collegeScopeKey(college.local_id || college.name));
      setAddCollegeOpen(false);
    },
    [onAddCollege, validateNewCollegeName]
  );

  const handleRemoveCollegeTab = useCallback(
    async (collegeLocalId: string) => {
      const college = colleges.find(item => (item.local_id || item.name) === collegeLocalId);
      const confirmed = await openConfirm({
        title: 'Remove school / college tab?',
        message: `Remove "${college?.name || 'this school / college'}" from academics?\n\nLinked academic mappings for this school / college will also be removed from this step.`,
        confirmLabel: 'Remove',
        variant: 'warning',
      });
      if (!confirmed) return;
      const collegeScope: Extract<WizardAcademicsEntityScope, { type: 'college' }> = {
        type: 'college',
        collegeLocalId,
        collegeName: college?.name || '',
        collegeId: college?.id ?? null,
      };
      setCourses(prev => prev.filter(item => !offeringMatchesCollege(item, collegeScope)));
      setCollegeOverrides(prev => {
        const next = new Set(prev);
        next.delete(collegeLocalId);
        return next;
      });
      onRemoveCollege?.(collegeLocalId);
      setActiveScopeKey(institutionScopeKey());
    },
    [colleges, onRemoveCollege, openConfirm]
  );

  const editingCourse = editingIndex !== null ? courses[editingIndex] : null;

  const renderEntitySelectorsPanel = (scope: WizardAcademicsEntityScope) => (
    <div
      className="space-y-4"
      data-wizard-academics-selectors
      onFocusCapture={() => setActiveScopeKey(scopeKey(scope))}
      onPointerDownCapture={() => setActiveScopeKey(scopeKey(scope))}
    >
      {editingAcademicGroup &&
      scopeKey(editingAcademicGroup.scope) === scopeKey(scope) ? (
        <div
          role="status"
          className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-accent/30 bg-accent/5 px-3 py-2 text-sm text-text-main"
        >
          <p>
            Editing{' '}
            <span className="font-semibold">{editingAcademicGroup.label}</span>
            . Update level, program, and courses below, then save.
          </p>
          <button
            type="button"
            onClick={cancelAcademicEdit}
            className="shrink-0 rounded-lg px-2 py-1 text-xs font-semibold text-text-muted hover:bg-surface-bg hover:text-text-main"
          >
            Cancel
          </button>
        </div>
      ) : null}
      <WizardFieldError message={selectionError || undefined} />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="md:col-span-2">
          <SearchableSelect
            label={ACADEMIC_FRAMEWORK_STEP_LABELS.level}
            value={levelId ? String(levelId) : ''}
            options={availableLevelOptions}
            onChange={value => {
              const nextLevelId = value ? Number(value) : 0;
              setActiveScopeKey(scopeKey(scope));
              if (nextLevelId === levelId) {
                setFullyMappedCourseProgramLabels([]);
                if (nextLevelId > 0) {
                  void loadPrograms(nextLevelId);
                }
                return;
              }
              setLevelId(nextLevelId);
              setFullyMappedCourseProgramLabels([]);
              setSelectedProgramMajorValues([]);
              setSelectedCourseIds([]);
              setMajorInstances([]);
              setMajors([]);
              setProgramMajorOptions([]);
              setCatalogCourses([]);
              cascadeSourceRef.current = null;
            }}
            placeholder="e.g. Undergraduate, Graduate"
          />
          {allProgramsMappedForSelectedLevel ? (
            <div
              role="status"
              className="mt-2 rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800"
            >
              All programs for this level are already mapped. Visit the Academic Framework menu to
              add new programs.
            </div>
          ) : null}
        </div>
        <div className="md:col-span-2">
          <SearchableMultiSelect
            label={ACADEMIC_FRAMEWORK_STEP_LABELS.program}
            values={visibleSelectedProgramMajorValues}
            options={availableProgramOptions}
            onChange={handleProgramChange}
            placeholder={
              !levelId
                ? 'Select a level first'
                : loadingPrograms || loadingMajors
                  ? 'Loading programs...'
                  : programMajorOptions.length === 0
                    ? 'No programs for this level'
                    : availableProgramOptions.length === 0
                      ? 'All programs added to list'
                      : 'Select one or more programs / majors'
            }
            disabled={
              !levelId ||
              loadingPrograms ||
              loadingMajors ||
              availableProgramOptions.length === 0
            }
            hint="Each mapped major appears as its own item (e.g. Bachelor of Engineering — Civil Engineering)."
            selectedDisplay={programSelectedDisplay}
          />
        </div>
        <div className="md:col-span-2">
          <SearchableMultiSelect
            label={ACADEMIC_FRAMEWORK_STEP_LABELS.course}
            values={selectableCourseIds.map(String)}
            options={catalogCourseOptions}
            onChange={values => {
              const allowed = new Set(catalogCourseOptions.map(option => option.value));
              setSelectedCourseIds(
                values.map(Number).filter(id => id > 0 && allowed.has(String(id)))
              );
            }}
            placeholder={
              !levelId
                ? 'Select a level first'
                : courseCatalogMajorIds.length === 0
                  ? 'Select a program first'
                  : loadingCatalog
                    ? 'Loading courses...'
                    : catalogCourseOptions.length === 0
                      ? 'No catalog courses (optional)'
                      : 'Select one or more courses'
            }
            disabled={courseCatalogMajorIds.length === 0 || loadingCatalog}
            hint="Optional. Multi-major courses stay available until every mapped program/major affiliation is on the list."
            selectedDisplay={courseSelectedDisplay}
          />
          {fullyMappedCourseProgramLabels.length > 0 ? (
            <div
              role="status"
              className="mt-2 rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800"
            >
              {fullyMappedCourseProgramLabels.length === 1
                ? `All courses for ${fullyMappedCourseProgramLabels[0]} are already mapped.`
                : `All courses for these programs are already mapped: ${fullyMappedCourseProgramLabels.join(
                    ', '
                  )}.`}{' '}
              Visit the Academic Framework menu to add new courses.
            </div>
          ) : null}
        </div>
      </div>
      <button
        type="button"
        onClick={() => handleAddAcademicsToList(scope)}
        disabled={!canAddAcademics}
        className="inline-flex items-center gap-1 rounded-xl border border-border-subtle px-4 py-2 text-sm font-semibold text-text-main disabled:cursor-not-allowed disabled:opacity-50"
      >
        {loadingCatalog || loadingMajors ? (
          <Loader2 size={14} className="animate-spin" />
        ) : editingAcademicGroup &&
          scopeKey(editingAcademicGroup.scope) === scopeKey(scope) ? (
          <Pencil size={14} />
        ) : (
          <Plus size={14} />
        )}
        {editingAcademicGroup &&
        scopeKey(editingAcademicGroup.scope) === scopeKey(scope)
          ? 'Update academics'
          : 'Add Academics to list'}
      </button>
    </div>
  );

  if (isHierarchy) {
    return (
      <div className="space-y-6">
        <section className="rounded-2xl border border-border-subtle bg-card p-5">
          <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className={wizardSectionTitleClass}>University &amp; school / college academics</h3>
              <p className="mt-1 text-sm text-text-muted">
                Institution is the primary tab. Add a school / college tab to configure academics
                there, or override inheritance per school / college.
              </p>
            </div>
            {linkedAcademicItems.length > 0 ? (
              <button
                type="button"
                onClick={() => void handleUnlinkAllLinkedAcademics()}
                className="inline-flex shrink-0 items-center gap-1 rounded-xl border border-alert/30 px-3 py-1.5 text-sm font-semibold text-alert hover:bg-alert/10"
              >
                <Unlink size={14} />
                Unlink all
              </button>
            ) : null}
          </div>
          {listError ? (
            <div
              data-wizard-step-error={listError}
              className="mb-4 rounded-xl border border-alert/40 bg-alert/10 px-4 py-3 text-sm font-medium text-alert ring-1 ring-alert/30"
              role="alert"
            >
              {listError}
            </div>
          ) : null}
          <WizardAcademicsHierarchyTree
            institutionName={institutionName}
            colleges={colleges}
            courses={courses}
            collegeOverrides={collegeOverrides}
            cascadeToColleges={cascadeToColleges}
            activeScopeKey={activeScopeKey}
            panelEnriching={panelEnriching}
            onActiveScopeChange={key => {
              if (
                editingAcademicGroup &&
                scopeKey(editingAcademicGroup.scope) !== key
              ) {
                cancelAcademicEdit();
              }
              setActiveScopeKey(key);
            }}
            onCascadeChange={handleCascadeChange}
            onToggleCollegeOverride={handleToggleCollegeOverride}
            onEditProgramGroup={(scope, group) => handleEditProgramGroup(scope, group)}
            onUnlinkProgramGroup={(scope, group) => void handleUnlinkProgramGroup(scope, group)}
            onUnlinkAllInScope={scope => void handleUnlinkAllInScope(scope)}
            onAddCollege={onAddCollege ? handleAddCollegeTab : undefined}
            onRemoveCollegeTab={onRemoveCollege ? handleRemoveCollegeTab : undefined}
            groupProgramsForScope={groupProgramsForScope}
            renderEntityPanel={scope => renderEntitySelectorsPanel(scope)}
          />
        </section>

        {editingCourse ? (
          <div className="mt-4">
            <WizardCourseEditPanel
              key={editingCourse.local_id || editingCourse.course_id}
              title={editingCourse.display_label || `Course #${editingCourse.course_id}`}
              subtitle="Edit course details"
              defaultValues={{
                course_code: editingCourse.course_code || null,
                credits: editingCourse.credits ?? null,
                syllabus_outline: editingCourse.syllabus_outline || null,
              }}
              onClose={() => setEditingIndex(null)}
              onSave={values => handleSaveCourseEdit(editingIndex!, values)}
            />
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-border-subtle bg-card p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <h3 className={wizardSectionTitleClass}>Linked Academics</h3>
            {panelEnriching ? (
              <span className="inline-flex items-center gap-1 text-xs text-text-muted">
                <Loader2 size={14} className="animate-spin" />
                Loading linked academics…
              </span>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {linkedAcademicItems.length > 0 ? (
              <button
                type="button"
                onClick={() => void handleUnlinkAllLinkedAcademics()}
                className="inline-flex items-center gap-1 rounded-xl border border-alert/30 px-3 py-1.5 text-sm font-semibold text-alert hover:bg-alert/10"
              >
                <Unlink size={14} />
                Unlink all
              </button>
            ) : null}
            {selectedLinkedRowKeys.size > 0 ? (
              <button
                type="button"
                onClick={handleBulkUnlinkSelected}
                className="inline-flex items-center gap-1 rounded-xl border border-alert/30 px-3 py-1.5 text-sm font-semibold text-alert hover:bg-alert/10"
              >
                <Unlink size={14} />
                Unlink selected ({selectedLinkedRowKeys.size})
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => handleAddAcademicsToList()}
              disabled={!canAddAcademics}
              className="inline-flex items-center gap-1 rounded-xl border border-border-subtle px-4 py-2 text-sm font-semibold text-text-main disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loadingCatalog || loadingMajors ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Plus size={14} />
              )}
              Add Academics to list
            </button>
          </div>
        </div>
        <WizardFieldError message={selectionError || undefined} />
        {listError ? (
          <div
            data-wizard-step-error={listError}
            className="mb-4 rounded-xl border border-alert/40 bg-alert/10 px-4 py-3 text-sm font-medium text-alert ring-1 ring-alert/30"
            role="alert"
          >
            {listError}
          </div>
        ) : null}
        {panelEnriching ? (
          <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-border-subtle bg-surface-bg/40 px-6 py-12 text-sm text-text-muted">
            <Loader2 size={22} className="animate-spin text-accent" />
            Loading linked academics…
          </div>
        ) : linkedAcademics.length > 0 ? (
          <>
            <div className="mb-4 flex flex-wrap items-center gap-3">
              <label className="relative min-w-[220px] flex-1">
                <Search
                  size={16}
                  className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-muted"
                />
                <input
                  type="search"
                  value={panelSearch}
                  onChange={event => setPanelSearch(event.target.value)}
                  placeholder="Search linked academics..."
                  className="w-full rounded-xl border border-border-subtle bg-surface-bg py-2 pl-9 pr-3 text-sm outline-none focus:border-accent"
                />
              </label>
              <span className="text-sm text-text-muted">
                {filteredPanelRows.length} of {resolvedPanelRows.length} shown
              </span>
            </div>
            <div className="overflow-x-auto rounded-xl border border-border-subtle">
            <table className="w-full min-w-[680px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-border-subtle bg-surface-bg/60 text-left text-xs font-semibold uppercase tracking-wide text-text-muted">
                  <th className="w-10 px-3 py-2">
                    <input
                      type="checkbox"
                      className="rounded border-border-subtle"
                      checked={allLinkedRowsSelected}
                      ref={input => {
                        if (input) {
                          input.indeterminate =
                            someLinkedRowsSelected && !allLinkedRowsSelected;
                        }
                      }}
                      onChange={toggleSelectAllLinkedRows}
                      aria-label="Select all linked academics"
                    />
                  </th>
                  <FrameworkSortableHeader
                    label={ACADEMIC_FRAMEWORK_LABELS.level}
                    column="level"
                    sortBy={panelSortBy}
                    sortDir={panelSortDir}
                    onSort={togglePanelSort}
                    className="px-3 py-2"
                  />
                  <FrameworkSortableHeader
                    label={ACADEMIC_FRAMEWORK_LABELS.program}
                    column="program"
                    sortBy={panelSortBy}
                    sortDir={panelSortDir}
                    onSort={togglePanelSort}
                    className="px-3 py-2"
                  />
                  <FrameworkSortableHeader
                    label={ACADEMIC_FRAMEWORK_LABELS.major}
                    column="major"
                    sortBy={panelSortBy}
                    sortDir={panelSortDir}
                    onSort={togglePanelSort}
                    className="px-3 py-2"
                  />
                  <FrameworkSortableHeader
                    label={ACADEMIC_FRAMEWORK_LABELS.course}
                    column="course"
                    sortBy={panelSortBy}
                    sortDir={panelSortDir}
                    onSort={togglePanelSort}
                    className="px-3 py-2"
                  />
                  <th className="px-3 py-2 text-right">Unlink</th>
                </tr>
              </thead>
              <tbody>
                {paginatedPanelRows.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-3 py-8 text-center text-text-muted">
                      No linked academics match your search.
                    </td>
                  </tr>
                ) : (
                  paginatedPanelRows.map(({ course, key, indices, row, courseItems }) => {
                  const isSelected = selectedLinkedRowKeys.has(key);
                  return (
                    <tr
                      key={key}
                      className={`border-b border-border-subtle last:border-b-0 ${
                        isSelected ? 'bg-accent/5' : ''
                      }`}
                    >
                      <td className="px-3 py-3 align-top">
                        <input
                          type="checkbox"
                          className="rounded border-border-subtle"
                          checked={isSelected}
                          onChange={() => toggleLinkedRowSelection(key)}
                          aria-label={`Select ${row.programName} / ${row.majorName}`}
                        />
                      </td>
                      <td className="px-3 py-3 align-top text-text-main">{row.levelName}</td>
                      <td className="px-3 py-3 align-top text-text-main">{row.programName}</td>
                      <td className="px-3 py-3 align-top text-text-main">{row.majorName}</td>
                      <td className="px-3 py-3 align-top text-text-main">
                        {courseItems.length > 0 ? (
                          <div className="flex flex-wrap items-center gap-y-1">
                            {courseItems.map((item, itemIndex) => (
                              <Fragment key={`${item.index}:${item.name}`}>
                                {itemIndex > 0 ? <span className="mr-1">,</span> : null}
                                <span>{item.name}</span>
                                {item.courseId ? (
                                  <span className="ml-1 tabular-nums text-text-muted">
                                    ID {item.courseId}
                                  </span>
                                ) : null}
                                <button
                                  type="button"
                                  onClick={() => setEditingIndex(item.index)}
                                  className="inline-flex shrink-0 items-center rounded-lg px-1 py-0.5 text-xs font-semibold text-accent hover:bg-accent/10"
                                  title={`Edit ${item.name}`}
                                  aria-label={`Edit ${item.name}`}
                                >
                                  <Pencil size={12} />
                                </button>
                                <button
                                  type="button"
                                  onClick={() => handleUnlinkSingleCourse(item.index, item.name)}
                                  className="mr-1 inline-flex shrink-0 items-center rounded-lg px-1 py-0.5 text-xs font-semibold text-alert hover:bg-alert/10"
                                  title={`Unlink ${item.name}`}
                                  aria-label={`Unlink ${item.name}`}
                                >
                                  <Unlink size={12} />
                                </button>
                              </Fragment>
                            ))}
                          </div>
                        ) : (
                          row.courseName
                        )}
                      </td>
                      <td className="px-3 py-3 align-top text-right">
                        <button
                          type="button"
                          onClick={() => handleUnlinkCourse(course, indices, row.majorName)}
                          className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-alert hover:bg-alert/10"
                        >
                          <Unlink size={14} />
                          {indices.length > 1 ? 'Unlink all' : 'Unlink'}
                        </button>
                      </td>
                    </tr>
                  );
                  })
                )}
              </tbody>
            </table>
            <FrameworkTablePagination
              page={panelPage}
              pageSize={panelPageSize}
              total={filteredPanelRows.length}
              totalPages={panelTotalPages}
              pageSizeOptions={LINKED_ACADEMICS_PAGE_SIZES}
              onPageChange={setPanelPage}
              onPageSizeChange={size => {
                setPanelPageSize(size);
                setPanelPage(1);
              }}
            />
          </div>
          </>
        ) : (
          <EmptyListMessage message='No linked academics added yet. Select a level, program, and optional courses below, then click "Add Academics to list".' />
        )}

        {editingCourse ? (
          <div className="mt-4">
            <WizardCourseEditPanel
              key={editingCourse.local_id || editingCourse.course_id}
              title={editingCourse.display_label || `Course #${editingCourse.course_id}`}
              subtitle="Edit course details"
              defaultValues={{
                course_code: editingCourse.course_code || null,
                credits: editingCourse.credits ?? null,
                syllabus_outline: editingCourse.syllabus_outline || null,
              }}
              onClose={() => setEditingIndex(null)}
              onSave={values => handleSaveCourseEdit(editingIndex!, values)}
            />
          </div>
        ) : null}
      </section>

      <section className={wizardSectionClass}>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div className="md:col-span-2">
            <SearchableSelect
              label={ACADEMIC_FRAMEWORK_STEP_LABELS.level}
              value={levelId ? String(levelId) : ''}
              options={availableLevelOptions}
              onChange={value => {
                const nextLevelId = value ? Number(value) : 0;
                // Re-selecting the same level must refresh programs. Clearing options
                // without reload left the Programs dropdown empty/disabled.
                if (nextLevelId === levelId) {
                  setFullyMappedCourseProgramLabels([]);
                  if (nextLevelId > 0) {
                    void loadPrograms(nextLevelId);
                  }
                  return;
                }
                setLevelId(nextLevelId);
                setFullyMappedCourseProgramLabels([]);
                setSelectedProgramMajorValues([]);
                setSelectedCourseIds([]);
                setMajorInstances([]);
                setMajors([]);
                setProgramMajorOptions([]);
                setCatalogCourses([]);
                cascadeSourceRef.current = null;
              }}
              placeholder="e.g. Undergraduate, Graduate"
            />
            {allProgramsMappedForSelectedLevel ? (
              <div
                role="status"
                className="mt-2 rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800"
              >
                All programs for this level are already mapped. Visit the Academic Framework
                menu to add new programs.
              </div>
            ) : null}
          </div>
          <div className="md:col-span-2">
            <SearchableMultiSelect
              label={ACADEMIC_FRAMEWORK_STEP_LABELS.program}
              values={visibleSelectedProgramMajorValues}
              options={availableProgramOptions}
              onChange={handleProgramChange}
              placeholder={
                !levelId
                  ? 'Select a level first'
                  : loadingPrograms || loadingMajors
                    ? 'Loading programs...'
                    : programMajorOptions.length === 0
                      ? 'No programs for this level'
                      : availableProgramOptions.length === 0
                        ? 'All programs added to list'
                        : 'Select one or more programs / majors'
              }
              disabled={
                !levelId ||
                loadingPrograms ||
                loadingMajors ||
                availableProgramOptions.length === 0
              }
              hint="Each mapped major appears as its own item (e.g. Bachelor of Engineering — Civil Engineering)."
              selectedDisplay={programSelectedDisplay}
            />
          </div>
          <div className="md:col-span-2">
            <SearchableMultiSelect
              label={ACADEMIC_FRAMEWORK_STEP_LABELS.course}
              values={selectableCourseIds.map(String)}
              options={catalogCourseOptions}
              onChange={values => {
                const allowed = new Set(catalogCourseOptions.map(option => option.value));
                setSelectedCourseIds(
                  values.map(Number).filter(id => id > 0 && allowed.has(String(id)))
                );
              }}
              placeholder={
                !levelId
                  ? 'Select a level first'
                  : courseCatalogMajorIds.length === 0
                    ? 'Select a program first'
                    : loadingCatalog
                      ? 'Loading courses...'
                      : catalogCourseOptions.length === 0
                        ? 'No catalog courses (optional)'
                        : 'Select one or more courses'
              }
              disabled={courseCatalogMajorIds.length === 0 || loadingCatalog}
              hint="Optional. Multi-major courses stay available until every mapped program/major affiliation is on the list."
              selectedDisplay={courseSelectedDisplay}
            />
            {fullyMappedCourseProgramLabels.length > 0 ? (
              <div
                role="status"
                className="mt-2 rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800"
              >
                {fullyMappedCourseProgramLabels.length === 1
                  ? `All courses for ${fullyMappedCourseProgramLabels[0]} are already mapped.`
                  : `All courses for these programs are already mapped: ${fullyMappedCourseProgramLabels.join(
                      ', '
                    )}.`}{' '}
                Visit the Academic Framework menu to add new courses.
              </div>
            ) : null}
          </div>
        </div>
      </section>

      <TextPromptModal
        open={addCollegeOpen}
        title="Add school / college"
        message={
          'Enter a valid school or college name.\n\n' +
          'Each school / college needs its own unique name. Duplicate names are not allowed.'
        }
        label="School / College name *"
        placeholder="e.g. School of Engineering"
        defaultValue=""
        confirmLabel="Add"
        cancelLabel="Cancel"
        validate={validateNewCollegeName}
        onConfirm={handleConfirmAddCollege}
        onCancel={() => setAddCollegeOpen(false)}
      />
    </div>
  );
});

InstitutionWizardStep4.displayName = 'InstitutionWizardStep4';
export default InstitutionWizardStep4;
