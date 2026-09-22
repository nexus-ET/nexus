import { z } from 'zod';

import { FRAMEWORK_DESCRIPTION_MAX_LENGTH } from './frameworkDescriptionLimits';
import { richTextField } from './wizard/shared';

const optionalSuperMajorCodeField = z
  .string()
  .trim()
  .max(80, 'Code must be 80 characters or fewer')
  .regex(/^[A-Za-z0-9_]*$/, 'Use letters, numbers, and underscores only')
  .transform(value => (value ? value.toUpperCase() : undefined))
  .optional();

export const superMajorSchema = z.object({
  name: z.string().trim().min(1, 'Super-major name is required').max(255),
  code: optionalSuperMajorCodeField,
  description: richTextField(FRAMEWORK_DESCRIPTION_MAX_LENGTH, 'Description'),
  sort_order: z.coerce.number().int().min(0).default(0),
  is_active: z.boolean().default(true),
});

export type SuperMajorFormValues = z.infer<typeof superMajorSchema>;

export const emptySuperMajorFormValues: SuperMajorFormValues = {
  name: '',
  code: '',
  description: null,
  sort_order: 0,
  is_active: true,
};
