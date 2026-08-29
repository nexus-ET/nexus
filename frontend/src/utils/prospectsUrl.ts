import type { ProspectsFilters } from '../types/prospect';
import { DEFAULT_PROSPECTS_FILTERS } from '../types/prospect';
import {
  PIPELINE_SUBPROCESS_PARAM,
  defaultSubprocessForBasePath,
  isDefaultPipelineSubprocess,
} from './studentPipelineProcess';
import {
  isContactStatusFilter,
  type ContactStatusFilter,
} from './leadQueueFilters';
import {
  isTablePageSize,
  readStoredTablePageSize,
  type TablePageSize,
} from './tablePageSize';

export type ProspectDetailTab = 'overview' | 'history' | 'notes';

export const PROSPECTS_PAGE_SIZE_KEY = 'nexus.prospects.pageSize';

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

function readPageSize(params: URLSearchParams): TablePageSize {
  const raw = Number(params.get('page_size') || params.get('limit') || '');
  if (isTablePageSize(raw)) return raw;
  return readStoredTablePageSize(PROSPECTS_PAGE_SIZE_KEY, DEFAULT_PROSPECTS_FILTERS.pageSize);
}

function readPage(params: URLSearchParams): number {
  const raw = Number(params.get('page') || '');
  if (Number.isFinite(raw) && raw >= 1) return Math.floor(raw);
  return DEFAULT_PROSPECTS_FILTERS.page;
}

function readContactStatus(params: URLSearchParams): ContactStatusFilter {
  const raw = params.get('contact') || params.get('contact_status') || '';
  if (isContactStatusFilter(raw)) return raw;
  return DEFAULT_PROSPECTS_FILTERS.contactStatus;
}

export function readFilters(params: URLSearchParams, fixedCategory = ''): ProspectsFilters {
  return {
    q: params.get('q') || '',
    source: slugToSource(params.get('source')),
    dateFrom: params.get('from') || '',
    dateTo: params.get('to') || '',
    category: fixedCategory || params.get('category') || '',
    contactStatus: readContactStatus(params),
    page: readPage(params),
    pageSize: readPageSize(params),
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
  tab?: ProspectDetailTab,
  subprocess?: string | null,
  extraDefaultSubprocess?: string | null
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

  if (filters.contactStatus && filters.contactStatus !== 'all') {
    next.set('contact', filters.contactStatus);
  } else {
    next.delete('contact');
  }
  next.delete('contact_status');

  if (filters.page && filters.page > 1) next.set('page', String(filters.page));
  else next.delete('page');

  if (filters.pageSize && filters.pageSize !== DEFAULT_PROSPECTS_FILTERS.pageSize) {
    next.set('page_size', String(filters.pageSize));
  } else {
    next.delete('page_size');
  }
  next.delete('limit');

  if (tab && tab !== 'overview') next.set('tab', tab);
  else next.delete('tab');

  const defaultSubprocess = extraDefaultSubprocess;
  if (subprocess && !isDefaultPipelineSubprocess(subprocess, defaultSubprocess)) {
    next.set(PIPELINE_SUBPROCESS_PARAM, subprocess.trim());
  } else {
    next.delete(PIPELINE_SUBPROCESS_PARAM);
  }

  return next;
}

export function buildProspectsPath(
  leadId: number | null,
  filters: ProspectsFilters,
  tab?: ProspectDetailTab,
  basePath = '/prospects',
  subprocess?: string | null
): string {
  const params = writeFilterParams(
    new URLSearchParams(),
    filters,
    tab,
    subprocess,
    defaultSubprocessForBasePath(basePath)
  );
  const query = params.toString();
  const base = leadId ? `${basePath}/${leadId}` : basePath;
  return query ? `${base}?${query}` : base;
}

export function prospectsScrollStorageKey(filters: ProspectsFilters, basePath = '/prospects'): string {
  return [
    `${basePath}-scroll`,
    filters.q,
    filters.source,
    filters.dateFrom,
    filters.dateTo,
    filters.category,
    filters.contactStatus,
    filters.page,
    filters.pageSize,
  ].join('|');
}

export function parseLeadIdParam(raw: string | undefined): number | null {
  if (!raw) return null;
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}
