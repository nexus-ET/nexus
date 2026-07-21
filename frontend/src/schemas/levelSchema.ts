import { z } from 'zod';

import { emptyToNull } from './wizard/shared';

export const levelSchema = z.object({
  name: z
    .string({ error: 'Name is required' })
    .trim()
    .min(1, 'Name is required')
    .max(100, 'Name must be 100 characters or fewer'),
  code: z
    .string({ error: 'Code is required' })
    .trim()
    .min(1, 'Code is required')
    .max(50, 'Code must be 50 characters or fewer')
    .regex(
      /^[A-Z0-9_]+$/i,
      'Code may only contain letters, numbers, and underscores'
    )
    .transform(value => value.toUpperCase()),
  description: z.preprocess(
    emptyToNull,
    z
      .string()
      .max(2000, 'Description must be 2000 characters or fewer')
      .nullable()
      .optional()
  ),
});

export type LevelFormValues = z.infer<typeof levelSchema>;

export const emptyLevelFormValues: LevelFormValues = {
  name: '',
  code: '',
  description: null,
};
