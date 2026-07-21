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
  serializeContacts,
  type ContactEntry,
  webLinkListSchema,
} from '../contactEntry';

export const wizardCampusItemSchema = z.object({
  id: z.number().int().positive().optional(),
  local_id: z.string().optional(),
  city_label: z.string().optional(),
  country_label: z.string().optional(),
  state_label: z.string().optional(),
  name: z.string().min(1, 'Campus name is required').max(250),
  campus_type_id: z.number({ error: 'Campus type is required' }).int().positive('Campus type is required'),
  description: richTextField(2000, 'Campus description'),
  address: z.preprocess(
    emptyToNull,
    z.string().max(200, 'Campus address must be 200 characters or fewer').nullable().optional()
  ),
  country_id: z.number({ error: 'Country is required' }).int().positive('Country is required'),
  state_id: z.number({ error: 'State is required' }).int().positive('State is required'),
  location_id: z.number({ error: 'City is required' }).int().positive('City is required'),
  zipcode: z.preprocess(
    emptyToNull,
    z.string().max(10, 'Zipcode must be 10 characters or fewer').nullable().optional()
  ),
  phone_numbers: phoneContactListSchema,
  fax_numbers: faxContactListSchema,
  email_addresses: emailContactListSchema,
  web_links: webLinkListSchema,
});

export const wizardCampusDraftSchema = wizardCampusItemSchema;

export const wizardCampusesStepSchema = z
  .array(wizardCampusItemSchema)
  .min(1, 'Add at least one campus to the list.');

export type WizardCampusFormValues = z.input<typeof wizardCampusDraftSchema>;
export type WizardCampusItem = z.infer<typeof wizardCampusItemSchema>;

export const emptyWizardCampusDraft: WizardCampusFormValues = {
  local_id: '',
  name: '',
  campus_type_id: undefined,
  description: null,
  address: null,
  country_id: undefined,
  state_id: undefined,
  location_id: undefined,
  zipcode: null,
  phone_numbers: createDefaultPhoneContacts(),
  fax_numbers: createDefaultFaxContacts(),
  email_addresses: createDefaultEmailContacts(),
  web_links: createDefaultWebLinks(),
};

export function createEmptyWizardCampusDraft(): WizardCampusFormValues {
  return {
    ...emptyWizardCampusDraft,
    local_id: crypto.randomUUID(),
    phone_numbers: createDefaultPhoneContacts(),
    fax_numbers: createDefaultFaxContacts(),
    email_addresses: createDefaultEmailContacts(),
    web_links: createDefaultWebLinks(),
  };
}

export function campusToApiPayload(campus: WizardCampusItem) {
  const { local_id: _localId, city_label: _cityLabel, ...rest } = campus;
  return {
    ...rest,
    name: campus.name.trim(),
    campus_type_id: Number(campus.campus_type_id),
    description: campus.description || null,
    address: campus.address?.trim() || null,
    country_id: campus.country_id || null,
    state_id: campus.state_id || null,
    location_id: Number(campus.location_id),
    zipcode: campus.zipcode?.trim() || null,
    phone_numbers: serializeContacts(campus.phone_numbers),
    fax_numbers: serializeContacts(campus.fax_numbers),
    email_addresses: serializeContacts(campus.email_addresses),
    web_links: serializeContacts(campus.web_links),
  };
}

export function hydrateWizardCampus(
  raw: Partial<WizardCampusItem> & { fax_number?: string | null }
): WizardCampusItem {
  const localId = raw.local_id || (raw.id ? String(raw.id) : crypto.randomUUID());
  return {
    ...createEmptyWizardCampusDraft(),
    ...raw,
    local_id: localId,
    campus_type_id: Number(raw.campus_type_id),
    country_id: Number(raw.country_id),
    state_id: Number(raw.state_id),
    location_id: Number(raw.location_id),
    phone_numbers: normalizePhoneContacts(raw.phone_numbers),
    fax_numbers: normalizeFaxContacts(raw.fax_numbers, raw.fax_number),
    email_addresses: normalizeEmailContacts(raw.email_addresses),
    web_links: normalizeWebLinks(raw.web_links),
  } as WizardCampusItem;
}

export type { ContactEntry };
