import { z } from 'zod';

/**
 * LPMC Academic Framework hierarchy (maps to DB tables):
 *   levels           → Level (e.g. Undergraduate)
 *   programs         → Program / qualification (e.g. BEng, BSc)
 *   education_super_majors → Super-Major / marketing cluster
 *   education_majors → Major / discipline (e.g. Computer Science)
 *   education_courses→ Course (optional, e.g. Thermodynamics 101)
 */
export const ACADEMIC_FRAMEWORK_LABELS = {
  level: 'Level',
  program: 'Program',
  superMajor: 'Super-Major',
  major: 'Major / Discipline',
  subMajor: 'Sub-majors',
  course: 'Course',
} as const;

export const ACADEMIC_FRAMEWORK_STEP_LABELS = {
  level: 'Step A — Level',
  program: 'Step B — Program',
  major: 'Step C — Major',
  course: 'Step C — Course (optional)',
} as const;

export const frameworkLevelIdField = z
  .number({ error: 'Select a level' })
  .int()
  .positive('Select a level');

export const frameworkProgramIdField = z
  .number({ error: 'Select a program' })
  .int()
  .positive('Select a program');

export const frameworkMajorIdField = z
  .number({ error: 'Select a major or discipline' })
  .int()
  .positive('Select a major or discipline');

export const frameworkCatalogCourseIdField = z
  .number({ error: 'Select a catalog course' })
  .int()
  .positive('Select a catalog course');

export interface FrameworkHierarchyContext {
  levelId: number;
  programId: number;
  majorId: number;
}

export function validateFrameworkHierarchyChain(
  value: FrameworkHierarchyContext,
  ctx: z.RefinementCtx
): void {
  if (!value.levelId) {
    ctx.addIssue({
      code: 'custom',
      message: 'Every program must belong to a level',
      path: ['level_id'],
    });
  }
  if (!value.programId) {
    ctx.addIssue({
      code: 'custom',
      message: 'Every major must belong to a program',
      path: ['program_id'],
    });
  }
}

export function validateOptionalCourseFields(
  value: { major_id?: number; name?: string | null; code?: string | null },
  ctx: z.RefinementCtx
): void {
  if (!value.major_id) {
    ctx.addIssue({
      code: 'custom',
      message: 'Select a major before adding a course',
      path: ['major_id'],
    });
  }
  const hasName = Boolean(value.name?.trim());
  const hasCode = Boolean(value.code?.trim());
  if (hasCode && !hasName) {
    ctx.addIssue({
      code: 'custom',
      message: 'Course name is required when a code is provided',
      path: ['name'],
    });
  }
}
