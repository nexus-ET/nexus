/** @deprecated Import campus wizard types from `schemas/wizard/step2-campus` instead. */
export {
  campusToApiPayload,
  createEmptyWizardCampusDraft as createEmptyWizardCampus,
  hydrateWizardCampus,
  wizardCampusItemSchema as wizardCampusSchema,
  type WizardCampusItem,
} from '../schemas/wizard/step2-campus';

export interface CampusTypeRecord {
  id: number;
  code: string;
  name: string;
  description: string;
}

/** @deprecated Use WizardCampusItem from schemas/wizard/step2-campus */
export type WizardCampusFormState = import('../schemas/wizard/step2-campus').WizardCampusItem;

export const emptyWizardCampus = {
  local_id: '',
  name: '',
  campus_type_id: 0,
  description: null as string | null,
  address: null as string | null,
  country_id: 0,
  state_id: 0,
  location_id: 0,
  zipcode: null as string | null,
  phone_numbers: [''] as string[],
  fax_numbers: [] as { type: string; value: string }[],
  email_addresses: [''] as string[],
};
