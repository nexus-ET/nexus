import type { ProspectsFilters } from '../types/prospect';
import { DEFAULT_PROSPECTS_FILTERS } from '../types/prospect';

export type ProspectDetailTab = 'overview' | 'history' | 'notes';

const SOURCE_TO_SLUG: Record<string, string> = {
  ALL: 'all',
  FACEBOOK_LEAD: 'facebook',
  INSTAGRAM_LEAD: 'instagram',
  WHATSAPP: 'whatsapp',
};

const SLUG_TO_SOURCE: Record<string, string> = {
  all: 'ALL',
  facebook: 'FACEBOOK_LEAD',
  fb: 'FACEBOOK_LEAD',
  instagram: 'INSTAGRAM_LEAD',
  ig: 'INSTAGRAM_LEAD',
  whatsapp: 'WHATSAPP',
};

export function sourceToSlug(source: string): string {
  return SOURCE_TO_SLUG[source] || source.toLowerCase();
}

export function slugToSource(slug: string | null): string {
  if (!slug) return DEFAULT_PROSPECTS_FILTERS.source;
  return SLUG_TO_SOURCE[slug.toLowerCase()] || slug.toUpperCase();
}

export function readFilters(params: URLSearchParams): ProspectsFilters {
  return {
    q: params.get('q') || '',
    source: slugToSource(params.get('source')),
    dateFrom: params.get('from') || '',
    dateTo: params.get('to') || '',
  };
}

export function readDetailTab(params: URLSearchParams): ProspectDetailTab {
  const tab = (params.get('tab') || 'overview').toLowerCase();
  if (tab === 'history' || tab === 'notes') return tab;
  return 'overview';
}

export function writeFilterParams(
  params: URLSearchParams,
  filters: ProspectsFilters,
  tab?: ProspectDetailTab
): URLSearchParams {
  const next = new URLSearchParams(params);

  if (filters.q) next.set('q', filters.q);
  else next.delete('q');

  if (filters.source && filters.source !== 'ALL') {
    next.set('source', sourceToSlug(filters.source));
  } else {
    next.delete('source');
  }

  if (filters.dateFrom) next.set('from', filters.dateFrom);
  else next.delete('from');

  if (filters.dateTo) next.set('to', filters.dateTo);
  else next.delete('to');

  if (tab && tab !== 'overview') next.set('tab', tab);
  else next.delete('tab');

  return next;
}

export function buildProspectsPath(
  leadId: number | null,
  filters: ProspectsFilters,
  tab?: ProspectDetailTab
): string {
  const params = writeFilterParams(new URLSearchParams(), filters, tab);
  const query = params.toString();
  const base = leadId ? `/prospects/${leadId}` : '/prospects';
  return query ? `${base}?${query}` : base;
}

export function prospectsScrollStorageKey(filters: ProspectsFilters): string {
  return [
    'prospects-scroll',
    filters.q,
    filters.source,
    filters.dateFrom,
    filters.dateTo,
  ].join('|');
}

export function parseLeadIdParam(raw: string | undefined): number | null {
  if (!raw) return null;
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}
