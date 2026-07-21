import type { WizardCollegeItem } from '../../../schemas/wizard/step3-colleges';
import type { WizardCourseOfferingItem } from '../../../schemas/wizard/step4-courses';

export type WizardAcademicsEntityScope =
  | { type: 'institution' }
  | { type: 'college'; collegeLocalId: string; collegeName: string };

export function institutionScopeKey(): string {
  return 'institution';
}

export function collegeScopeKey(collegeLocalId: string): string {
  return `college:${collegeLocalId}`;
}

export function scopeKey(scope: WizardAcademicsEntityScope): string {
  return scope.type === 'institution'
    ? institutionScopeKey()
    : collegeScopeKey(scope.collegeLocalId);
}

export function offeringScopeKey(
  offering: Pick<WizardCourseOfferingItem, 'college_id' | 'college_local_id'>
): string {
  if (offering.college_local_id?.trim()) {
    return collegeScopeKey(offering.college_local_id.trim());
  }
  if (offering.college_id) {
    return `college-id:${offering.college_id}`;
  }
  return institutionScopeKey();
}

export function filterOfferingsForScope(
  offerings: WizardCourseOfferingItem[],
  scope: WizardAcademicsEntityScope,
  options?: {
    collegeOverrides?: Set<string>;
    includeInherited?: boolean;
  }
): WizardCourseOfferingItem[] {
  const overrides = options?.collegeOverrides ?? new Set<string>();
  const includeInherited = options?.includeInherited ?? true;

  if (scope.type === 'institution') {
    return offerings.filter(item => offeringScopeKey(item) === institutionScopeKey());
  }

  const collegeKey = collegeScopeKey(scope.collegeLocalId);
  const hasOverride = overrides.has(scope.collegeLocalId);

  if (hasOverride) {
    return offerings.filter(item => offeringScopeKey(item) === collegeKey);
  }

  if (includeInherited) {
    return offerings.filter(item => {
      const key = offeringScopeKey(item);
      return key === institutionScopeKey() || key === collegeKey;
    });
  }

  return offerings.filter(item => offeringScopeKey(item) === collegeKey);
}

export function stampOfferingScope(
  offering: WizardCourseOfferingItem,
  scope: WizardAcademicsEntityScope
): WizardCourseOfferingItem {
  if (scope.type === 'institution') {
    return {
      ...offering,
      college_id: null,
      college_local_id: null,
    };
  }
  return {
    ...offering,
    college_id: null,
    college_local_id: scope.collegeLocalId,
  };
}

export function cloneOfferingForCollege(
  offering: WizardCourseOfferingItem,
  college: WizardCollegeItem
): WizardCourseOfferingItem {
  return {
    ...offering,
    local_id: crypto.randomUUID(),
    college_id: null,
    college_local_id: college.local_id || null,
  };
}

export interface GroupedProgramLink {
  key: string;
  levelName: string;
  programName: string;
  majorName: string;
  courseNames: string[];
  indices: number[];
}

export function groupProgramsForOfferings(
  entries: Array<{ offering: WizardCourseOfferingItem; index: number }>,
  resolveRow: (offering: WizardCourseOfferingItem) => {
    levelName: string;
    programName: string;
    majorName: string;
    courseName: string;
  }
): GroupedProgramLink[] {
  const groups = new Map<string, GroupedProgramLink>();

  entries.forEach(({ offering, index }) => {
    const row = resolveRow(offering);
    const hasCourse = Number(offering.course_id) > 0;
    const groupKey = hasCourse
      ? `course-group:${offering.level_id}|${offering.program_id}|${offering.major_id || 0}`
      : `scope-group:${offering.level_id}|${offering.program_id}|${offering.major_id || 0}`;

    const existing = groups.get(groupKey);
    if (!existing) {
      groups.set(groupKey, {
        key: groupKey,
        levelName: row.levelName,
        programName: row.programName,
        majorName: row.majorName,
        courseNames: hasCourse ? [row.courseName] : [],
        indices: [index],
      });
      return;
    }

    existing.indices.push(index);
    if (hasCourse && row.courseName && !existing.courseNames.includes(row.courseName)) {
      existing.courseNames.push(row.courseName);
    }
    if (row.majorName && row.majorName !== '—' && existing.majorName === '—') {
      existing.majorName = row.majorName;
    }
  });

  return Array.from(groups.values());
}

export function getUnlinkableIndicesForDisplayedScope(
  courses: WizardCourseOfferingItem[],
  scope: WizardAcademicsEntityScope,
  collegeOverrides: Set<string>,
  candidateIndices?: number[]
): number[] {
  const includeInherited =
    scope.type === 'college' && !collegeOverrides.has(scope.collegeLocalId);

  let indices: number[] = [];

  courses.forEach((offering, index) => {
    const isLinked =
      Number(offering.course_id) > 0 ||
      Boolean(offering.program_id?.trim()) ||
      Number(offering.major_id) > 0;
    if (!isLinked) return;

    const visible = filterOfferingsForScope([offering], scope, {
      collegeOverrides,
      includeInherited,
    });
    if (visible.length > 0) {
      indices.push(index);
    }
  });

  if (candidateIndices && candidateIndices.length > 0) {
    const candidateSet = new Set(candidateIndices);
    indices = indices.filter(index => candidateSet.has(index));
  }

  return indices;
}

/** College unlink must only target rows owned by that college — never university rows. */
export function getCollegeOwnedUnlinkIndices(
  courses: WizardCourseOfferingItem[],
  collegeLocalId: string,
  candidateIndices?: number[]
): number[] {
  const collegeKey = collegeScopeKey(collegeLocalId);
  let indices: number[] = [];

  courses.forEach((offering, index) => {
    const isLinked =
      Number(offering.course_id) > 0 ||
      Boolean(offering.program_id?.trim()) ||
      Number(offering.major_id) > 0;
    if (!isLinked) return;
    if (offeringScopeKey(offering) !== collegeKey) return;
    indices.push(index);
  });

  if (candidateIndices && candidateIndices.length > 0) {
    const candidateSet = new Set(candidateIndices);
    indices = indices.filter(index => candidateSet.has(index));
  }

  return indices;
}

function normalizeProgramId(id: string | number | null | undefined): string {
  if (id === null || id === undefined) return '';
  return String(id).trim().toLowerCase();
}

function academicAffiliationKey(offering: WizardCourseOfferingItem): string {
  if (Number(offering.course_id) > 0) {
    return `course:${offering.course_id}|${normalizeProgramId(offering.program_id)}|${offering.major_id}`;
  }
  return `scope:${offering.level_id}|${normalizeProgramId(offering.program_id)}|${offering.major_id}`;
}

/** When unlinking university academics, also drop cascaded college copies. */
export function expandInstitutionUnlinkIndices(
  courses: WizardCourseOfferingItem[],
  indices: number[],
  collegeOverrides: Set<string>
): number[] {
  const expanded = new Set(indices);

  for (const index of indices) {
    const source = courses[index];
    if (!source || offeringScopeKey(source) !== institutionScopeKey()) continue;

    const affiliationKey = academicAffiliationKey(source);
    courses.forEach((item, itemIndex) => {
      if (expanded.has(itemIndex)) return;

      const scope = offeringScopeKey(item);
      if (scope === institutionScopeKey()) return;
      if (!scope.startsWith('college')) return;
      if (academicAffiliationKey(item) !== affiliationKey) return;

      const collegeLocalId = item.college_local_id?.trim();
      if (collegeLocalId && collegeOverrides.has(collegeLocalId)) return;

      expanded.add(itemIndex);
    });
  }

  return [...expanded].sort((a, b) => a - b);
}

export function collegeUnlinkIncludesInheritedUniversityItems(
  courses: WizardCourseOfferingItem[],
  scope: WizardAcademicsEntityScope,
  collegeOverrides: Set<string>,
  indices: number[]
): boolean {
  if (scope.type !== 'college' || collegeOverrides.has(scope.collegeLocalId)) {
    return false;
  }
  return indices.some(index => {
    const offering = courses[index];
    return offering && offeringScopeKey(offering) === institutionScopeKey();
  });
}
