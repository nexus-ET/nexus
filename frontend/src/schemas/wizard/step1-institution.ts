import { z } from 'zod';

import { emptyToNull, richTextField } from './shared';
import {
  createDefaultEmailContacts,
  createDefaultFaxContacts,
  createDefaultPhoneContacts,
  createDefaultWebLinks,
  emailContactListSchema,
  faxContactListSchema,
  normalizeEmailContacts,
  normalizeFaxContacts,
  normalizePhoneContacts,
  normalizeWebLinks,
  phoneContactListSchema,
  primaryWebUrl,
  serializeContacts,
  webLinkListSchema,
} from '../contactEntry';

export const INSTITUTION_TYPE_OPTIONS = [
  { value: 'Public / State University', label: 'Public / State University' },
  { value: 'Private University', label: 'Private University' },
  {
    value: 'Community College / Technical Institute',
    label: 'Community College / Technical Institute',
  },
  { value: 'Others', label: 'Others' },
] as const;

export const RANKING_TIER_OPTIONS = [
  { value: 'Top 100 (Global Elite)', label: 'Top 100 (Global Elite)' },
  { value: 'Top 300 (Highly Research-Intensive)', label: 'Top 300 (Highly Research-Intensive)' },
  { value: 'Top 500 (Broad Academic Excellence)', label: 'Top 500 (Broad Academic Excellence)' },
  { value: 'Others', label: 'Others' },
] as const;

export const CURRENCY_OPTIONS = [
  { value: 'USD', label: 'USD — US Dollar' },
  { value: 'EUR', label: 'EUR — Euro' },
  { value: 'GBP', label: 'GBP — British Pound' },
  { value: 'CAD', label: 'CAD — Canadian Dollar' },
  { value: 'AUD', label: 'AUD — Australian Dollar' },
  { value: 'INR', label: 'INR — Indian Rupee' },
  { value: 'CNY', label: 'CNY — Chinese Yuan' },
  { value: 'JPY', label: 'JPY — Japanese Yen' },
  { value: 'SGD', label: 'SGD — Singapore Dollar' },
  { value: 'AED', label: 'AED — UAE Dirham' },
  { value: 'CHF', label: 'CHF — Swiss Franc' },
  { value: 'NZD', label: 'NZD — New Zealand Dollar' },
] as const;

export const wizardInstitutionSchema = z.object({
  institution_type: z.string().min(1, 'Institution type is required').max(80),
  company_affiliated: z.boolean().nullable().optional(),
  ranking_tier_global: z.preprocess(emptyToNull, z.string().max(120).nullable().optional()),
  ad_promotion_flag: z.boolean().nullable().optional(),
  web_links: webLinkListSchema,
  currency_type: z.string().max(10).default('USD'),
  students_count: z.preprocess(emptyToNull, z.string().max(250).nullable().optional()),
  address: z.preprocess(
    emptyToNull,
    z.string().max(200, 'Address must be 200 characters or fewer').nullable().optional()
  ),
  country_id: z.number({ error: 'Country is required' }).int().positive('Country is required'),
  state_id: z.number({ error: 'State is required' }).int().positive('State is required'),
  city_id: z.number({ error: 'City is required' }).int().positive('City is required'),
  zipcode: z.preprocess(emptyToNull, z.string().max(10).nullable().optional()),
  phone_numbers: phoneContactListSchema,
  fax_numbers: faxContactListSchema,
  email_addresses: emailContactListSchema,
  code: z.preprocess(emptyToNull, z.string().max(50).nullable().optional()),
  name: z.string().min(1, 'Institution long name is required').max(200),
  dean_name: z.preprocess(emptyToNull, z.string().max(255).nullable().optional()),
  accreditation_details: richTextField(2500, 'Accreditation details'),
  short_description: richTextField(2500, 'Institution short description'),
  long_description: richTextField(5000, 'Institution overview / mission'),
});

export type WizardInstitutionFormValues = z.infer<typeof wizardInstitutionSchema>;

export const emptyWizardInstitution: WizardInstitutionFormValues = {
  institution_type: '',
  company_affiliated: null,
  ranking_tier_global: null,
  ad_promotion_flag: null,
  web_links: createDefaultWebLinks(),
  currency_type: 'USD',
  students_count: null,
  address: null,
  country_id: 0,
  state_id: 0,
  city_id: 0,
  zipcode: null,
  phone_numbers: createDefaultPhoneContacts(),
  fax_numbers: createDefaultFaxContacts(),
  email_addresses: createDefaultEmailContacts(),
  code: null,
  name: '',
  dean_name: null,
  accreditation_details: null,
  short_description: null,
  long_description: null,
};

export function normalizeWizardInstitution(
  values: Partial<WizardInstitutionFormValues> & {
    institution_type?: string;
    ranking_tier_global?: string | null;
    web_links?: unknown;
    institution_web_url?: string | null;
    students_count?: string | null;
    address?: string | null;
    zipcode?: string | null;
    fax_numbers?: unknown;
    fax_number?: string | null;
    phone_numbers?: unknown;
    email_addresses?: unknown;
    code?: string | null;
    dean_name?: string | null;
    accreditation_details?: string | null;
    short_description?: string | null;
    long_description?: string | null;
    country_id?: number | null;
    state_id?: number | null;
    city_id?: number | null;
  }
): WizardInstitutionFormValues {
  return {
    ...emptyWizardInstitution,
    ...values,
    institution_type: values.institution_type || '',
    ranking_tier_global: values.ranking_tier_global || null,
    web_links: normalizeWebLinks(values.web_links, values.institution_web_url),
    students_count: values.students_count || null,
    address: values.address || null,
    zipcode: values.zipcode || null,
    fax_numbers: normalizeFaxContacts(values.fax_numbers, values.fax_number),
    phone_numbers: normalizePhoneContacts(values.phone_numbers),
    email_addresses: normalizeEmailContacts(values.email_addresses),
    code: values.code || null,
    name: values.name || '',
    dean_name: values.dean_name || null,
    accreditation_details: values.accreditation_details || null,
    short_description: values.short_description || null,
    long_description: values.long_description || null,
    country_id: values.country_id || 0,
    state_id: values.state_id || 0,
    city_id: values.city_id || 0,
    currency_type: values.currency_type || 'USD',
  };
}

export function institutionToApiPayload(values: WizardInstitutionFormValues) {
  const web_links = serializeContacts(values.web_links);
  return {
    ...values,
    address: values.address?.trim() || null,
    zipcode: values.zipcode?.trim() || null,
    phone_numbers: serializeContacts(values.phone_numbers),
    fax_numbers: serializeContacts(values.fax_numbers),
    email_addresses: serializeContacts(values.email_addresses),
    web_links,
    // Keep legacy single-URL column in sync with the Website (or first) link.
    institution_web_url: primaryWebUrl(values.web_links),
    name: values.name.trim(),
    dean_name: values.dean_name?.trim() || null,
  };
}
