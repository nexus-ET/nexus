export const INTERACTION_DAYS_OPTIONS = [
  { value: 5, label: 'Last 5 days' },
  { value: 15, label: 'Last 15 days' },
  { value: 30, label: 'Last 30 days' },
  { value: 0, label: 'All days' },
] as const;

export type InteractionDaysFilter = (typeof INTERACTION_DAYS_OPTIONS)[number]['value'];

export const DEFAULT_INTERACTION_DAYS: InteractionDaysFilter = 5;

export function buildLeadQueueQueryParams(
  days: InteractionDaysFilter,
  searchQuery: string
): string {
  const params = new URLSearchParams();
  const q = searchQuery.trim();
  if (q) {
    params.set('q', q);
  } else {
    params.set('days', String(days));
  }
  return params.toString();
}

export function interactionDaysEmptyLabel(days: InteractionDaysFilter): string {
  if (days === 0) return 'all time';
  const match = INTERACTION_DAYS_OPTIONS.find(option => option.value === days);
  return match?.label.toLowerCase() ?? `the last ${days} days`;
}
