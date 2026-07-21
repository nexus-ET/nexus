import { z } from 'zod';

export const emptyToNull = (value: unknown) => {
  if (value === undefined || value === null) return null;
  if (typeof value === 'string' && !value.trim()) return null;
  return value;
};

export const stripHtml = (html: string) =>
  html
    .replace(/<[^>]*>/g, ' ')
    .replace(/&nbsp;/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

export const richTextField = (max: number, fieldLabel = 'Field') =>
  z.preprocess(
    emptyToNull,
    z
      .string()
      .nullable()
      .optional()
      .refine(
        value => {
          if (!value) return true;
          return stripHtml(value).length <= max;
        },
        { message: `${fieldLabel} must be ${max} characters or fewer` }
      )
  );

export const optionalUrlField = (
  max = 250,
  message = 'Website URL must be a valid link'
) =>
  z.preprocess(
    emptyToNull,
    z
      .string()
      .max(max)
      .nullable()
      .optional()
      .refine(value => {
        if (!value) return true;
        try {
          const parsed = new URL(value);
          return parsed.protocol === 'http:' || parsed.protocol === 'https:';
        } catch {
          return false;
        }
      }, message)
  );

export const optionalEmailField = (message = 'Enter a valid email address') =>
  z.preprocess(
    emptyToNull,
    z.string().max(120).nullable().optional().refine(value => {
      if (!value) return true;
      return z.string().email().safeParse(value).success;
    }, message)
  );

export const IMAGE_MIME_TYPES = [
  'image/jpeg',
  'image/png',
  'image/webp',
  'image/svg+xml',
] as const;

export const MAX_PICTURE_BYTES = 500 * 1024;

export function validatePictureFile(file: File | null | undefined): string | null {
  if (!file) return null;
  if (!IMAGE_MIME_TYPES.includes(file.type as (typeof IMAGE_MIME_TYPES)[number])) {
    return 'Image must be SVG, PNG, WebP, or JPEG';
  }
  if (file.size > MAX_PICTURE_BYTES) {
    return 'Image must be 500 KB or smaller';
  }
  return null;
}
