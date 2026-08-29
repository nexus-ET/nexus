/** Fallback defaults when admin has not configured custom contact types. */
export const DEFAULT_EMAIL_CONTACT_TYPES = [
  'General',
  'Admissions',
  'Billing',
  'Support',
  'Legal',
] as const;

export const DEFAULT_PHONE_CONTACT_TYPES = [
  'Main Line',
  'Sales',
  'WhatsApp',
  'Support',
  'Billing',
] as const;

/** @deprecated Prefer useAdminSettingsStore / getEmailContactTypeOptions */
export const EMAIL_CONTACT_TYPES = DEFAULT_EMAIL_CONTACT_TYPES.map(value => ({
  value,
  label: value,
}));

/** @deprecated Prefer useAdminSettingsStore / getPhoneContactTypeOptions */
export const PHONE_CONTACT_TYPES = DEFAULT_PHONE_CONTACT_TYPES.map(value => ({
  value,
  label: value,
}));

/** Fax types mirror phone types. */
export const FAX_CONTACT_TYPES = PHONE_CONTACT_TYPES;

export const WEB_LINK_TYPES = [
  { value: 'Website', label: 'Website' },
  { value: 'Admissions', label: 'Admissions' },
  { value: 'Enquiries', label: 'Enquiries' },
  { value: 'Contact Page', label: 'Contact Page' },
  { value: 'Campus', label: 'Campus' },
  { value: 'College', label: 'College' },
] as const;

export const PHONE_TYPE_MAIN = DEFAULT_PHONE_CONTACT_TYPES[0];
export const FAX_TYPE_MAIN = PHONE_TYPE_MAIN;
export const EMAIL_TYPE_GENERAL = DEFAULT_EMAIL_CONTACT_TYPES[0];
export const WEB_LINK_TYPE_WEBSITE = 'Website';

export type PhoneContactType = string;
export type FaxContactType = string;
export type EmailContactType = string;
export type WebLinkType = (typeof WEB_LINK_TYPES)[number]['value'];

export type ContactTypeOption = { value: string; label: string };

export function toContactTypeOptions(types: readonly string[]): ContactTypeOption[] {
  return types
    .map(type => type.trim())
    .filter(Boolean)
    .map(type => ({ value: type, label: type }));
}

export function normalizeContactTypeLabel(raw: string): string {
  return raw.trim().replace(/\s+/g, ' ');
}
