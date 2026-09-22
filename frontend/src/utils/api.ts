// src/utils/api.ts

import { reportApiFailure } from './exceptionReporter';

/**
 * Dynamically resolves the API gateway base URL from the current window location.
 * Completely free of hardcoded host domains, ports, or protocols.
 */
export const resolveBaseUrl = (): string => {
  const envUrl =
    (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_URL) ||
    (typeof process !== 'undefined' && process.env?.REACT_APP_API_URL);

  if (envUrl) return envUrl.trim().replace(/\/$/, '');

  const { protocol, host } = window.location;
  return `${protocol}//${host}/api/v1`;
};

const BASE_URL = resolveBaseUrl();

const TOKEN_KEY = 'token';
const POST_LOGIN_REDIRECT_KEY = 'nexus:postLoginRedirect';

/** Per-tab session storage so multiple users can be logged in across tabs/windows. */
export const getStoredToken = (): string | null => {
  const sessionToken = sessionStorage.getItem(TOKEN_KEY)?.trim();
  if (sessionToken) return sessionToken;

  // One-time migration from legacy shared localStorage (avoids breaking existing sessions).
  const legacyToken = localStorage.getItem(TOKEN_KEY)?.trim();
  if (legacyToken) {
    sessionStorage.setItem(TOKEN_KEY, legacyToken);
    localStorage.removeItem(TOKEN_KEY);
    return legacyToken;
  }

  return null;
};

export const setSessionToken = (token: string): void => {
  sessionStorage.setItem(TOKEN_KEY, token);
  // Drop shared storage so another tab's login cannot overwrite this tab's session.
  localStorage.removeItem(TOKEN_KEY);
};

export const getCurrentUserId = (): number | null => {
  const token = getStoredToken();
  if (!token) return null;
  const payload = decodeJwtPayload(token);
  const sub = payload?.sub;
  return sub != null ? Number(sub) : null;
};

export const clearSession = (): void => {
  sessionStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(POST_LOGIN_REDIRECT_KEY);
};

export function isSafeInternalPath(path: string | null | undefined): boolean {
  if (!path || typeof path !== 'string') return false;
  const trimmed = path.trim();
  if (!trimmed.startsWith('/') || trimmed.startsWith('//') || trimmed.startsWith('/\\')) return false;
  if (trimmed.includes('://')) return false;
  const pathname = trimmed.split(/[?#]/)[0] || '/';
  return pathname !== '/login' && !pathname.startsWith('/login/');
}

export function rememberPostLoginRedirect(path?: string): void {
  const target =
    path?.trim() ||
    `${window.location.pathname}${window.location.search}${window.location.hash}`;
  if (!isSafeInternalPath(target)) return;
  sessionStorage.setItem(POST_LOGIN_REDIRECT_KEY, target);
}

export function consumePostLoginRedirect(): string | null {
  const stored = sessionStorage.getItem(POST_LOGIN_REDIRECT_KEY)?.trim() || null;
  sessionStorage.removeItem(POST_LOGIN_REDIRECT_KEY);
  return stored && isSafeInternalPath(stored) ? stored : null;
}

export const isValidTokenFormat = (token: string | null | undefined): boolean => {
  if (!token) return false;
  return token.split('.').length === 3;
};

/** Decode JWT payload (base64url). Returns null if the token cannot be decoded. */
function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const part = token.split('.')[1];
    if (!part) return null;
    const base64 = part.replace(/-/g, '+').replace(/_/g, '/');
    const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4);
    return JSON.parse(atob(padded)) as Record<string, unknown>;
  } catch {
    return null;
  }
}

/** Allow small client/server clock drift before treating a token as expired. */
const TOKEN_EXPIRY_SKEW_MS = 120_000;

export const isTokenExpired = (token: string | null | undefined): boolean => {
  if (!isValidTokenFormat(token)) return true;
  const payload = decodeJwtPayload(token!);
  // Do not force-logout on decode quirks — only when exp is present and past.
  if (!payload || payload.exp == null) return false;
  return Date.now() >= Number(payload.exp) * 1000 + TOKEN_EXPIRY_SKEW_MS;
};

export const hasValidSession = (): boolean => {
  const token = getStoredToken();
  return isValidTokenFormat(token) && !isTokenExpired(token);
};

const redirectToLogin = (): void => {
  if (window.location.pathname.startsWith('/login')) return;
  const returnTo = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  clearSession();
  rememberPostLoginRedirect(returnTo);
  window.location.href = '/login';
};

/** Best-effort telemetry — a 401/429 here must not eject the user from a form. */
function isNonSessionEndpoint(endpoint: string): boolean {
  const path = endpoint.replace(/^\//, '').split(/[?#]/)[0].toLowerCase();
  return (
    path.startsWith('reports/exception-logs') ||
    path.startsWith('audit-events') ||
    path.startsWith('analytics')
  );
}

function shouldRedirectOnAuthFailure(
  endpoint: string,
  status: number | undefined,
  authRedirect: boolean
): boolean {
  if (!authRedirect) return false;
  if (status === 429) return false;
  if (isNonSessionEndpoint(endpoint)) return false;
  return status === 401;
}

const formatApiErrorDetail = (detail: unknown): string => {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item: { msg?: string; loc?: unknown[] }) => {
        if (!item?.msg) return null;
        const field = Array.isArray(item.loc)
          ? item.loc.filter(part => typeof part === 'string' && part !== 'body').join('.')
          : '';
        const msg = item.msg.replace(/^Value error,\s*/i, '');
        return field ? `${field}: ${msg}` : msg;
      })
      .filter((msg): msg is string => Boolean(msg));
    if (messages.length > 0) return messages.join(' ');
  }
  if (detail && typeof detail === 'object') {
    const rec = detail as { message?: unknown; matches?: unknown };
    if (Array.isArray(rec.matches) && rec.matches.length) {
      return JSON.stringify(detail);
    }
    if (typeof rec.message === 'string' && rec.message.trim()) return rec.message.trim();
  }
  return JSON.stringify(detail);
};

export function formatApiUiError(
  error: unknown,
  fallback: string,
  options?: { retrying?: boolean }
): string {
  const raw = error instanceof Error ? error.message.trim() : '';
  const retrySuffix = options?.retrying ? ' Retrying…' : ' Please try again.';

  if (/bad gateway|gateway timeout|service unavailable/i.test(raw)) {
    const gatewayLabel = /bad gateway/i.test(raw) ? ' (Bad Gateway)' : '';
    return `Backend unavailable${gatewayLabel}.${retrySuffix}`;
  }

  if (/failed to fetch|networkerror|network request failed|load failed/i.test(raw)) {
    return `Backend unavailable or network connection lost.${retrySuffix}`;
  }

  return raw || fallback;
}

/**
 * A clean, agnostic universal network abstraction client wrapper.
 * Contains zero hardcoded fallback entities or localized data payloads.
 */
const API_FETCH_TIMEOUT_MS = 60_000;
export const API_SYNC_TIMEOUT_MS = 10 * 60_000;
/** Bulk PEM apply from NZ/CA mapping review (remote DB can be slow). */
export const API_MAPPING_APPLY_TIMEOUT_MS = 5 * 60_000;
/** ScanX bulk-delete: DB commit is fast; allow tunnel/R2 jitter without AbortError. */
export const API_SCANX_BULK_DELETE_TIMEOUT_MS = 3 * 60_000;
/** Legacy 5-minute ScanX budget — do not use for POST ingest (OCR is async). */
export const API_SCANX_TIMEOUT_MS = 5 * 60_000;
/** POST upload / group / reprocess: store bytes + 202. OCR continues in the background. */
export const API_SCANX_UPLOAD_TIMEOUT_MS = 90_000;
/** ScanX document list (non-silent). Silent polls pass a shorter explicit budget. */
export const API_SCANX_LIST_TIMEOUT_MS = 2 * 60_000;
/** Review GET may backfill passport fields from OCR blocks (can exceed 60s). */
export const API_SCANX_REVIEW_TIMEOUT_MS = 5 * 60_000;

function isScanxEndpoint(endpoint?: string): boolean {
  return /^scanx\//i.test((endpoint || '').replace(/^\//, ''));
}

function isScanxDocumentListPath(path: string): boolean {
  return /^scanx\/documents(\?|$)/i.test(path);
}

function isScanxReviewPath(path: string): boolean {
  return /^scanx\/documents\/\d+\/review(\?|$)/i.test(path);
}

function isScanxIngestPost(path: string, verb: string): boolean {
  if (verb !== 'POST') return false;
  return (
    /^scanx\/documents(\/group)?(\?|$)/i.test(path) ||
    /^scanx\/documents\/\d+\/reprocess(\?|$)/i.test(path)
  );
}

function defaultTimeoutForEndpoint(
  endpoint: string,
  override?: number,
  method: string = 'GET'
): number {
  if (override != null) return override;
  const path = endpoint.replace(/^\//, '');
  const verb = (method || 'GET').toUpperCase();
  if (/^scanx\/documents\/bulk-delete/i.test(path)) {
    return API_SCANX_BULK_DELETE_TIMEOUT_MS;
  }
  // Upload / reprocess must not wait for OCR — server returns 202 then processes.
  if (isScanxIngestPost(path, verb)) {
    return API_SCANX_UPLOAD_TIMEOUT_MS;
  }
  // List GET only.
  if ((verb === 'GET' || verb === 'HEAD') && isScanxDocumentListPath(path)) {
    return API_SCANX_LIST_TIMEOUT_MS;
  }
  // Review may run passport field backfill when extracted_fields_json is missing.
  if ((verb === 'GET' || verb === 'HEAD') && isScanxReviewPath(path)) {
    return API_SCANX_REVIEW_TIMEOUT_MS;
  }
  if (isScanxEndpoint(path)) {
    return API_FETCH_TIMEOUT_MS;
  }
  return API_FETCH_TIMEOUT_MS;
}

/** True when the SPA aborted a ScanX request (job may still be running). */
export function isScanxClientTimeoutError(error: unknown): boolean {
  return error instanceof Error && /^ScanX timed out after \d+s/i.test(error.message);
}

function buildClientTimeoutMessage(
  timeoutMs: number = API_FETCH_TIMEOUT_MS,
  endpoint?: string
): string {
  const host = typeof window !== 'undefined' ? window.location.hostname : '';
  const isLocalDev = /^(localhost|127\.0\.0\.1)$/i.test(host);
  const backendPort =
    (typeof import.meta !== 'undefined' && import.meta.env?.VITE_NEXUS_BACKEND_PORT) || '8002';
  const secs = Math.round(timeoutMs / 1000);
  const path = (endpoint || '').replace(/^\//, '');
  const isLeadSearch = /^leads\/prospects(\?|$)/i.test(path);

  // ScanX ingest is 202 + poll. A long abort is not "backend down".
  if (isScanxEndpoint(path)) {
    return (
      `ScanX timed out after ${secs}s while the backend was busy (OCR / uploads / DB tunnel). ` +
      `Document processing usually continues in the background — wait and refresh the list. ` +
      (isLocalDev ? `If nothing updates for several minutes, check port ${backendPort}.` : '')
    ).trim();
  }

  if (isLocalDev) {
    if (isLeadSearch) {
      return (
        `Lead search timed out after ${secs}s. Confirm the NEXUS backend is running on port ${backendPort} ` +
        '(try: powershell -ExecutionPolicy Bypass -File .\\start-dev.ps1). ' +
        'Also confirm the SSH DB tunnel on 127.0.0.1:15432 is up — a hung or missing tunnel makes prospects search stall.'
      );
    }
    let msg =
      `Request timed out after ${secs}s on port ${backendPort} ` +
      '(Vite proxies /api — see vite.config.js).';
    if (timeoutMs >= API_MAPPING_APPLY_TIMEOUT_MS) {
      msg +=
        ' Bulk PEM apply allows up to 5 minutes; if this appears sooner, the proxy/backend is likely down.';
    } else {
      msg +=
        ' If the backend is busy with ScanX OCR, wait and retry — otherwise confirm it is running.';
    }
    return msg;
  }
  if (isLeadSearch) {
    return (
      `Lead search timed out after ${secs}s. The API took too long to respond — ` +
      'check staging/backend health and database connectivity, then retry.'
    );
  }
  let msg =
    'Request timed out on this hosted environment. The API took too long to respond. ' +
    'This is not a local Vite/8002 proxy issue - check staging/backend health, then retry.';
  if (timeoutMs >= API_SYNC_TIMEOUT_MS) {
    msg +=
      ' For Meta lead sync, open Reports -> Meta Leads (the job may still finish in the background).';
  }
  return msg;
}


export type ApiFetchOptions = RequestInit & {
  /** Override default client timeout (60s; ScanX paths use longer budgets automatically). */
  timeoutMs?: number;
  /** Optional label for audit log when this request loads data (control + value). */
  auditContext?: { label: string; value?: string };
  /**
   * When false, expired tokens / HTTP 401 throw without forcing /login.
   * Use for best-effort background polls (presence, unread, notification inbox)
   * so a flaky auth blip does not eject the user mid-interaction.
   */
  authRedirect?: boolean;
  /**
   * When false, skip Exception Report for timeout/http/network failures.
   * Use for best-effort background polls so DB pool pressure during ScanX
   * does not spam ERROR rows for notifications/inbox.
   */
  reportFailures?: boolean;
};

function mergeAbortSignals(...signals: AbortSignal[]): AbortSignal {
  const controller = new AbortController();
  const onAbort = () => controller.abort();

  for (const signal of signals) {
    if (signal.aborted) {
      controller.abort();
      return controller.signal;
    }
    signal.addEventListener('abort', onAbort, { once: true });
  }

  return controller.signal;
}

function sleepMs(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException('Aborted', 'AbortError'));
      return;
    }
    const id = window.setTimeout(resolve, ms);
    const onAbort = () => {
      window.clearTimeout(id);
      reject(new DOMException('Aborted', 'AbortError'));
    };
    signal?.addEventListener('abort', onAbort, { once: true });
  });
}

function isTransientUnavailableStatus(status: number): boolean {
  return status === 502 || status === 503 || status === 504;
}

function retryAfterDelayMs(response: Response, attempt: number): number {
  const raw = response.headers.get('Retry-After');
  if (raw) {
    const secs = Number(raw);
    if (Number.isFinite(secs) && secs >= 0) {
      return Math.min(Math.max(secs, 0.2) * 1000, 8_000);
    }
  }
  return Math.min(400 * attempt, 2_000);
}

export async function apiFetch(endpoint: string, options?: ApiFetchOptions) {
  const {
    timeoutMs: timeoutMsOverride,
    auditContext,
    authRedirect = true,
    reportFailures = true,
    ...requestInit
  } = options ?? {};
  const token = getStoredToken();

  if (token && isTokenExpired(token)) {
    if (authRedirect) redirectToLogin();
    throw new Error('Session expired. Please log in again.');
  }

  const cleanBase = BASE_URL.replace(/\/$/, '');
  const cleanEndpoint = endpoint.replace(/^\//, '');
  const method = (requestInit.method || 'GET').toUpperCase();
  const timeoutMs = defaultTimeoutForEndpoint(cleanEndpoint, timeoutMsOverride, method);
  const isIdempotent = method === 'GET' || method === 'HEAD';
  // GET/HEAD: retry 502/503/504 (SSH-tunnel pool / busy). Do not retry
  // AbortError — a 120s–5min abort retried 3x holds sockets and starves OCR.
  // Never retry POST/PUT/PATCH/DELETE (uploads).
  const maxAttempts = isIdempotent ? 3 : 1;

  const headers: Record<string, string> = {
    ...(requestInit.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
    'ngrok-skip-browser-warning': 'true',
    'X-Nexus-Page': window.location.pathname,
    ...((options?.headers as Record<string, string>) || {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };

  const callerSignal = requestInit.signal;
  let lastError: unknown;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const timeoutController = new AbortController();
    const timeoutId = window.setTimeout(() => timeoutController.abort(), timeoutMs);
    const signal = callerSignal
      ? mergeAbortSignals(callerSignal, timeoutController.signal)
      : timeoutController.signal;

    let response: Response;
    try {
      response = await fetch(`${cleanBase}/${cleanEndpoint}`, {
        ...requestInit,
        method: requestInit.method || 'GET',
        headers,
        signal,
      });
    } catch (error) {
      window.clearTimeout(timeoutId);
      if (error instanceof Error && error.name === 'AbortError') {
        if (callerSignal?.aborted) {
          throw error;
        }
        lastError = error;
        if (reportFailures) {
          reportApiFailure({
            endpoint: cleanEndpoint,
            kind: 'timeout',
            timeoutMs,
          });
        }
        throw new Error(buildClientTimeoutMessage(timeoutMs, cleanEndpoint));
      }
      if (reportFailures) {
        reportApiFailure({
          endpoint: cleanEndpoint,
          kind: 'network',
          detail: error instanceof Error ? error.message : 'Network request failed',
        });
      }
      throw error;
    } finally {
      window.clearTimeout(timeoutId);
    }

    // If the server returns any error status (404, 500, 403, etc.), throw it cleanly
    if (!response.ok) {
      const errorText = await response.text();
      let detail = response.statusText;
      try {
        const body = errorText ? JSON.parse(errorText) : null;
        if (body?.detail) {
          detail = formatApiErrorDetail(body.detail);
        }
      } catch {
        if (errorText) detail = errorText;
      }

      if (
        isIdempotent &&
        isTransientUnavailableStatus(response.status) &&
        attempt < maxAttempts
      ) {
        try {
          await sleepMs(retryAfterDelayMs(response, attempt), callerSignal);
        } catch (sleepErr) {
          if (sleepErr instanceof Error && sleepErr.name === 'AbortError' && callerSignal?.aborted) {
            throw sleepErr;
          }
        }
        continue;
      }

      if (reportFailures && response.status !== 401 && response.status !== 429) {
        reportApiFailure({
          endpoint: cleanEndpoint,
          kind: 'http',
          status: response.status,
          detail: typeof detail === 'string' ? detail.slice(0, 500) : undefined,
        });
      }

      if (shouldRedirectOnAuthFailure(cleanEndpoint, response.status, authRedirect)) {
        redirectToLogin();
      }

      throw new Error(detail);
    }

    // Handle empty or 204 No Content text tracks safely before parsing JSON payload frames
    const text = await response.text();
    const json = text ? JSON.parse(text) : {};

    if ((requestInit.method || 'GET').toUpperCase() === 'GET') {
      void import('./auditTracker').then(({ trackApiRead }) => {
        trackApiRead(cleanEndpoint, requestInit.method || 'GET', response.status, { auditContext });
      });
    }

    // Handle dynamic shape normalization for dictionary-wrapped array responses
    if (json && !Array.isArray(json)) {
      const keys = Object.keys(json);
      if (Array.isArray(json.data) && keys.length === 1) return json.data;
      if (Array.isArray(json.leads) && keys.length === 1) return json.leads;
      if (Array.isArray(json.results) && keys.length === 1) return json.results;
    }

    return json;
  }

  throw lastError instanceof Error
    ? lastError
    : new Error(buildClientTimeoutMessage(timeoutMs, cleanEndpoint));
}

/** Fetch a binary response (e.g. PDF export) with the same auth/session handling as apiFetch. */
export async function apiFetchBlob(endpoint: string, options?: ApiFetchOptions): Promise<Blob> {
  const {
    timeoutMs: timeoutMsOverride,
    auditContext,
    authRedirect = true,
    ...requestInit
  } = options ?? {};
  const token = getStoredToken();

  if (token && isTokenExpired(token)) {
    if (authRedirect) redirectToLogin();
    throw new Error('Session expired. Please log in again.');
  }

  const cleanBase = BASE_URL.replace(/\/$/, '');
  const cleanEndpoint = endpoint.replace(/^\//, '');
  const method = (requestInit.method || 'GET').toUpperCase();
  const timeoutMs = defaultTimeoutForEndpoint(cleanEndpoint, timeoutMsOverride, method);

  const timeoutController = new AbortController();
  const timeoutId = window.setTimeout(() => timeoutController.abort(), timeoutMs);
  const callerSignal = requestInit.signal;
  const signal = callerSignal
    ? mergeAbortSignals(callerSignal, timeoutController.signal)
    : timeoutController.signal;

  const headers: Record<string, string> = {
    'ngrok-skip-browser-warning': 'true',
    'X-Nexus-Page': window.location.pathname,
    ...((options?.headers as Record<string, string>) || {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };

  let response: Response;
  try {
    response = await fetch(`${cleanBase}/${cleanEndpoint}`, {
      ...requestInit,
      method: requestInit.method || 'GET',
      headers,
      signal,
    });
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      if (callerSignal?.aborted) {
        throw error;
      }
      reportApiFailure({
        endpoint: cleanEndpoint,
        kind: 'timeout',
        timeoutMs,
      });
      throw new Error(
        isScanxEndpoint(cleanEndpoint)
          ? buildClientTimeoutMessage(timeoutMs, cleanEndpoint)
          : 'PDF export timed out. Try narrowing the date range or ask an admin to run a background export.'
      );
    }
    reportApiFailure({
      endpoint: cleanEndpoint,
      kind: 'network',
      detail: error instanceof Error ? error.message : 'Network request failed',
    });
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }

  if (!response.ok) {
    const errorText = await response.text();
    let detail = response.statusText;
    try {
      const body = errorText ? JSON.parse(errorText) : null;
      if (body?.detail) {
        detail = formatApiErrorDetail(body.detail);
      }
    } catch {
      if (errorText) detail = errorText;
    }

    if (response.status !== 401 && response.status !== 429) {
      reportApiFailure({
        endpoint: cleanEndpoint,
        kind: 'http',
        status: response.status,
        detail: typeof detail === 'string' ? detail.slice(0, 500) : undefined,
      });
    }

    if (shouldRedirectOnAuthFailure(cleanEndpoint, response.status, authRedirect)) {
      redirectToLogin();
    }

    throw new Error(detail);
  }

  if ((requestInit.method || 'GET').toUpperCase() === 'GET') {
    void import('./auditTracker').then(({ trackApiRead }) => {
      trackApiRead(cleanEndpoint, requestInit.method || 'GET', response.status, { auditContext });
    });
  }

  return response.blob();
}

export async function apiUpload(
  endpoint: string,
  formData: FormData,
  options?: { timeoutMs?: number }
) {
  const token = getStoredToken();

  if (token && isTokenExpired(token)) {
    redirectToLogin();
    throw new Error('Session expired. Please log in again.');
  }

  const cleanBase = BASE_URL.replace(/\/$/, '');
  const cleanEndpoint = endpoint.replace(/^\//, '');
  // ScanX ingest POST: store + 202. Never retry — a timed-out POST may
  // already have created the document on the server.
  const timeoutMs = defaultTimeoutForEndpoint(cleanEndpoint, options?.timeoutMs, 'POST');

  const headers: Record<string, string> = {
    'ngrok-skip-browser-warning': 'true',
    'X-Nexus-Page': window.location.pathname,
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };

  const timeoutController = new AbortController();
  const timeoutId = window.setTimeout(() => timeoutController.abort(), timeoutMs);

  let response: Response;
  try {
    response = await fetch(`${cleanBase}/${cleanEndpoint}`, {
      method: 'POST',
      headers,
      body: formData,
      signal: timeoutController.signal,
    });
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      reportApiFailure({
        endpoint: cleanEndpoint,
        kind: 'timeout',
        timeoutMs,
      });
      throw new Error(buildClientTimeoutMessage(timeoutMs, cleanEndpoint));
    }
    reportApiFailure({
      endpoint: cleanEndpoint,
      kind: 'network',
      detail: error instanceof Error ? error.message : 'Network request failed',
    });
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }

  if (!response.ok) {
    const errorText = await response.text();
    let detail = response.statusText;
    try {
      const body = errorText ? JSON.parse(errorText) : null;
      if (body?.detail) {
        detail = formatApiErrorDetail(body.detail);
      }
    } catch {
      if (errorText) detail = errorText;
    }
    if (shouldRedirectOnAuthFailure(cleanEndpoint, response.status, true)) {
      redirectToLogin();
    }
    throw new Error(detail);
  }

  const text = await response.text();
  return text ? JSON.parse(text) : {};
}

export const resolveWebSocketUrl = (path = '/ws/nexus'): string => {
  const token = getStoredToken();
  const envWs =
    (typeof import.meta !== 'undefined' && import.meta.env?.VITE_WS_URL) ||
    (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_URL);

  let wsBase: string;
  if (envWs && String(envWs).trim()) {
    wsBase = String(envWs).trim().replace(/^http/i, 'ws').replace(/\/api\/v1\/?$/, '');
  } else {
    // Connect directly to the backend in local dev so long-running HTTP work
    // on the Vite proxy cannot stall the WebSocket opening handshake.
    wsBase = `ws://${import.meta.env.VITE_NEXUS_BIND_HOST || '127.0.0.1'}:${import.meta.env.VITE_NEXUS_BACKEND_PORT || '8002'}`;
  }

  const suffix = path.startsWith('/') ? path : `/${path}`;
  const query = token ? `?token=${encodeURIComponent(token)}` : '';
  return `${wsBase.replace(/\/$/, '')}/api/v1${suffix}${query}`;
};