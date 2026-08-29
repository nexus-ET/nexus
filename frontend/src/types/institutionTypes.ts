import { apiFetch } from '../utils/api';

export interface InstitutionTypeRecord {
  id: number;
  code: string;
  name: string;
  is_active: boolean;
  sort_order: number;
}

export interface InstitutionTypeSelectOption {
  value: string;
  label: string;
}

/** Legacy string labels from pre-lookup filter URLs / forms. */
export const LEGACY_INSTITUTION_TYPE_LABELS: Record<string, string> = {
  'Public / State University': 'PUBLIC_STATE',
  'Public / State': 'PUBLIC_STATE',
  'Private University': 'PRIVATE',
  Private: 'PRIVATE',
  'Community College / Technical Institute': 'COMMUNITY_COLLEGE',
  'Community College': 'COMMUNITY_COLLEGE',
  'Technical Institute': 'TECHNICAL_INSTITUTE',
  Others: 'OTHERS',
};

export function institutionTypeSelectOptions(
  types: InstitutionTypeRecord[]
): InstitutionTypeSelectOption[] {
  return types
    .filter(type => type.is_active !== false)
    .sort(
      (left, right) =>
        left.sort_order - right.sort_order ||
        left.name.localeCompare(right.name) ||
        left.id - right.id
    )
    .map(type => ({ value: String(type.id), label: type.name }));
}

export async function fetchInstitutionTypes(): Promise<InstitutionTypeRecord[]> {
  const data = await apiFetch<InstitutionTypeRecord[]>('academia/institution-types');
  return Array.isArray(data) ? data : [];
}

/** Map a legacy institution_type text filter to institution_type_id once types are loaded. */
export function resolveLegacyInstitutionTypeId(
  legacyLabel: string,
  types: InstitutionTypeRecord[]
): string | null {
  const trimmed = legacyLabel.trim();
  if (!trimmed) return null;

  const byName = types.find(type => type.name === trimmed);
  if (byName) return String(byName.id);

  const code = LEGACY_INSTITUTION_TYPE_LABELS[trimmed];
  if (code) {
    const byCode = types.find(type => type.code === code);
    if (byCode) return String(byCode.id);
  }

  return null;
}
