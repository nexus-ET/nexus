import { z } from 'zod';

import {
  validateFrameworkHierarchyChain,
} from '../academicFrameworkHierarchy';
import { emptyToNull, richTextField } from './shared';

export const wizardCourseOfferingItemSchema = z
  .object({
    local_id: z.string().optional(),
    level_id: z.number().int().nonnegative(),
    program_id: z.string(),
    major_id: z.number().int().nonnegative(),
    course_id: z.number().int().nonnegative(),
    college_id: z.number().int().positive().optional().nullable(),
    college_local_id: z.string().optional().nullable(),
    course_code: z.preprocess(
      emptyToNull,
      z
        .string()
        .max(50, 'Course code must be 50 characters or fewer')
        .regex(
          /^[A-Z0-9_-]+$/i,
          'Course code may only contain letters, numbers, dashes, and underscores'
        )
        .nullable()
        .optional()
    ),
    credits: z
      .number({ error: 'Credits must be a number' })
      .min(0, 'Credits cannot be negative')
      .max(30, 'Credits cannot exceed 30')
      .optional()
      .nullable(),
    syllabus_outline: richTextField(5000, 'Course description'),
  })
  .superRefine((value, ctx) => {
    const hasCourse = value.course_id > 0;
    const hasScope =
      value.level_id > 0 ||
      value.program_id.trim().length > 0 ||
      value.major_id > 0;

    if (!hasCourse && !hasScope) {
      ctx.addIssue({
        code: 'custom',
        message: 'Each academic entry must include a level, program, major, or course.',
        path: ['level_id'],
      });
      return;
    }

    if (hasCourse) {
      validateFrameworkHierarchyChain(
        {
          levelId: value.level_id,
          programId: value.program_id,
          majorId: value.major_id,
        },
        ctx
      );
    }
  });

export const wizardCoursesStepSchema = z
  .array(wizardCourseOfferingItemSchema)
  .superRefine((items, ctx) => {
    const seenCourseAffiliations = new Set<string>();
    const seenScopes = new Set<string>();
    items.forEach((item, index) => {
      const collegeScope =
        item.college_local_id?.trim() ||
        (item.college_id ? `college-id:${item.college_id}` : 'institution');

      if (item.course_id > 0) {
        // Same catalog course may be linked once per program×major×college affiliation.
        const affiliationKey = [
          item.course_id,
          String(item.program_id || '')
            .trim()
            .toLowerCase(),
          item.major_id,
          collegeScope,
        ].join('|');
        if (seenCourseAffiliations.has(affiliationKey)) {
          ctx.addIssue({
            code: 'custom',
            message:
              'This course is already linked for the same program and major. Remove the duplicate before continuing.',
            path: [index, 'course_id'],
          });
        }
        seenCourseAffiliations.add(affiliationKey);
        return;
      }
      const scopeKey = `${item.level_id}|${item.program_id}|${item.major_id}|${collegeScope}`;
      if (seenScopes.has(scopeKey)) {
        ctx.addIssue({
          code: 'custom',
          message: 'This academic scope is already linked.',
          path: [index, 'major_id'],
        });
      }
      seenScopes.add(scopeKey);
    });
  });

export type WizardCourseOfferingItem = z.infer<typeof wizardCourseOfferingItemSchema>;

export type WizardCourseOfferingDraft = WizardCourseOfferingItem & {
  display_label?: string | null;
};

export const emptyWizardCourseDraft: WizardCourseOfferingItem = {
  local_id: '',
  level_id: 0,
  program_id: '',
  major_id: 0,
  course_id: 0,
  college_id: null,
  course_code: null,
  credits: null,
  syllabus_outline: null,
};

export function createEmptyWizardCourseDraft(): WizardCourseOfferingItem {
  return {
    ...emptyWizardCourseDraft,
    local_id: crypto.randomUUID(),
  };
}

type LegacyOfferingFields = {
  course_level_id?: number | string | null;
};

export function hydrateWizardCourseOffering(
  raw: Partial<WizardCourseOfferingDraft> & LegacyOfferingFields & {
    course_id?: number | string;
    program_id?: number | string;
  }
): WizardCourseOfferingDraft {
  const legacyLevelId = raw.level_id ?? raw.course_level_id;
  const rawCredits = raw.credits;
  const credits =
    rawCredits === null || rawCredits === undefined || rawCredits === ('' as never)
      ? null
      : Number(rawCredits);
  return {
    ...createEmptyWizardCourseDraft(),
    ...raw,
    local_id: raw.local_id || crypto.randomUUID(),
    level_id: Number(legacyLevelId) || 0,
    program_id: raw.program_id ? String(raw.program_id) : '',
    major_id: Number(raw.major_id) || 0,
    course_id: Number(raw.course_id) || 0,
    college_id: raw.college_id ? Number(raw.college_id) : null,
    college_local_id: raw.college_local_id?.trim() || null,
    course_code: raw.course_code || null,
    credits: Number.isFinite(credits) ? credits : null,
    syllabus_outline: raw.syllabus_outline || null,
    display_label: raw.display_label?.trim() || undefined,
  };
}

export function courseOfferingToApiPayload(offering: WizardCourseOfferingDraft) {
  const {
    local_id: _localId,
    level_id: _levelId,
    program_id: _programId,
    major_id: _majorId,
    display_label,
    course_code,
    credits,
    syllabus_outline,
    ...rest
  } = offering;
  return {
    course_id: offering.course_id > 0 ? Number(rest.course_id) : null,
    college_id: rest.college_id ? Number(rest.college_id) : null,
    college_local_id: rest.college_local_id?.trim() || null,
    level_id: offering.level_id > 0 ? offering.level_id : null,
    program_id: offering.program_id?.trim() ? offering.program_id : null,
    major_id: offering.major_id > 0 ? offering.major_id : null,
    course_code: course_code || null,
    credits: credits ?? null,
    syllabus_outline: syllabus_outline || null,
    display_label: display_label?.trim() || null,
  };
}
