import { apiFetch } from './api';

export interface PaginatedListResponse<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

/** Accept paginated `{ items }` or a legacy bare array from older API builds. */
export function normalizePaginatedList<T>(data: unknown): PaginatedListResponse<T> {
  if (Array.isArray(data)) {
    return {
      items: data as T[],
      page: 1,
      page_size: data.length || 25,
      total: data.length,
      total_pages: data.length > 0 ? 1 : 0,
    };
  }
  if (data && typeof data === 'object') {
    const payload = data as Partial<PaginatedListResponse<T>>;
    const items = Array.isArray(payload.items) ? payload.items : [];
    return {
      items,
      page: Number(payload.page) || 1,
      page_size: Number(payload.page_size) || items.length || 25,
      total: Number(payload.total) || items.length,
      total_pages: Number(payload.total_pages) || (items.length > 0 ? 1 : 0),
    };
  }
  return { items: [], page: 1, page_size: 25, total: 0, total_pages: 0 };
}

/** Fetch all items from a paginated academia list endpoint (for dropdowns). */
export async function fetchAcademiaListItems<T>(
  endpoint: string,
  extraParams?: Record<string, string | undefined>
): Promise<T[]> {
  const pageSize = 100;
  let page = 1;
  let allItems: T[] = [];
  let totalPages = 1;

  while (page <= totalPages) {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(extraParams ?? {})) {
      if (value != null && value !== '') params.set(key, value);
    }
    params.set('page', String(page));
    params.set('page_size', String(pageSize));

    const data = normalizePaginatedList<T>(
      await apiFetch<PaginatedListResponse<T> | T[]>(`${endpoint}?${params}`)
    );
    allItems = allItems.concat(data.items);
    // Legacy bare-array responses are complete in one shot.
    if (page === 1 && data.page_size === data.items.length && data.total === data.items.length) {
      break;
    }
    totalPages = Math.max(data.total_pages || 1, 1);
    page += 1;
  }

  return allItems;
}
