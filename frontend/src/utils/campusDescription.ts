import { stripHtml } from '../schemas/wizard/shared';

export const CAMPUS_DESCRIPTION_PREVIEW_LEN = 80;

export function campusDescriptionPreview(description: string | null | undefined): {
  preview: string;
  title?: string;
} {
  const text = stripHtml(description || '');
  if (!text) return { preview: '—' };
  if (text.length <= CAMPUS_DESCRIPTION_PREVIEW_LEN) {
    return { preview: text, title: text };
  }
  return {
    preview: `${text.slice(0, CAMPUS_DESCRIPTION_PREVIEW_LEN).trimEnd()}…`,
    title: text,
  };
}
