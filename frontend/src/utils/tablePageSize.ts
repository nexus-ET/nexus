export const TABLE_PAGE_SIZE_OPTIONS = [25, 50, 100] as const;
export type TablePageSize = (typeof TABLE_PAGE_SIZE_OPTIONS)[number];

export function isTablePageSize(value: number): value is TablePageSize {
  return value === 25 || value === 50 || value === 100;
}

export function readStoredTablePageSize(
  storageKey: string,
  fallback: TablePageSize = 25
): TablePageSize {
  if (typeof window === 'undefined') return fallback;
  try {
    const parsed = Number(window.localStorage.getItem(storageKey));
    if (isTablePageSize(parsed)) return parsed;
  } catch {
    // Ignore private mode / blocked storage.
  }
  return fallback;
}

export function storeTablePageSize(storageKey: string, pageSize: TablePageSize): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(storageKey, String(pageSize));
  } catch {
    // Ignore private mode / blocked storage.
  }
}
