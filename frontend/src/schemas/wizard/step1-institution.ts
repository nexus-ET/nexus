import { z } from 'zod';

import { institutionTypeSelectOptions } from '../../types/institutionTypes';
import { emptyToNull, richTextField } from './shared';
import {
  createDefaultEmailContacts,
  createDefaultFaxContacts,
  createDefaultPhoneContacts,
  createDefaultWebLinks,
  faxContactListSchema,
  optionalEmailContactListSchema,
  optionalPhoneContactListSchema,
  normalizeEmailContacts,
  normalizeFaxContacts,
  normalizePhoneContacts,
  normalizeWebLinks,
  primaryWebUrl,
  serializeContacts,
  webLinkListSchema,
} from '../contactEntry';

export { institutionTypeSelectOptions } from '../../types/institutionTypes';

export const RANKING_TIER_OPTIONS = [
  { value: 'Top 100 (Global Elite)', label: 'Top 100 (Global Elite)' },
  { value: 'Top 300 (Research-Intensive)', label: 'Top 300 (Research-Intensive)' },
  { value: 'Top 500 (Academic Excellence)', label: 'Top 500 (Academic Excellence)' },
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

const optionalText = z.preprocess(emptyToNull, z.string().nullable().optional());

export const INSTITUTION_PROFILE_TEXT_FIELDS = [
  { key: 'year_established', label: 'Year established', placeholder: 'e.g. 1861', hint: 'Free text — year or range is fine.' },
  { key: 'global_ranking', label: 'Global ranking', placeholder: 'e.g. QS #3 (2026)', hint: 'Text ranking, not a forced number.' },
  { key: 'national_ranking', label: 'National ranking', placeholder: 'e.g. #1 in the US', hint: 'Text ranking, not a forced number.' },
  {
    key: 'brochure_url',
    label: 'Brochure URL',
    placeholder: 'https://www.university.edu/brochure.pdf',
    hint: 'Public link to the institution brochure.',
    type: 'url' as const,
  },
  { key: 'tuition_fees', label: 'Tuition fees', placeholder: 'e.g. USD 55,000 per year', hint: 'Living-cost text; currency as written.' },
  { key: 'hostel_expenses', label: 'Hostel expenses', placeholder: 'e.g. USD 12,000 per year' },
  { key: 'food_expense', label: 'Food expense', placeholder: 'e.g. USD 4,500 per year' },
  { key: 'books_expense', label: 'Books expense', placeholder: 'e.g. USD 1,200 per year' },
  { key: 'commutation_expense', label: 'Commutation expense', placeholder: 'e.g. USD 800 per year' },
  { key: 'insurance_expense', label: 'Insurance expense', placeholder: 'e.g. USD 2,000 per year' },
  { key: 'medical_expense', label: 'Medical expense', placeholder: 'e.g. USD 600 per year' },
  { key: 'other_expense', label: 'Other expense', placeholder: 'e.g. personal / miscellaneous' },
] as const;

export type InstitutionProfileTextFieldKey = (typeof INSTITUTION_PROFILE_TEXT_FIELDS)[number]['key'];

export const wizardInstitutionSchema = z.object({
  institution_type_id: z.coerce
    .number({ error: 'Institution type is required' })
    .int()
    .positive('Institution type is required'),
  company_affiliated: z.boolean().nullable().optional(),
  ranking_tier_global: z.preprocess(emptyToNull, z.string().max(120).nullable().optional()),
  ad_promotion_flag: z.boolean().nullable().optional(),
  web_links: webLinkListSchema,
  currency_type: z.string().max(10).default('USD'),
  students_count: z.preprocess(emptyToNull, z.string().max(250).nullable().optional()),
  year_established: optionalText,
  global_ranking: optionalText,
  national_ranking: optionalText,
  brochure_url: optionalText,
  tuition_fees: optionalText,
  hostel_expenses: optionalText,
  food_expense: optionalText,
  books_expense: optionalText,
  commutation_expense: optionalText,
  insurance_expense: optionalText,
  medical_expense: optionalText,
  other_expense: optionalText,
  address: z.preprocess(
    emptyToNull,
    z.string().max(200, 'Address must be 200 characters or fewer').nullable().optional()
  ),
  country_id: z.number({ error: 'Country is required' }).int().positive('Country is required'),
  state_id: z.number({ error: 'State is required' }).int().positive('State is required'),
  city_id: z.number({ error: 'City is required' }).int().positive('City is required'),
  zipcode: z.preprocess(emptyToNull, z.string().max(10).nullable().optional()),
  phone_numbers: optionalPhoneContactListSchema,
  fax_numbers: faxContactListSchema,
  email_addresses: optionalEmailContactListSchema,
  code: z.preprocess(emptyToNull, z.string().max(50).nullable().optional()),
  name: z.string().min(1, 'Institution long name is required').max(200),
  dean_name: z.preprocess(emptyToNull, z.string().max(255).nullable().optional()),
  accreditation_details: richTextField(2500, 'Accreditation details'),
  short_description: richTextField(2500, 'Institution short description'),
  long_description: richTextField(5000, 'Institution overview / mission').optional(),
});

export type WizardInstitutionFormValues = z.infer<typeof wizardInstitutionSchema>;

export const emptyWizardInstitution: WizardInstitutionFormValues = {
  institution_type_id: 0,
  company_affiliated: null,
  ranking_tier_global: null,
  ad_promotion_flag: null,
  web_links: createDefaultWebLinks(),
  currency_type: 'USD',
  students_count: null,
  year_established: null,
  global_ranking: null,
  national_ranking: null,
  brochure_url: null,
  tuition_fees: null,
  hostel_expenses: null,
  food_expense: null,
  books_expense: null,
  commutation_expense: null,
  insurance_expense: null,
  medical_expense: null,
  other_expense: null,
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
    institution_type_id?: number | null;
    ranking_tier_global?: string | null;
    web_links?: unknown;
    institution_web_url?: string | null;
    students_count?: string | null;
    year_established?: string | null;
    global_ranking?: string | null;
    national_ranking?: string | null;
    brochure_url?: string | null;
    tuition_fees?: string | null;
    hostel_expenses?: string | null;
    food_expense?: string | null;
    books_expense?: string | null;
    commutation_expense?: string | null;
    insurance_expense?: string | null;
    medical_expense?: string | null;
    other_expense?: string | null;
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
    institution_type_id: Number(values.institution_type_id) || 0,
    ranking_tier_global: values.ranking_tier_global || null,
    web_links: normalizeWebLinks(values.web_links, values.institution_web_url),
    students_count: values.students_count || null,
    year_established: values.year_established || null,
    global_ranking: values.global_ranking || null,
    national_ranking: values.national_ranking || null,
    brochure_url: values.brochure_url || null,
    tuition_fees: values.tuition_fees || null,
    hostel_expenses: values.hostel_expenses || null,
    food_expense: values.food_expense || null,
    books_expense: values.books_expense || null,
    commutation_expense: values.commutation_expense || null,
    insurance_expense: values.insurance_expense || null,
    medical_expense: values.medical_expense || null,
    other_expense: values.other_expense || null,
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
