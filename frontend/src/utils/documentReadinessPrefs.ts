const LAST_SCANNED_LEAD_KEY = 'nexus.documentReadiness.lastScannedLeadId';
const LAST_SEARCHED_LEAD_KEY = 'nexus.documentReadiness.lastSearchedLeadId';
const LAST_SEARCHED_QUERY_KEY = 'nexus.documentReadiness.lastSearchedQuery';

function readStoredInt(key: string): number | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    const parsed = Number(raw);
    return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : null;
  } catch {
    return null;
  }
}

function writeStoredInt(key: string, value: number): void {
  if (typeof window === 'undefined') return;
  if (!Number.isFinite(value) || value <= 0) return;
  try {
    window.localStorage.setItem(key, String(Math.floor(value)));
  } catch {
    // Ignore private mode / blocked storage.
  }
}

function readStoredString(key: string): string {
  if (typeof window === 'undefined') return '';
  try {
    return (window.localStorage.getItem(key) || '').trim();
  } catch {
    return '';
  }
}

function writeStoredString(key: string, value: string): void {
  if (typeof window === 'undefined') return;
  try {
    const trimmed = value.trim();
    if (trimmed) window.localStorage.setItem(key, trimmed);
    else window.localStorage.removeItem(key);
  } catch {
    // Ignore private mode / blocked storage.
  }
}

/** Most recently ScanX-processed / document-readiness activity lead. */
export function readLastScannedLeadId(): number | null {
  return readStoredInt(LAST_SCANNED_LEAD_KEY);
}

export function writeLastScannedLeadId(leadId: number): void {
  writeStoredInt(LAST_SCANNED_LEAD_KEY, leadId);
}

/** Last student selected from the Document Readiness list (search or click). */
export function readLastSearchedLeadId(): number | null {
  return readStoredInt(LAST_SEARCHED_LEAD_KEY);
}

export function writeLastSearchedLeadId(leadId: number): void {
  writeStoredInt(LAST_SEARCHED_LEAD_KEY, leadId);
}

/** Last search term used on Document Readiness. */
export function readLastSearchedQuery(): string {
  return readStoredString(LAST_SEARCHED_QUERY_KEY);
}

export function writeLastSearchedQuery(query: string): void {
  writeStoredString(LAST_SEARCHED_QUERY_KEY, query);
}

/**
 * Pick which lead to auto-open for Document Readiness.
 * Preference: last scanned (in-set when searching) → last searched lead → first result.
 */
export function pickDocumentReadinessLead(options: {
  items: Array<{ id: number }>;
  searchQuery: string;
  lastScannedLeadId: number | null;
  lastSearchedLeadId: number | null;
}): number | null {
  const { items, searchQuery, lastScannedLeadId, lastSearchedLeadId } = options;
  const q = searchQuery.trim();

  if (q) {
    if (items.length === 0) return null;
    if (lastScannedLeadId != null && items.some(item => item.id === lastScannedLeadId)) {
      return lastScannedLeadId;
    }
    if (lastSearchedLeadId != null && items.some(item => item.id === lastSearchedLeadId)) {
      return lastSearchedLeadId;
    }
    return items[0]?.id ?? null;
  }

  if (lastScannedLeadId != null) return lastScannedLeadId;
  if (lastSearchedLeadId != null) return lastSearchedLeadId;
  return items[0]?.id ?? null;
}
