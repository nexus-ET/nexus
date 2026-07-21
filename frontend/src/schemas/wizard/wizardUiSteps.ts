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

  return uiSteps.slice(0, WIZARD_UI_STEP_COUNT);
}
