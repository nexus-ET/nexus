import { apiFetch } from '../utils/api';

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

export interface CampusTypeSelectOption {
  value: string;
  label: string;
}

/** Display name only — strip a trailing "(CODE)" suffix if already embedded in name. */
export function campusTypeDisplayName(type: Pick<CampusTypeRecord, 'code' | 'name'>): string {
  const name = type.name.trim();
  const code = type.code.trim();
  if (!code) return name;

  const suffix = `(${code})`;
  if (name.endsWith(suffix)) {
    return name.slice(0, -suffix.length).trim();
  }

  const bracketMatch = name.match(/^(.+?)\s*\(([^)]+)\)\s*$/);
  if (bracketMatch && bracketMatch[2].trim().toLowerCase() === code.toLowerCase()) {
    return bracketMatch[1].trim();
  }

  return name;
}

export function campusTypeSelectOptions(types: CampusTypeRecord[]): CampusTypeSelectOption[] {
  const seenIds = new Set<number>();
  const seenCodes = new Set<string>();

  return types
    .slice()
    .sort(
      (left, right) =>
        left.id - right.id || left.name.localeCompare(right.name) || left.code.localeCompare(right.code)
    )
    .filter(type => {
      const codeKey = type.code.trim().toLowerCase();
      if (!codeKey || seenIds.has(type.id) || seenCodes.has(codeKey)) {
        return false;
      }
      seenIds.add(type.id);
      seenCodes.add(codeKey);
      return true;
    })
    .map(type => ({
      value: String(type.id),
      label: campusTypeDisplayName(type),
    }));
}

export async function fetchCampusTypes(): Promise<CampusTypeRecord[]> {
  const data = await apiFetch<CampusTypeRecord[]>('academia/campus-types');
  return Array.isArray(data) ? data : [];
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
