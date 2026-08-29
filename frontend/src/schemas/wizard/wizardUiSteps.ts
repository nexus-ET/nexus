/**
 * UI wizard has 5 steps (Institution+Campuses merged).
 * Backend still uses API steps 1–6 (1=institution, 2=campuses, 3–6 unchanged).
 * Rollback: restore 6-step labels/page wiring and drop this mapping.
 */

export const WIZARD_UI_STEP_COUNT = 5;

export const WIZARD_STEP_LABELS = [
  'Institution & Campuses',
  'Schools & Colleges',
  'Academics',
  'Intakes',
  'Gallery',
] as const;

/** Map UI step (1–5) to the primary API step used for draft.current_step / navigation. */
export function uiStepToApiStep(uiStep: number): number {
  if (uiStep <= 1) return 1;
  return uiStep + 1; // 2→3, 3→4, 4→5, 5→6
}

/** Map API step (1–6) to UI step (1–5). API campus step 2 collapses into UI step 1. */
export function apiStepToUiStep(apiStep: number): number {
  if (apiStep <= 2) return 1;
  return apiStep - 1; // 3→2, 4→3, 5→4, 6→5
}

export function clampUiStep(step: number | null | undefined): number | null {
  if (!Number.isInteger(step) || !step) return null;
  if (step < 1 || step > WIZARD_UI_STEP_COUNT) return null;
  return step;
}

/** Collapse API completed/data step lists into UI steps. */
export function mapApiStepsToUi(apiSteps: number[]): number[] {
  return [...new Set(apiSteps.map(apiStepToUiStep))].sort((a, b) => a - b);
}

const LEGACY_PUBLISH_STEP_LABELS: Record<number, string> = {
  1: 'Institution & Campuses',
  2: 'Schools & Colleges',
  3: 'Academics',
  4: 'Intakes',
  5: 'Gallery',
};

type PublishCheckLike = {
  name: string;
  status: string;
  details: string;
};

type PublishStepLike = {
  step: number;
  label: string;
  status: string;
  started_at: string;
  completed_at: string;
  checks: unknown[];
  discrepancies: unknown[];
  result: Record<string, unknown>;
};

const AUDIT_FIELD_LABELS: Record<string, string> = {
  campus_count: 'Campuses (optional)',
  campus_id: 'Campus',
  campuses: 'Campuses (optional)',
  campus: 'Campus',
  campuses_created_or_updated: 'Campuses saved',
  campuses_removed: 'Campuses removed',
};

const CAMPUS_MISSING_RE =
  /at least one campus|campus(?:es)?(?:\s+\w+){0,3}\s+required|required\s+campus|no campus|0 campus|missing campus|incomplete(?:\s+\w+){0,2}\s+campus/i;

function isPublishCheckLike(value: unknown): value is PublishCheckLike {
  return Boolean(
    value &&
      typeof value === 'object' &&
      typeof (value as PublishCheckLike).name === 'string' &&
      typeof (value as PublishCheckLike).status === 'string' &&
      typeof (value as PublishCheckLike).details === 'string'
  );
}

function campusCountFromResult(result: Record<string, unknown> | undefined): number | undefined {
  const value = result?.campus_count;
  return typeof value === 'number' ? value : undefined;
}

/** Display labels for history/audit snapshots. Campus count is optional, not a required field. */
export function formatAuditFieldLabel(key: string): string {
  if (AUDIT_FIELD_LABELS[key]) return AUDIT_FIELD_LABELS[key];
  return key.replace(/_/g, ' ').replace(/\b\w/g, character => character.toUpperCase());
}

export function rewriteOptionalCampusCheck<T extends PublishCheckLike>(
  check: T,
  campusCount?: number | null
): T {
  const blob = `${check.name} ${check.details}`;
  if (!/campus/i.test(blob)) return check;

  const countIsZero = campusCount === 0 || /\b0 campus/i.test(blob);
  const looksMissing = CAMPUS_MISSING_RE.test(blob);
  const looksFailedMissing = check.status !== 'passed' && looksMissing;

  if (countIsZero || looksFailedMissing) {
    if (/assignment/i.test(check.name)) {
      return {
        ...check,
        status: 'passed',
        details: 'No campus assigned — pictures stay on the institution (campuses are optional).',
      };
    }
    return {
      ...check,
      name: 'Campuses',
      status: 'passed',
      details: 'None added — campuses are optional.',
    };
  }

  if (/required/i.test(blob)) {
    const stripped = check.name.replace(/\s*required\s*/gi, ' ').replace(/\s+/g, ' ').trim();
    const name =
      !stripped || /^fields$/i.test(stripped)
        ? 'Campus fields'
        : /campus/i.test(stripped)
          ? stripped
          : `Campus ${stripped}`;
    return {
      ...check,
      name,
      details: /every campus/i.test(check.details)
        ? 'Each added campus has a name, campus type, and city.'
        : check.details.replace(/required/gi, 'present'),
    };
  }

  return check;
}

function rewriteOptionalCampusPublishStep<T extends PublishStepLike>(step: T): T {
  const campusCount = campusCountFromResult(step.result);
  const originalChecks = step.checks || [];
  const checks = originalChecks.map(check =>
    isPublishCheckLike(check) ? rewriteOptionalCampusCheck(check, campusCount) : check
  );
  const typed = checks.filter(isPublishCheckLike);
  const allPassed = typed.length === 0 || typed.every(item => item.status === 'passed');
  const hadCampusBlocker = originalChecks.some(
    check =>
      isPublishCheckLike(check) &&
      check.status !== 'passed' &&
      /campus/i.test(`${check.name} ${check.details}`)
  );
  return {
    ...step,
    checks,
    status: hadCampusBlocker && allPassed ? 'success' : step.status,
  };
}

/**
 * Map stored publish-report steps onto the 5-step UI wizard.
 * Legacy reports had separate Institution + Campuses steps (6 total).
 */
export function normalizePublishReportSteps<T extends PublishStepLike>(steps: T[]): T[] {
  if (!steps.length) return steps;

  const sorted = [...steps].sort((a, b) => a.step - b.step);
  const looksLegacySix =
    sorted.length >= 6 ||
    (sorted[0]?.label === 'Institution' && sorted[1]?.label === 'Campuses');

  let uiSteps: T[];
  if (looksLegacySix) {
    const institution = sorted[0];
    const campuses = sorted[1];
    const merged = {
      ...institution,
      step: 1,
      label: LEGACY_PUBLISH_STEP_LABELS[1],
      started_at: institution.started_at,
      completed_at: campuses?.completed_at || institution.completed_at,
      checks: [...(institution.checks || []), ...(campuses?.checks || [])],
      discrepancies: [...(institution.discrepancies || []), ...(campuses?.discrepancies || [])],
      result: { ...(institution.result || {}), ...(campuses?.result || {}) },
    } as T;
    uiSteps = [merged, ...sorted.slice(2).map((item, index) => ({
      ...item,
      step: index + 2,
      label: LEGACY_PUBLISH_STEP_LABELS[index + 2] || item.label,
    }))];
  } else {
    uiSteps = sorted.map((item, index) => ({
      ...item,
      step: index + 1,
      label:
        item.label === 'Colleges'
          ? LEGACY_PUBLISH_STEP_LABELS[2]
          : LEGACY_PUBLISH_STEP_LABELS[index + 1] || item.label,
    }));
  }

  return uiSteps.slice(0, WIZARD_UI_STEP_COUNT).map(rewriteOptionalCampusPublishStep);
}
