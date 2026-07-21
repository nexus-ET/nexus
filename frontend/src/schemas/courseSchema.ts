import { z } from 'zod';

import { emptyToNull, richTextField } from './wizard/shared';

const optionalCourseCodeField = z.preprocess(
  value => {
    const normalized = emptyToNull(value);
    return typeof normalized === 'string' ? normalized.toUpperCase() : normalized;
  },
  z
    .string()
    .max(50, 'Course code must be 50 characters or fewer')
    .regex(
      /^[A-Z0-9_-]+$/,
      'Course code may only contain letters, numbers, dashes, and underscores'
    )
    .nullish()
);

const courseNameField = z.preprocess(
  emptyToNull,
  z
    .string({ error: 'Course name is required' })
    .min(1, 'Course name is required')
    .max(255, 'Course name must be 255 characters or fewer')
);

export const courseSchema = z.object({
  major_ids: z
    .array(z.coerce.number().int().positive())
    .min(1, 'Select at least one major or discipline'),
  name: courseNameField,
  code: optionalCourseCodeField,
  description: richTextField(5000, 'Description'),
  is_active: z.boolean().default(true),
});

export type CourseFormValues = z.infer<typeof courseSchema>;

export const emptyCourseFormValues: CourseFormValues = {
  major_ids: [],
  name: '',
  code: '',
  description: null,
  is_active: true,
};
