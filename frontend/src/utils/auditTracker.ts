import { getStoredToken, hasValidSession, resolveBaseUrl } from './api';

export type ClientAuditActionType = 'PAGE_VIEW' | 'UI_CLICK' | 'UI_FIELD_CHANGE' | 'API_READ';

export interface ClientAuditEvent {
  action_type: ClientAuditActionType;
  page: string;
  menu?: string;
  action: string;
  target_resource?: string;
  resource_id?: string;
  element_type?: string;
  element_label?: string;
  metadata?: Record<string, unknown>;
}

export interface ApiReadAuditOptions {
  auditContext?: { label: string; value?: string };
}

interface PendingApiTrigger {
  controlLabel: string;
  controlValue: string;
  at: number;
}

const ROUTE_LABELS: Record<string, string> = {
  '/': 'Dashboard',
  '/ai-active': 'Manage Leads > AI Active',
  '/handoffs': 'Manage Leads > Handoffs',
  '/prospects': 'Manage Leads > All Prospects',
  '/offline-leads': 'Manage Leads > Offline Leads',
  '/archive': 'Manage Leads > Archive',
  '/users': 'Users > Manage Users',
  '/access-control': 'Users > Access Control',
  '/agents': 'Cockpit > AI Agent Brain',
  '/analytics': 'Reports > Analytics',
  '/counselling': 'Appointments > Manage Appointments',
  '/command-center': 'Cockpit > Mission Control',
  '/messaging-hub': 'Chat',
  '/my-bookings': 'Appointments > My Appointments',
  '/my-profile': 'My Profile',
  '/settings': 'Cockpit > Application Settings',
  '/reports/meta-leads': 'Reports > Meta Leads',
  '/reports/audit-logs': 'Reports > Audit Logs',
  '/quarantine': 'Manage Leads > Lead Quarantine',
  '/security-audit': 'Cockpit > Security Audit',
};

/** Automatic/session GET calls — not user-initiated actions; tracked via PAGE_VIEW instead. */
const SKIP_API_READ_PREFIXES = [
  'audit-events',
  'permissions/my-role',
  'settings/business-timezone',
  'settings/business-profile',
  'notifications/unread-count',
  'notifications/stream',
  'notifications',
  'dashboard/presence',
  'dashboard/summary',
  'users/me',
  'chat/conversations',
  'admin/audit-logs',
];

const DEDUPE_WINDOWS_MS: Record<ClientAuditActionType, number> = {
  PAGE_VIEW: 2000,
  UI_CLICK: 1500,
  UI_FIELD_CHANGE: 2000,
  API_READ: 5000,
};

const PENDING_TRIGGER_MAX_AGE_MS = 4000;

const FLUSH_INTERVAL_MS = 2000;
const MAX_BATCH_SIZE = 25;
const MAX_QUEUE_SIZE = 200;

let queue: ClientAuditEvent[] = [];
let flushTimer: number | null = null;
let flushing = false;
let lastPageViewPath = '';
let lastPageViewAt = 0;
let pendingApiTrigger: PendingApiTrigger | null = null;
const recentFingerprints = new Map<string, number>();

export const labelForPath = (pathname: string): string => {
  const normalized = pathname.replace(/\/+$/, '') || '/';
  if (ROUTE_LABELS[normalized]) return ROUTE_LABELS[normalized];
  for (const [route, label] of Object.entries(ROUTE_LABELS).sort((a, b) => b[0].length - a[0].length)) {
    if (route !== '/' && (normalized === route || normalized.startsWith(`${route}/`))) {
      return label;
    }
  }
  return normalized;
};

export const currentPagePath = (): string => window.location.pathname;

const shouldTrackSession = (): boolean =>
  hasValidSession() && Boolean(getStoredToken()) && !window.location.pathname.startsWith('/login');

const setPendingApiTrigger = (controlLabel: string, controlValue: string): void => {
  pendingApiTrigger = { controlLabel, controlValue, at: Date.now() };
};

const consumeApiTrigger = (
  explicit?: { label: string; value?: string }
): { controlLabel: string; controlValue: string } | null => {
  if (explicit?.label) {
    return { controlLabel: explicit.label, controlValue: explicit.value || '' };
  }
  if (pendingApiTrigger && Date.now() - pendingApiTrigger.at < PENDING_TRIGGER_MAX_AGE_MS) {
    const trigger = pendingApiTrigger;
    pendingApiTrigger = null;
    return { controlLabel: trigger.controlLabel, controlValue: trigger.controlValue };
  }
  return null;
};

const summarizeQueryString = (query: string): string => {
  const params = new URLSearchParams(query);
  const parts: string[] = [];
  params.forEach((value, key) => {
    const label = key.replace(/_/g, ' ');
    parts.push(`${label}=${value}`);
  });
  const joined = parts.join(', ');
  return joined.length > 100 ? `${joined.slice(0, 97)}…` : joined;
};

const buildApiReadAction = (
  cleanEndpoint: string,
  queryString: string | undefined,
  trigger: { controlLabel: string; controlValue: string } | null
): string => {
  if (trigger?.controlLabel) {
    const valuePart = trigger.controlValue ? ` to ${trigger.controlValue}` : '';
    return `Loaded ${cleanEndpoint} — changed ${trigger.controlLabel}${valuePart}`;
  }
  if (queryString) {
    return `Loaded ${cleanEndpoint} (${summarizeQueryString(queryString)})`;
  }
  return `Loaded ${cleanEndpoint}`;
};

const eventFingerprint = (event: ClientAuditEvent): string => {
  const metadata = event.metadata || {};
  const endpoint = typeof metadata.api_endpoint === 'string' ? metadata.api_endpoint : '';
  const query = typeof metadata.query_string === 'string' ? metadata.query_string : '';
  const trigger = `${metadata.trigger_control || ''}:${metadata.trigger_value || ''}`;
  const fieldValue = typeof metadata.field_value === 'string' ? metadata.field_value : '';
  return [
    event.action_type,
    event.page,
    event.action,
    event.element_label || '',
    event.element_type || '',
    endpoint,
    query,
    trigger,
    fieldValue,
  ].join('|');
};

const isDuplicateEvent = (event: ClientAuditEvent): boolean => {
  const fingerprint = eventFingerprint(event);
  const now = Date.now();
  const windowMs = DEDUPE_WINDOWS_MS[event.action_type];
  const lastSeen = recentFingerprints.get(fingerprint);
  if (lastSeen !== undefined && now - lastSeen < windowMs) {
    return true;
  }
  recentFingerprints.set(fingerprint, now);
  if (recentFingerprints.size > 500) {
    for (const [key, ts] of recentFingerprints) {
      if (now - ts > 60000) recentFingerprints.delete(key);
    }
  }
  return false;
};

const enqueue = (event: ClientAuditEvent): void => {
  if (!shouldTrackSession()) return;
  if (isDuplicateEvent(event)) return;
  if (queue.length >= MAX_QUEUE_SIZE) {
    queue.shift();
  }
  queue.push(event);
  scheduleFlush();
};

const scheduleFlush = (): void => {
  if (flushTimer !== null) return;
  flushTimer = window.setTimeout(() => {
    flushTimer = null;
    void flushAuditEvents();
  }, FLUSH_INTERVAL_MS);
};

const sendBatch = async (events: ClientAuditEvent[]): Promise<void> => {
  const token = getStoredToken();
  if (!token) return;

  const base = resolveBaseUrl().replace(/\/$/, '');
  await fetch(`${base}/audit-events`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      'ngrok-skip-browser-warning': 'true',
      'X-Nexus-Page': window.location.pathname,
    },
    body: JSON.stringify({ events }),
    keepalive: true,
  });
};

export const flushAuditEvents = async (): Promise<void> => {
  if (!shouldTrackSession() || flushing || queue.length === 0) return;
  flushing = true;
  const batch = queue.splice(0, MAX_BATCH_SIZE);
  try {
    await sendBatch(batch);
  } catch {
    queue.unshift(...batch);
  } finally {
    flushing = false;
    if (queue.length > 0) {
      scheduleFlush();
    }
  }
};

export const trackPageView = (pathname: string = currentPagePath()): void => {
  if (!shouldTrackSession() || pathname.startsWith('/login')) return;
  const now = Date.now();
  if (pathname === lastPageViewPath && now - lastPageViewAt < DEDUPE_WINDOWS_MS.PAGE_VIEW) return;
  lastPageViewPath = pathname;
  lastPageViewAt = now;

  const label = labelForPath(pathname);
  enqueue({
    action_type: 'PAGE_VIEW',
    page: pathname,
    menu: label,
    action: `Viewed ${label}`,
    target_resource: 'navigation',
  });
};

export const trackUiClick = (target: HTMLElement): void => {
  if (!shouldTrackSession()) return;
  const label = getInteractiveLabel(target);
  const page = currentPagePath();
  enqueue({
    action_type: 'UI_CLICK',
    page,
    menu: labelForPath(page),
    action: `Clicked ${label}`,
    target_resource: 'ui_interaction',
    element_type: target.tagName.toLowerCase(),
    element_label: label,
    metadata: {
      id: target.id || undefined,
      role: target.getAttribute('role') || undefined,
      href: target instanceof HTMLAnchorElement ? target.getAttribute('href') || undefined : undefined,
    },
  });

  if (isActionControl(target)) {
    setPendingApiTrigger(label, 'clicked');
  }
};

export const trackFieldChange = (target: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement): void => {
  if (!shouldTrackSession()) return;
  if (target instanceof HTMLInputElement) {
    const type = (target.type || 'text').toLowerCase();
    if (type === 'password' || type === 'hidden' || type === 'file') return;
  }
  const label = getFieldLabel(target);
  const value = getFieldValue(target);
  const page = currentPagePath();
  setPendingApiTrigger(label, value);

  enqueue({
    action_type: 'UI_FIELD_CHANGE',
    page,
    menu: labelForPath(page),
    action: value ? `Changed ${label} to ${value}` : `Changed ${label}`,
    target_resource: 'ui_interaction',
    element_type: target.tagName.toLowerCase(),
    element_label: label,
    metadata: {
      field_name: target.name || undefined,
      field_id: target.id || undefined,
      field_value: value || undefined,
      input_type: target instanceof HTMLInputElement ? target.type : undefined,
    },
  });
};

export const trackApiRead = (
  endpoint: string,
  method: string,
  status: number,
  options?: ApiReadAuditOptions
): void => {
  if (!shouldTrackSession()) return;
  if (method.toUpperCase() !== 'GET') return;

  const normalizedEndpoint = endpoint.replace(/^\//, '');
  const [cleanEndpoint, queryString] = normalizedEndpoint.split('?');
  if (SKIP_API_READ_PREFIXES.some(prefix => cleanEndpoint === prefix || cleanEndpoint.startsWith(`${prefix}/`))) {
    return;
  }
  if (status >= 400) return;

  const trigger = consumeApiTrigger(options?.auditContext);
  const action = buildApiReadAction(cleanEndpoint, queryString, trigger);
  const page = currentPagePath();

  enqueue({
    action_type: 'API_READ',
    page,
    menu: labelForPath(page),
    action,
    target_resource: 'api_read',
    metadata: {
      api_endpoint: `/api/v1/${cleanEndpoint}`,
      query_string: queryString || undefined,
      trigger_control: trigger?.controlLabel || undefined,
      trigger_value: trigger?.controlValue || undefined,
      http_method: 'GET',
      status_code: status,
    },
  });
};

const extractLabelText = (labelEl: Element): string => {
  const clone = labelEl.cloneNode(true) as HTMLElement;
  clone.querySelectorAll('select, input, textarea, button').forEach(node => node.remove());
  return (clone.textContent || '').replace(/\s+/g, ' ').trim();
};

const getInteractiveLabel = (el: HTMLElement): string => {
  const aria = el.getAttribute('aria-label')?.trim();
  if (aria) return truncate(aria);
  const title = el.getAttribute('title')?.trim();
  if (title) return truncate(title);
  if (el instanceof HTMLInputElement && (el.type === 'submit' || el.type === 'button')) {
    const value = el.value.trim();
    if (value) return truncate(value);
  }
  const text = (el.textContent || '').replace(/\s+/g, ' ').trim();
  if (text) return truncate(text);
  if (el.id) return `#${el.id}`;
  return el.tagName.toLowerCase();
};

const getFieldLabel = (el: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement): string => {
  if (el.id) {
    const linked = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
    if (linked?.textContent) return truncate(extractLabelText(linked));
  }
  const parentLabel = el.closest('label');
  if (parentLabel) return truncate(extractLabelText(parentLabel));

  const fieldset = el.closest('fieldset');
  const legend = fieldset?.querySelector('legend');
  const aria = el.getAttribute('aria-label')?.trim();
  if (legend?.textContent && aria) {
    return truncate(`${legend.textContent.replace(/\s+/g, ' ').trim()}: ${aria}`);
  }
  if (legend?.textContent) return truncate(legend.textContent.replace(/\s+/g, ' ').trim());

  if (aria) return truncate(aria);
  const placeholder = el.getAttribute('placeholder')?.trim();
  if (placeholder) return truncate(placeholder);
  if (el.name) return truncate(el.name.replace(/_/g, ' '));
  if (el.id) return `#${el.id}`;
  return el.tagName.toLowerCase();
};

const getFieldValue = (el: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement): string => {
  if (el instanceof HTMLSelectElement) {
    const option = el.options[el.selectedIndex];
    return (option?.text || el.value || '').trim();
  }
  if (el instanceof HTMLInputElement) {
    const type = (el.type || 'text').toLowerCase();
    if (type === 'checkbox') return el.checked ? 'checked' : 'unchecked';
    if (type === 'radio') {
      const option = el.labels?.[0]?.textContent?.trim();
      return option || el.value || '';
    }
    return el.value.trim();
  }
  return el.value.trim();
};

const isActionControl = (el: HTMLElement): boolean => {
  if (el.tagName === 'BUTTON') return true;
  if (el.getAttribute('role') === 'button') return true;
  if (el instanceof HTMLInputElement) {
    const type = (el.type || '').toLowerCase();
    return type === 'button' || type === 'submit';
  }
  return false;
};

const truncate = (value: string, max = 120): string =>
  value.length <= max ? value : `${value.slice(0, max - 1)}…`;

export const getClickTarget = (target: EventTarget | null): HTMLElement | null => {
  if (!(target instanceof HTMLElement)) return null;
  const interactive = target.closest(
    'button, a[href], input[type="button"], input[type="submit"], input[type="checkbox"], input[type="radio"], select, [role="button"], [role="menuitem"], [role="tab"], label[for]'
  );
  return interactive instanceof HTMLElement ? interactive : null;
};

export const isChoiceField = (
  target: EventTarget | null
): target is HTMLInputElement | HTMLSelectElement => {
  if (target instanceof HTMLSelectElement) return true;
  if (target instanceof HTMLInputElement) {
    const type = (target.type || '').toLowerCase();
    return type === 'checkbox' || type === 'radio' || type === 'select-one' || type === 'select-multiple';
  }
  return false;
};

export const isTextLikeField = (
  target: EventTarget | null
): target is HTMLInputElement | HTMLTextAreaElement => {
  if (target instanceof HTMLTextAreaElement) return true;
  if (target instanceof HTMLInputElement) {
    const type = (target.type || 'text').toLowerCase();
    return !['checkbox', 'radio', 'hidden', 'file', 'password', 'button', 'submit', 'reset'].includes(type);
  }
  return false;
};

if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', () => {
    if (!shouldTrackSession() || queue.length === 0) return;
    const token = getStoredToken();
    if (!token) return;
    const base = resolveBaseUrl().replace(/\/$/, '');
    const batch = queue.splice(0, MAX_BATCH_SIZE);
    void fetch(`${base}/audit-events`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
        'ngrok-skip-browser-warning': 'true',
        'X-Nexus-Page': window.location.pathname,
      },
      body: JSON.stringify({ events: batch }),
      keepalive: true,
    });
  });
}
