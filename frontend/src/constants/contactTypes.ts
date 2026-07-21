export const PHONE_CONTACT_TYPES = [
  { value: 'Main', label: 'Main' },
  { value: 'Admissions', label: 'Admissions' },
  { value: 'Inquiries', label: 'Inquiries' },
  { value: 'Registrar', label: 'Registrar' },
  { value: 'Campus', label: 'Campus' },
  { value: 'Other', label: 'Other' },
] as const;

/** Fax types mirror phone types. */
export const FAX_CONTACT_TYPES = PHONE_CONTACT_TYPES;

export const EMAIL_CONTACT_TYPES = [
  { value: 'General', label: 'General' },
  { value: 'Admissions', label: 'Admissions' },
  { value: 'Support', label: 'Support' },
  { value: 'Registrar', label: 'Registrar' },
  { value: 'Inquiries', label: 'Inquiries' },
  { value: 'Applications help', label: 'Applications help' },
  { value: 'Financial aid', label: 'Financial aid' },
  { value: 'Other', label: 'Other' },
] as const;

export const WEB_LINK_TYPES = [
  { value: 'Website', label: 'Website' },
  { value: 'Admissions', label: 'Admissions' },
  { value: 'Enquiries', label: 'Enquiries' },
  { value: 'Contact Page', label: 'Contact Page' },
  { value: 'Campus', label: 'Campus' },
  { value: 'College', label: 'College' },
] as const;

export const PHONE_TYPE_MAIN = 'Main';
export const FAX_TYPE_MAIN = PHONE_TYPE_MAIN;
export const EMAIL_TYPE_GENERAL = 'General';
export const WEB_LINK_TYPE_WEBSITE = 'Website';

export type PhoneContactType = (typeof PHONE_CONTACT_TYPES)[number]['value'];
export type FaxContactType = PhoneContactType;
export type EmailContactType = (typeof EMAIL_CONTACT_TYPES)[number]['value'];
export type WebLinkType = (typeof WEB_LINK_TYPES)[number]['value'];
