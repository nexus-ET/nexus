import { z } from 'zod';

import { frameworkLevelIdField } from './academicFrameworkHierarchy';
import { emptyToNull, richTextField } from './wizard/shared';

export const programSchema = z.object({
  country_id: z.coerce.number().int().positive({ message: 'Country is required' }),
  institution_id: z.coerce.number().int().positive({ message: 'Institution is required' }),
  college_id: z.coerce.number().int().positive().optional().nullable(),
  level_id: frameworkLevelIdField,
  major_ids: z.array(z.coerce.number().int().positive()).default([]),
  sub_major_ids: z.array(z.coerce.number().int().positive()).default([]),
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
  program_url: z.preprocess(
    emptyToNull,
    z
      .string()
      .trim()
      .max(2048, 'URL must be 2048 characters or fewer')
      .url('Enter a valid URL')
      .nullable()
      .optional()
  ),
  is_active: z.boolean().default(true),
  sort_order: z.coerce.number().int().min(0).default(0),
  intake_ids: z.array(z.coerce.number().int().positive()).default([]),
});

export type ProgramFormValues = z.infer<typeof programSchema>;

export const emptyProgramFormValues: ProgramFormValues = {
  country_id: 0,
  institution_id: 0,
  college_id: null,
  level_id: 0,
  major_ids: [],
  sub_major_ids: [],
  name: '',
  code: '',
  description: null,
  program_url: null,
  is_active: true,
  sort_order: 0,
  intake_ids: [],
};
