import { z } from 'zod';

import { FRAMEWORK_DESCRIPTION_MAX_LENGTH } from './frameworkDescriptionLimits';
import { richTextField } from './wizard/shared';

export const subMajorSchema = z.object({
  name: z.string().trim().min(1, 'Sub-major name is required').max(255),
  major_id: z.coerce.number().int().positive('Select a parent major'),
  sub_major_description: richTextField(
    FRAMEWORK_DESCRIPTION_MAX_LENGTH,
    'Sub-major description'
  ),
});

export type SubMajorFormValues = z.infer<typeof subMajorSchema>;

export const emptySubMajorFormValues: SubMajorFormValues = {
  name: '',
  major_id: 0,
  sub_major_description: null,
};
