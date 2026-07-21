export type DigitalPlatform =
  | 'GITHUB'
  | 'LINKEDIN'
  | 'PERSONAL_PORTFOLIO'
  | 'GOOGLE_SCHOLAR'
  | 'RESEARCHGATE'
  | 'BEHANCE'
  | 'DRIBBBLE'
  | 'KAGGLE'
  | 'DEVPOST'
  | 'OTHER';

export type DigitalPresenceCategory =
  | 'TECHNICAL'
  | 'PROFESSIONAL'
  | 'ACADEMIC'
  | 'CREATIVE'
  | 'OTHER';

export const ADMISSION_VALUE_NOTE_MAX_LENGTH = 1000;

export const PLATFORM_LABELS: Record<DigitalPlatform, string> = {
  GITHUB: 'GitHub',
  LINKEDIN: 'LinkedIn',
  PERSONAL_PORTFOLIO: 'Personal Portfolio',
  GOOGLE_SCHOLAR: 'Google Scholar',
  RESEARCHGATE: 'ResearchGate',
  BEHANCE: 'Behance',
  DRIBBBLE: 'Dribbble',
  KAGGLE: 'Kaggle',
  DEVPOST: 'Devpost',
  OTHER: 'Other',
};

export const CATEGORY_LABELS: Record<DigitalPresenceCategory, string> = {
  TECHNICAL: 'Technical',
  PROFESSIONAL: 'Professional',
  ACADEMIC: 'Academic',
  CREATIVE: 'Creative',
  OTHER: 'Other',
};

export const PLATFORM_DEFAULT_CATEGORY: Record<DigitalPlatform, DigitalPresenceCategory> = {
  GITHUB: 'TECHNICAL',
  KAGGLE: 'TECHNICAL',
  DEVPOST: 'TECHNICAL',
  LINKEDIN: 'PROFESSIONAL',
  PERSONAL_PORTFOLIO: 'PROFESSIONAL',
  GOOGLE_SCHOLAR: 'ACADEMIC',
  RESEARCHGATE: 'ACADEMIC',
  BEHANCE: 'CREATIVE',
  DRIBBBLE: 'CREATIVE',
  OTHER: 'OTHER',
};

export const PLATFORM_OPTIONS: DigitalPlatform[] = [
  'GITHUB',
  'LINKEDIN',
  'PERSONAL_PORTFOLIO',
  'GOOGLE_SCHOLAR',
  'RESEARCHGATE',
  'BEHANCE',
  'DRIBBBLE',
  'KAGGLE',
  'DEVPOST',
  'OTHER',
];

export const CATEGORY_OPTIONS: DigitalPresenceCategory[] = [
  'TECHNICAL',
  'PROFESSIONAL',
  'ACADEMIC',
  'CREATIVE',
  'OTHER',
];

const URL_PATTERN =
  /^https?:\/\/(?:localhost(?::\d{2,5})?|(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63})(?::\d{2,5})?(?:\/[^\s]*)?$/i;

export function normalizeWebUrl(value: string): string {
  const cleaned = value.trim();
  if (!cleaned) {
    throw new Error('URL is required.');
  }
  const withScheme = /^https?:\/\//i.test(cleaned) ? cleaned : `https://${cleaned}`;
  if (!URL_PATTERN.test(withScheme)) {
    throw new Error('Enter a valid web URL (include a domain such as example.com).');
  }
  return withScheme;
}

export interface DigitalPlatformOption {
  value: DigitalPlatform;
  label: string;
  default_category: DigitalPresenceCategory;
}

export interface DigitalPresenceCategoryOption {
  value: DigitalPresenceCategory;
  label: string;
}

export interface DigitalPresenceLinkRecord {
  id: number;
  platform_name: DigitalPlatform | null;
  platform_label: string | null;
  url: string | null;
  category: DigitalPresenceCategory | null;
  category_label: string | null;
  admission_value_note: string | null;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface DigitalPresenceLinksResponse {
  booking_id?: number | null;
  lead_id: number | null;
  platform_options: DigitalPlatformOption[];
  category_options: DigitalPresenceCategoryOption[];
  links: DigitalPresenceLinkRecord[];
  saved_at: string | null;
}

export interface DigitalPresenceLinkFormState {
  platform_name: DigitalPlatform | '';
  url: string;
  category: DigitalPresenceCategory | '';
  admission_value_note: string;
}

export const emptyDigitalPresenceLinkForm = (): DigitalPresenceLinkFormState => ({
  platform_name: '',
  url: '',
  category: '',
  admission_value_note: '',
});

export function linkToForm(record: DigitalPresenceLinkRecord): DigitalPresenceLinkFormState {
  return {
    platform_name: record.platform_name ?? '',
    url: record.url ?? '',
    category: record.category ?? '',
    admission_value_note: record.admission_value_note ?? '',
  };
}

export function formToLinkPayload(form: DigitalPresenceLinkFormState) {
  return {
    platform_name: form.platform_name || null,
    url: form.url.trim() ? normalizeWebUrl(form.url) : null,
    category: form.category || null,
    admission_value_note: form.admission_value_note.trim() || null,
  };
}

export function validateDigitalPresenceLinkForm(
  form: DigitalPresenceLinkFormState
): Record<string, string> {
  const errors: Record<string, string> = {};

  if (!form.platform_name) {
    errors.platform_name = 'Platform is required.';
  }
  if (!form.url.trim()) {
    errors.url = 'URL is required.';
  } else {
    try {
      normalizeWebUrl(form.url);
    } catch (err) {
      errors.url = err instanceof Error ? err.message : 'Enter a valid web URL.';
    }
  }
  if (!form.category) {
    errors.category = 'Category is required.';
  }
  if (form.admission_value_note.length > ADMISSION_VALUE_NOTE_MAX_LENGTH) {
    errors.admission_value_note = `Value to admission must be ${ADMISSION_VALUE_NOTE_MAX_LENGTH} characters or fewer.`;
  }

  return errors;
}

export const FALLBACK_PLATFORM_OPTIONS: DigitalPlatformOption[] = PLATFORM_OPTIONS.map(value => ({
  value,
  label: PLATFORM_LABELS[value],
  default_category: PLATFORM_DEFAULT_CATEGORY[value],
}));

export const FALLBACK_CATEGORY_OPTIONS: DigitalPresenceCategoryOption[] = CATEGORY_OPTIONS.map(
  value => ({
    value,
    label: CATEGORY_LABELS[value],
  })
);
