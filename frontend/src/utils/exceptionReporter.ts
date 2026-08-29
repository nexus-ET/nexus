/**
 * Best-effort client → Exception Report reporter.
 * Used by apiFetch, window error handlers, and React error boundaries.
 *
 * Intentionally avoids importing ./api to prevent circular deps.
 */

export type ClientExceptionSeverity = 'EXCEPTION' | 'ERROR' | 'WARNING' | 'OMISSION';

export interface ClientExceptionPayload {
  severity?: ClientExceptionSeverity;
  source?: string;
  category?: string;
  message: string;
  details?: string[];
  page_path?: string;
  exception_type?: string;
  related_resource?: string;
  related_id?: string;
}

const TOKEN_KEY = 'token';
const DEDUPE_WINDOW_MS = 60_000;
const TRANSIENT_RESOLVE_SESSION_KEY = 'nexus_exception_transient_resolved';
const recentFingerprints = new Map<string, number>();

function resolveBaseUrl(): string {
  const envUrl =
    (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_URL) ||
    (typeof process !== 'undefined' && process.env?.REACT_APP_API_URL);
  if (envUrl) return String(envUrl).trim().replace(/\/$/, '');
  const { protocol, host } = window.location;
  return `${protocol}//${host}/api/v1`;
}

function getStoredToken(): string | null {
  const sessionToken = sessionStorage.getItem(TOKEN_KEY)?.trim();
  if (sessionToken) return sessionToken;
  const legacyToken = localStorage.getItem(TOKEN_KEY)?.trim();
  if (legacyToken) {
    sessionStorage.setItem(TOKEN_KEY, legacyToken);
    localStorage.removeItem(TOKEN_KEY);
    return legacyToken;
  }
  return null;
}

function isTokenExpired(token: string | null | undefined): boolean {
  if (!token || token.split('.').length !== 3) return true;
  try {
    const payload = JSON.parse(atob(token.split('.')[1] ?? ''));
    if (!payload?.exp) return false;
    return Date.now() >= Number(payload.exp) * 1000;
  } catch {
    return true;
  }
}

/** Collapse unique resource IDs so N 404s on /courses/1,/courses/2 share one fingerprint. */
export function normalizeApiEndpoint(endpoint: string): string {
  const path = String(endpoint || '')
    .replace(/^\//, '')
    .split(/[?#]/)[0]
    .replace(/\/{2,}/g, '/');
  return path
    .replace(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi, ':id')
    .replace(/\/\d+(?=\/|$)/g, '/:id');
}

function isExceptionLogsEndpoint(endpoint: string): boolean {
  return normalizeApiEndpoint(endpoint).toLowerCase().includes('reports/exception-logs');
}

/** Lookups like academia/courses/123 — missing rows are expected, not an incident flood. */
function isExpectedMissingResource(endpoint: string): boolean {
  const path = normalizeApiEndpoint(endpoint);
  if (!path) return false;
  if (/\/:id(?:\/|$)/.test(path) || path.endsWith('/:id')) return true;
  return /^academia\/(courses|degrees|programs|education-majors|institutions|offerings)\//i.test(
    path
  );
}

function fingerprint(payload: ClientExceptionPayload): string {
  const related = normalizeApiEndpoint(payload.related_id || '');
  const messageCore = (payload.message || '')
    .replace(/https?:\/\/[^\s]+/gi, '')
    .replace(/\d+/g, ':n')
    .slice(0, 180);
  return [
    payload.severity || 'ERROR',
    payload.source || 'api_client',
    payload.category || 'general',
    payload.exception_type || '',
    messageCore,
    related,
  ].join('|');
}

function shouldSkipDuplicate(payload: ClientExceptionPayload): boolean {
  const key = fingerprint(payload);
  const now = Date.now();
  const last = recentFingerprints.get(key);
  if (last != null && now - last < DEDUPE_WINDOW_MS) {
    return true;
  }
  recentFingerprints.set(key, now);
  if (recentFingerprints.size > 200) {
    for (const [entryKey, at] of recentFingerprints) {
      if (now - at > DEDUPE_WINDOW_MS) recentFingerprints.delete(entryKey);
    }
  }
  return false;
}

/**
 * Fire-and-forget POST to Exception Report. Never throws to callers.
 */
export function reportClientException(payload: ClientExceptionPayload): void {
  try {
    const message = (payload.message || '').trim();
    if (!message) return;

    const haystack = `${message} ${(payload.details || []).join(' ')} ${payload.related_id || ''}`.toLowerCase();
    if (haystack.includes('reports/exception-logs')) return;
    if (/\b429\b/.test(haystack) || haystack.includes('too many requests')) return;

    const pagePath =
      payload.page_path ||
      (typeof window !== 'undefined' ? window.location.pathname : undefined);

    const body: ClientExceptionPayload = {
      severity: payload.severity || 'ERROR',
      source: payload.source || 'api_client',
      category: payload.category || 'general',
      message: message.slice(0, 4000),
      details: (payload.details || []).slice(0, 20).map(item => String(item).slice(0, 500)),
      page_path: pagePath,
      exception_type: payload.exception_type?.slice(0, 120),
      related_resource: payload.related_resource?.slice(0, 100),
      related_id: payload.related_id?.slice(0, 100),
    };

    if (shouldSkipDuplicate(body)) return;

    const token = getStoredToken();
    if (!token || isTokenExpired(token)) return;

    const base = resolveBaseUrl().replace(/\/$/, '');
    void fetch(`${base}/reports/exception-logs`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
        'X-Nexus-Page': pagePath || '',
        'ngrok-skip-browser-warning': 'true',
      },
      body: JSON.stringify(body),
    }).catch(() => {
      // Never block the original failure path.
    });
  } catch {
    // Swallow — reporting must never break the app.
  }
}

/**
 * After a healthy authenticated page load/refresh, auto-resolve transient
 * browser/UI exceptions with a standard resolution comment (once per tab session).
 */
export function autoResolveTransientExceptionsOnPageRefresh(): void {
  try {
    if (typeof window === 'undefined') return;
    if (sessionStorage.getItem(TRANSIENT_RESOLVE_SESSION_KEY) === '1') return;

    const token = getStoredToken();
    if (!token || isTokenExpired(token)) return;

    sessionStorage.setItem(TRANSIENT_RESOLVE_SESSION_KEY, '1');
    const base = resolveBaseUrl().replace(/\/$/, '');
    void fetch(`${base}/reports/exception-logs/auto-resolve`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
        'ngrok-skip-browser-warning': 'true',
      },
      body: JSON.stringify({ mode: 'page_refresh' }),
    }).catch(() => {
      sessionStorage.removeItem(TRANSIENT_RESOLVE_SESSION_KEY);
    });
  } catch {
    // Swallow — never block app startup.
  }
}

export function reportApiFailure(options: {
  endpoint: string;
  status?: number;
  detail?: string;
  kind: 'timeout' | 'http' | 'network';
  timeoutMs?: number;
}): void {
  const endpoint = options.endpoint.replace(/^\//, '');
  // Never report failures of the exception sink itself (breaks the 429 feedback loop).
  if (isExceptionLogsEndpoint(endpoint)) return;

  if (options.kind === 'timeout') {
    reportClientException({
      severity: 'ERROR',
      source: 'api_client',
      category: 'request_timeout',
      message: `Client request timed out after ${Math.round((options.timeoutMs || 0) / 1000)}s: ${endpoint}`,
      details: [`endpoint=${endpoint}`, `timeout_ms=${options.timeoutMs ?? ''}`],
      exception_type: 'AbortError',
      related_resource: 'api',
      related_id: endpoint.slice(0, 100),
    });
    return;
  }

  if (options.kind === 'network') {
    reportClientException({
      severity: 'ERROR',
      source: 'api_client',
      category: 'network_error',
      message: options.detail || `Network error calling ${endpoint}`,
      details: [`endpoint=${endpoint}`],
      exception_type: 'NetworkError',
      related_resource: 'api',
      related_id: endpoint.slice(0, 100),
    });
    return;
  }

  const status = options.status ?? 0;
  // Rate-limit responses must not be logged — reporting them retriggers 429s.
  if (status === 429) return;
  // Auth failures must not be logged — reporting them can 401/429 and eject the session.
  if (status === 401) return;
  if (status === 404 && isExpectedMissingResource(endpoint)) return;

  const severity: ClientExceptionSeverity =
    status >= 500 ? 'EXCEPTION' : status >= 400 ? 'ERROR' : 'WARNING';
  const normalized = normalizeApiEndpoint(endpoint);

  reportClientException({
    severity,
    source: 'api_client',
    category: 'http_error',
    message: `HTTP ${status} from ${normalized}${options.detail ? `: ${options.detail}` : ''}`,
    details: [`endpoint=${endpoint}`, `status=${status}`, options.detail || ''].filter(Boolean),
    exception_type: `HTTP_${status}`,
    related_resource: 'api',
    related_id: normalized.slice(0, 100),
  });
}
