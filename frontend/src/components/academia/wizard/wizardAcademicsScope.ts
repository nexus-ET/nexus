import type { WizardCollegeItem } from '../../../schemas/wizard/step3-colleges';
import type { WizardCourseOfferingItem } from '../../../schemas/wizard/step4-courses';

export type WizardAcademicsEntityScope =
  | { type: 'institution' }
  | {
      type: 'college';
      collegeLocalId: string;
      collegeName: string;
      /** Live DB colleges.id when known — matches offering.college_id from offerings table. */
      collegeId?: number | null;
    };

export function institutionScopeKey(): string {
  return 'institution';
}

export function collegeScopeKey(collegeLocalId: string): string {
  return `college:${collegeLocalId}`;
}

export function collegeIdScopeKey(collegeId: number): string {
  return `college-id:${collegeId}`;
}

export function scopeKey(scope: WizardAcademicsEntityScope): string {
  return scope.type === 'institution'
    ? institutionScopeKey()
    : collegeScopeKey(scope.collegeLocalId);
}

export function offeringScopeKey(
  offering: Pick<WizardCourseOfferingItem, 'college_id' | 'college_local_id'>
): string {
  // Prefer live DB college_id so tabs filter correctly even when college_local_id is unset.
  if (offering.college_id != null && Number(offering.college_id) > 0) {
    return collegeIdScopeKey(Number(offering.college_id));
  }
  if (offering.college_local_id?.trim()) {
    return collegeScopeKey(offering.college_local_id.trim());
  }
  return institutionScopeKey();
}

/** True when an offering belongs to the given college tab (local_id and/or live id). */
export function offeringMatchesCollege(
  offering: Pick<WizardCourseOfferingItem, 'college_id' | 'college_local_id'>,
  scope: Extract<WizardAcademicsEntityScope, { type: 'college' }>
): boolean {
  const offeringCollegeId =
    offering.college_id != null && Number(offering.college_id) > 0
      ? Number(offering.college_id)
      : null;
  const scopeCollegeId =
    scope.collegeId != null && Number(scope.collegeId) > 0 ? Number(scope.collegeId) : null;

  // Prefer live DB college_id — draft college_local_id can be stale or missing.
  if (offeringCollegeId != null && scopeCollegeId != null) {
    return offeringCollegeId === scopeCollegeId;
  }
  if (offeringCollegeId != null && scope.collegeLocalId === String(offeringCollegeId)) {
    return true;
  }
  const localId = offering.college_local_id?.trim();
  if (localId && localId === scope.collegeLocalId) {
    return true;
  }
  return false;
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

  const hasOverride = overrides.has(scope.collegeLocalId);

  if (hasOverride) {
    return offerings.filter(item => offeringMatchesCollege(item, scope));
  }

  if (includeInherited) {
    return offerings.filter(item => {
      if (offeringMatchesCollege(item, scope)) return true;
      // Inherit only true university rows (no college_id / college_local_id).
      // Rows owned by another college must never appear on this tab.
      const ownedElsewhere =
        (item.college_id != null && Number(item.college_id) > 0) ||
        Boolean(item.college_local_id?.trim());
      if (ownedElsewhere) return false;
      return offeringScopeKey(item) === institutionScopeKey();
    });
  }

  return offerings.filter(item => offeringMatchesCollege(item, scope));
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
    college_id: scope.collegeId ?? null,
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
    college_id: college.id ?? null,
    college_local_id: college.local_id || null,
  };
}

export const NO_MAJOR_GROUP_LABEL = 'No major';

export function majorGroupHeading(majorName: string | null | undefined): string {
  const trimmed = (majorName || '').trim();
  if (
    !trimmed ||
    trimmed === '—' ||
    trimmed.toLowerCase() === 'no major' ||
    trimmed.toLowerCase() === 'uncategorized'
  ) {
    return NO_MAJOR_GROUP_LABEL;
  }
  return trimmed;
}

export interface GroupedProgramLink {
  key: string;
  levelName: string;
  programName: string;
  majorName: string;
  programUrl?: string | null;
  courseNames: string[];
  indices: number[];
}

export type ResolvedOfferingRow = {
  levelName: string;
  programName: string;
  majorName: string;
  courseName: string;
  programUrl?: string | null;
  /** When set, the program is listed under each mapped major (college panel grouping). */
  majorGroups?: Array<{ id: number; name: string }>;
};

export function programUrlHref(url: string): string {
  const trimmed = url.trim();
  if (/^[a-z][a-z0-9+.-]*:/i.test(trimmed)) return trimmed;
  return `https://${trimmed}`;
}

export function groupProgramsForOfferings(
  entries: Array<{ offering: WizardCourseOfferingItem; index: number }>,
  resolveRow: (offering: WizardCourseOfferingItem) => ResolvedOfferingRow
): GroupedProgramLink[] {
  const groups = new Map<string, GroupedProgramLink>();

  entries.forEach(({ offering, index }) => {
    const row = resolveRow(offering);
    const hasCourse = Number(offering.course_id) > 0;
    const majorGroups =
      row.majorGroups && row.majorGroups.length > 0
        ? row.majorGroups
        : [
            {
              id: Number(offering.major_id) || 0,
              name: row.majorName,
            },
          ];

    for (const major of majorGroups) {
      const majorId = Number(major.id) || Number(offering.major_id) || 0;
      const majorName = majorGroupHeading(major.name || row.majorName);
      const groupKey = hasCourse
        ? `course-group:${offering.level_id}|${offering.program_id}|${majorId}|${majorName.toLowerCase()}`
        : `scope-group:${offering.level_id}|${offering.program_id}|${majorId}|${majorName.toLowerCase()}`;

      const existing = groups.get(groupKey);
      const programUrl =
        (typeof offering.program_url === 'string' ? offering.program_url.trim() : '') ||
        row.programUrl?.trim() ||
        null;
      if (!existing) {
        groups.set(groupKey, {
          key: groupKey,
          levelName: row.levelName,
          programName: row.programName,
          majorName,
          programUrl,
          courseNames: hasCourse ? [row.courseName] : [],
          indices: [index],
        });
        continue;
      }

      existing.indices.push(index);
      if (!existing.programUrl && programUrl) {
        existing.programUrl = programUrl;
      }
      if (hasCourse && row.courseName && !existing.courseNames.includes(row.courseName)) {
        existing.courseNames.push(row.courseName);
      }
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
  candidateIndices?: number[],
  collegeId?: number | null
): number[] {
  const scope: Extract<WizardAcademicsEntityScope, { type: 'college' }> = {
    type: 'college',
    collegeLocalId,
    collegeName: '',
    collegeId: collegeId ?? null,
  };
  let indices: number[] = [];

  courses.forEach((offering, index) => {
    const isLinked =
      Number(offering.course_id) > 0 ||
      Boolean(offering.program_id?.trim()) ||
      Number(offering.major_id) > 0;
    if (!isLinked) return;
    if (!offeringMatchesCollege(offering, scope)) return;
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
