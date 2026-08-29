import { z } from 'zod';

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
  description: z
    .union([
      z.string().trim().max(5000, 'Description must be 5000 characters or fewer'),
      z.null(),
    ])
    .optional()
    .transform(value => {
      if (value == null) return null;
      const trimmed = value.trim();
      return trimmed || null;
    }),
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
