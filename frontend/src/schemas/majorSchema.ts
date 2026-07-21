import { z } from 'zod';

import { richTextField } from './wizard/shared';

const optionalMajorCodeField = z
  .string()
  .trim()
  .max(50, 'Code must be 50 characters or fewer')
  .regex(/^[A-Za-z0-9_]*$/, 'Use letters, numbers, and underscores only')
  .transform(value => (value ? value.toUpperCase() : undefined))
  .optional();

export const majorSchema = z.object({
  label: z.string().trim().min(1, 'Major name is required').max(255),
  code: optionalMajorCodeField,
  description: richTextField(5000, 'Description'),
  sort_order: z.coerce.number().int().min(0).default(0),
  is_other: z.boolean().default(false),
  is_active: z.boolean().default(true),
});

export type MajorFormValues = z.infer<typeof majorSchema>;

export const emptyMajorFormValues: MajorFormValues = {
  label: '',
  code: '',
  description: null,
  sort_order: 0,
  is_other: false,
  is_active: true,
};

// Backward-compatible aliases
export const educationMajorSchema = majorSchema;
export type EducationMajorFormValues = MajorFormValues;
export const emptyEducationMajorFormValues = emptyMajorFormValues;
