import { apiFetch } from './api';

export type GeographyEntityType = 'country' | 'state' | 'city';

export interface GeographyStatusImpact {
  entity_type: GeographyEntityType;
  entity_id: number;
  entity_name: string;
  current_is_active: boolean;
  proposed_is_active: boolean;
  states: number;
  cities: number;
  institutions: number;
  campuses: number;
  colleges: number;
  has_links: boolean;
  message: string;
}

export async function fetchGeographyStatusImpact(
  entityType: GeographyEntityType,
  entityId: number,
  proposedIsActive: boolean
): Promise<GeographyStatusImpact> {
  return apiFetch<GeographyStatusImpact>(
    `academia/geography/status-impact?entity_type=${encodeURIComponent(entityType)}&entity_id=${entityId}&is_active=${proposedIsActive ? 'true' : 'false'}`
  );
}

export function geographyEntityTypeFromKey(entityKey: string): GeographyEntityType | null {
  if (entityKey === 'countries') return 'country';
  if (entityKey === 'states') return 'state';
  if (entityKey === 'cities') return 'city';
  return null;
}
