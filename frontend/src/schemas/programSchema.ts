import { z } from 'zod';

import { frameworkLevelIdField } from './academicFrameworkHierarchy';
import { emptyToNull, richTextField } from './wizard/shared';

export const programSchema = z
  .object({
    level_id: frameworkLevelIdField,
    major_ids: z.array(z.coerce.number().int().positive()).default([]),
    name: z.string().trim().min(1, 'Program name is required').max(120),
    code: z.preprocess(
      emptyToNull,
      z
        .string()
        .max(50)
        .regex(/^[A-Za-z0-9_]+$/, 'Use letters, numbers, and underscores only')
        .transform(value => value.toUpperCase())
        .nullable()
        .optional()
    ),
    description: richTextField(5000, 'Description'),
    is_active: z.boolean().default(true),
    sort_order: z.coerce.number().int().min(0).default(0),
    institution_id: z.coerce.number().int().positive().optional().nullable(),
    intake_ids: z.array(z.coerce.number().int().positive()).default([]),
  })
  .superRefine((value, ctx) => {
    if (!value.is_active || !value.institution_id) return;
    if (!value.intake_ids.length) {
      ctx.addIssue({
        code: 'custom',
        message: 'Active programs must be assigned at least one Open intake term.',
        path: ['intake_ids'],
      });
    }
  });

export type ProgramFormValues = z.infer<typeof programSchema>;

export const emptyProgramFormValues: ProgramFormValues = {
  level_id: 0,
  major_ids: [],
  name: '',
  code: '',
  description: null,
  is_active: true,
  sort_order: 0,
  institution_id: null,
  intake_ids: [],
};
