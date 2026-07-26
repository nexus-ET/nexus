import {
  isTablePageSize,
  readStoredTablePageSize,
  storeTablePageSize,
  TABLE_PAGE_SIZE_OPTIONS,
  type TablePageSize,
} from './tablePageSize';

export const INTERACTION_DAYS_OPTIONS = [
  { value: 5, label: 'Last 5 days' },
  { value: 15, label: 'Last 15 days' },
  { value: 30, label: 'Last 30 days' },
  { value: 0, label: 'All days' },
] as const;

export type InteractionDaysFilter = (typeof INTERACTION_DAYS_OPTIONS)[number]['value'];

export const DEFAULT_INTERACTION_DAYS: InteractionDaysFilter = 5;

export const CONTACT_STATUS_OPTIONS = [
  { value: 'all', label: 'All' },
  { value: 'started', label: 'Chat started' },
  { value: 'not_started', label: 'Not contacted yet' },
] as const;

export type ContactStatusFilter = (typeof CONTACT_STATUS_OPTIONS)[number]['value'];

export const DEFAULT_CONTACT_STATUS: ContactStatusFilter = 'all';

export const AI_ACTIVE_PAGE_SIZE_KEY = 'nexus.aiActive.pageSize';
export const HANDOFFS_PAGE_SIZE_KEY = 'nexus.handoffs.pageSize';
export const LEAD_QUEUE_PAGE_SIZE_OPTIONS = TABLE_PAGE_SIZE_OPTIONS;
export type LeadQueuePageSize = TablePageSize;
export const DEFAULT_LEAD_QUEUE_PAGE_SIZE: LeadQueuePageSize = 50;

export function readLeadQueuePageSize(
  storageKey: string,
  fallback: LeadQueuePageSize = DEFAULT_LEAD_QUEUE_PAGE_SIZE
): LeadQueuePageSize {
  return readStoredTablePageSize(storageKey, fallback);
}

export function persistLeadQueuePageSize(storageKey: string, pageSize: LeadQueuePageSize): void {
  if (!isTablePageSize(pageSize)) return;
  storeTablePageSize(storageKey, pageSize);
}

export function isContactStatusFilter(value: unknown): value is ContactStatusFilter {
  return (
    value === 'all' || value === 'started' || value === 'not_started'
  );
}

export function buildLeadQueueQueryParams(
  days: InteractionDaysFilter,
  searchQuery: string,
  contactStatus: ContactStatusFilter = DEFAULT_CONTACT_STATUS
): string {
  const params = new URLSearchParams();
  const q = searchQuery.trim();
  if (q) {
    params.set('q', q);
  } else {
    params.set('days', String(days));
  }
  if (contactStatus) {
    params.set('contact_status', contactStatus);
  }
  return params.toString();
}

export function interactionDaysEmptyLabel(days: InteractionDaysFilter): string {
  if (days === 0) return 'all time';
  const match = INTERACTION_DAYS_OPTIONS.find(option => option.value === days);
  return match?.label.toLowerCase() ?? `the last ${days} days`;
}

export function formatViewingRecordsLabel(
  rangeStart: number,
  rangeEnd: number,
  totalCount: number
): string {
  if (totalCount <= 0) return 'Viewing 0 of 0 records';
  if (rangeStart === rangeEnd) {
    return `Viewing ${rangeStart} of ${totalCount} records`;
  }
  return `Viewing ${rangeStart}–${rangeEnd} of ${totalCount} records`;
}
