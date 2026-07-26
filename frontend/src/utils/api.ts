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
  try {
    const payload = JSON.parse(atob(token.split('.')[1] ?? ''));
    const sub = payload?.sub;
    return sub != null ? Number(sub) : null;
  } catch {
    return null;
  }
};

export const clearSession = (): void => {
  sessionStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(TOKEN_KEY);
};

export const isValidTokenFormat = (token: string | null | undefined): boolean => {
  if (!token) return false;
  return token.split('.').length === 3;
};

export const isTokenExpired = (token: string | null | undefined): boolean => {
  if (!isValidTokenFormat(token)) return true;
  try {
    const payload = JSON.parse(atob(token!.split('.')[1] ?? ''));
    if (!payload?.exp) return false;
    return Date.now() >= Number(payload.exp) * 1000;
  } catch {
    return true;
  }
};

export const hasValidSession = (): boolean => {
  const token = getStoredToken();
  return isValidTokenFormat(token) && !isTokenExpired(token);
};

const redirectToLogin = (): void => {
  if (window.location.pathname.startsWith('/login')) return;
  clearSession();
  window.location.href = '/login';
};

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
  return JSON.stringify(detail);
};

/**
 * A clean, agnostic universal network abstraction client wrapper.
 * Contains zero hardcoded fallback entities or localized data payloads.
 */
const API_FETCH_TIMEOUT_MS = 60_000;
export const API_SYNC_TIMEOUT_MS = 10 * 60_000;

function buildClientTimeoutMessage(): string {
  const host = typeof window !== 'undefined' ? window.location.hostname : '';
  const isLocalDev = /^(localhost|127\.0\.0\.1)$/i.test(host);
  if (isLocalDev) {
    return 'Request timed out. Confirm the NEXUS backend is running (dev proxy: port 8002 in vite.config.js).';
  }
  return (
    'Request timed out. The server took too long to respond. ' +
    'If this was Meta lead sync, open Reports → Meta Leads — the sync may still have completed in the background.'
  );
}

export type ApiFetchOptions = RequestInit & {
  /** Override the default 60s client timeout (e.g. long-running Meta sync). */
  timeoutMs?: number;
  /** Optional label for audit log when this request loads data (control + value). */
  auditContext?: { label: string; value?: string };
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

export async function apiFetch(endpoint: string, options?: ApiFetchOptions) {
  const { timeoutMs = API_FETCH_TIMEOUT_MS, auditContext, ...requestInit } = options ?? {};
  const token = getStoredToken();

  if (token && isTokenExpired(token)) {
    redirectToLogin();
    throw new Error('Session expired. Please log in again.');
  }

  const timeoutController = new AbortController();
  const timeoutId = window.setTimeout(() => timeoutController.abort(), timeoutMs);
  const callerSignal = requestInit.signal;
  const signal = callerSignal
    ? mergeAbortSignals(callerSignal, timeoutController.signal)
    : timeoutController.signal;

  // Combine native objects cleanly while ensuring absolute cross-origin headers
  const headers: Record<string, string> = {
    ...(requestInit.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
    'ngrok-skip-browser-warning': 'true',
    'X-Nexus-Page': window.location.pathname,
    ...((options?.headers as Record<string, string>) || {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };

  const cleanBase = BASE_URL.replace(/\/$/, '');
  const cleanEndpoint = endpoint.replace(/^\//, '');

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
      throw new Error(buildClientTimeoutMessage());
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

    reportApiFailure({
      endpoint: cleanEndpoint,
      kind: 'http',
      status: response.status,
      detail: typeof detail === 'string' ? detail.slice(0, 500) : undefined,
    });

    if (response.status === 401) {
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

/** Fetch a binary response (e.g. PDF export) with the same auth/session handling as apiFetch. */
export async function apiFetchBlob(endpoint: string, options?: ApiFetchOptions): Promise<Blob> {
  const { timeoutMs = API_FETCH_TIMEOUT_MS, auditContext, ...requestInit } = options ?? {};
  const token = getStoredToken();

  if (token && isTokenExpired(token)) {
    redirectToLogin();
    throw new Error('Session expired. Please log in again.');
  }

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

  const cleanBase = BASE_URL.replace(/\/$/, '');
  const cleanEndpoint = endpoint.replace(/^\//, '');

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
        'PDF export timed out. Try narrowing the date range or ask an admin to run a background export.'
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

    reportApiFailure({
      endpoint: cleanEndpoint,
      kind: 'http',
      status: response.status,
      detail: typeof detail === 'string' ? detail.slice(0, 500) : undefined,
    });

    if (response.status === 401) {
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

export async function apiUpload(endpoint: string, formData: FormData) {
  const token = getStoredToken();

  if (token && isTokenExpired(token)) {
    redirectToLogin();
    throw new Error('Session expired. Please log in again.');
  }

  const headers: Record<string, string> = {
    'ngrok-skip-browser-warning': 'true',
    'X-Nexus-Page': window.location.pathname,
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };

  const cleanBase = BASE_URL.replace(/\/$/, '');
  const cleanEndpoint = endpoint.replace(/^\//, '');

  const response = await fetch(`${cleanBase}/${cleanEndpoint}`, {
    method: 'POST',
    headers,
    body: formData,
  });

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
    if (response.status === 401) redirectToLogin();
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