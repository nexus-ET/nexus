let cachedBusinessTimezone: string | null = null;

export const fetchBusinessTimezone = async (): Promise<string> => {
  if (cachedBusinessTimezone) return cachedBusinessTimezone;
  try {
    const { apiFetch } = await import('./api');
    const data = (await apiFetch('settings/business-timezone', {
      authRedirect: false,
    })) as { timezone?: string };
    cachedBusinessTimezone = data.timezone || 'UTC';
    return cachedBusinessTimezone;
  } catch {
    return 'UTC';
  }
};

export const clearBusinessTimezoneCache = () => {
  cachedBusinessTimezone = null;
};

/** Last fetched Nexus business timezone (falls back to UTC until loaded). */
export const getCachedBusinessTimezone = (): string => cachedBusinessTimezone || 'UTC';

/** Calendar YYYY-MM-DD for "today" in the given IANA timezone. */
export const businessTodayIsoDate = (timezone = 'UTC'): string => {
  try {
    const parts = getBusinessCalendarParts(new Date(), timezone || 'UTC');
    if (parts) {
      return `${parts.year}-${String(parts.month).padStart(2, '0')}-${String(parts.day).padStart(2, '0')}`;
    }
  } catch {
    // Invalid IANA zone — fall through
  }
  // Last resort: UTC calendar day (not browser-local) so Nexus stays consistent.
  const parts = getBusinessCalendarParts(new Date(), 'UTC');
  if (parts) {
    return `${parts.year}-${String(parts.month).padStart(2, '0')}-${String(parts.day).padStart(2, '0')}`;
  }
  return new Date().toISOString().slice(0, 10);
};

/** API datetimes are stored in UTC; naive ISO strings must not be parsed as browser-local time. */
export const parseApiDateTime = (value: string | Date): Date => {
  if (value instanceof Date) return value;
  const trimmed = value.trim();
  if (!trimmed) return new Date(Number.NaN);
  if (/[zZ]$|[+-]\d{2}:?\d{2}$/.test(trimmed)) {
    return new Date(trimmed);
  }
  if (/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/.test(trimmed)) {
    const normalized = trimmed.replace(' ', 'T');
    return new Date(normalized.endsWith('Z') ? normalized : `${normalized}Z`);
  }
  return new Date(trimmed);
};

const padAuditFraction = (raw: string | undefined): string => {
  if (!raw) return '000000';
  return raw.padEnd(6, '0').slice(0, 6);
};

const AUDIT_REPORT_TIME_OPTIONS: Intl.DateTimeFormatOptions = {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
};

const AUDIT_ISO_PREFIX =
  /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?/;

/**
 * Format audit log timestamps with millisecond and microsecond precision.
 * Stored values are business-local wall-clock; legacy UTC rows (Z suffix) are converted.
 */
export const formatAuditReportTimestamp = (
  value: string | Date,
  timezone: string,
  options?: Intl.DateTimeFormatOptions
): string => {
  const formatOptions = { ...AUDIT_REPORT_TIME_OPTIONS, ...options };

  if (value instanceof Date) {
    if (Number.isNaN(value.getTime())) return String(value);
    const base = value.toLocaleString(undefined, { timeZone: timezone, ...formatOptions });
    const ms = value.getMilliseconds();
    return `${base}.${String(ms).padStart(3, '0')}000`;
  }

  const trimmed = value.trim();
  if (!trimmed) return '—';

  if (/[zZ]$|[+-]\d{2}:?\d{2}$/.test(trimmed)) {
    const fractionMatch = trimmed.match(AUDIT_ISO_PREFIX);
    const fraction = padAuditFraction(fractionMatch?.[7]);
    const base = formatInBusinessTimezone(trimmed, timezone, formatOptions);
    return `${base}.${fraction}`;
  }

  const match = trimmed.match(AUDIT_ISO_PREFIX);
  if (!match) return trimmed;

  const [, y, mo, d, h, mi, s] = match;
  const fraction = padAuditFraction(match[7]);
  const literal = new Date(Date.UTC(+y, +mo - 1, +d, +h, +mi, +s));
  if (Number.isNaN(literal.getTime())) return trimmed;

  const base = literal.toLocaleString(undefined, {
    timeZone: 'UTC',
    ...formatOptions,
  });
  return `${base}.${fraction}`;
};

/**
 * Format audit timestamps stored as business-local wall-clock (naive ISO from API).
 * Legacy UTC rows (with Z suffix) are converted via the business timezone.
 */
export const formatBusinessLocalTimestamp = (
  value: string | Date,
  timezone: string,
  options?: Intl.DateTimeFormatOptions
): string => {
  if (value instanceof Date) {
    if (Number.isNaN(value.getTime())) return String(value);
    return value.toLocaleString(undefined, { timeZone: timezone, ...options });
  }
  const trimmed = value.trim();
  if (!trimmed) return '—';
  if (/[zZ]$|[+-]\d{2}:?\d{2}$/.test(trimmed)) {
    return formatInBusinessTimezone(trimmed, timezone, options);
  }
  const match = trimmed.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?/);
  if (!match) return trimmed;
  const [, y, mo, d, h, mi, s = '00'] = match;
  const literal = new Date(Date.UTC(+y, +mo - 1, +d, +h, +mi, +s));
  if (Number.isNaN(literal.getTime())) return trimmed;
  return literal.toLocaleString(undefined, {
    timeZone: 'UTC',
    ...options,
  });
};

/** Explicit locale so `timeZone` is honored (browser `undefined` locale can keep machine time). */
const BUSINESS_DISPLAY_LOCALE = 'en-GB';

export const formatInBusinessTimezone = (
  value: string | Date,
  timezone: string,
  options?: Intl.DateTimeFormatOptions
): string => {
  const date = value instanceof Date ? value : parseApiDateTime(value);
  if (Number.isNaN(date.getTime())) return String(value);
  const zone = (timezone || '').trim() || 'UTC';
  const formatOptions: Intl.DateTimeFormatOptions = {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    ...options,
    timeZone: zone,
  };
  try {
    return new Intl.DateTimeFormat(BUSINESS_DISPLAY_LOCALE, formatOptions).format(date);
  } catch {
    return new Intl.DateTimeFormat(BUSINESS_DISPLAY_LOCALE, {
      ...formatOptions,
      timeZone: 'UTC',
    }).format(date);
  }
};

const readParts = (
  date: Date,
  timezone: string,
  options: Intl.DateTimeFormatOptions
): Record<string, string> => {
  const parts = new Intl.DateTimeFormat('en-US', { timeZone: timezone, ...options }).formatToParts(date);
  return Object.fromEntries(parts.filter(p => p.type !== 'literal').map(p => [p.type, p.value]));
};

/** Calendar Y-M-D (and optional time) for a UTC/API instant in the business timezone. */
export const getBusinessCalendarParts = (
  value: string | Date,
  timezone: string
): { year: number; month: number; day: number; hour: number; minute: number } | null => {
  const date = value instanceof Date ? value : parseApiDateTime(value);
  if (Number.isNaN(date.getTime())) return null;
  let parts: Record<string, string>;
  try {
    parts = readParts(date, timezone, {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });
  } catch {
    return null;
  }
  const year = Number(parts.year);
  const month = Number(parts.month);
  const day = Number(parts.day);
  let hour = Number(parts.hour);
  if (hour === 24) hour = 0; // some engines emit 24:00
  const minute = Number(parts.minute);
  if (![year, month, day, hour, minute].every(n => Number.isFinite(n))) return null;
  return { year, month, day, hour, minute };
};

export const formatApiClockTime = (
  value: string | Date | null | undefined,
  timezone: string,
  options?: Intl.DateTimeFormatOptions
): string => {
  if (value === null || value === undefined || value === '') return '';
  const date = value instanceof Date ? value : parseApiDateTime(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleTimeString(undefined, {
    timeZone: timezone,
    hour: '2-digit',
    minute: '2-digit',
    ...options,
  });
};

export const formatApiDateOnly = (
  value: string | Date | null | undefined,
  timezone: string,
  options?: Intl.DateTimeFormatOptions
): string => {
  if (value === null || value === undefined || value === '') return '—';
  const date = value instanceof Date ? value : parseApiDateTime(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleDateString(undefined, {
    timeZone: timezone,
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    ...options,
  });
};

/**
 * Today / Yesterday / weekday / date label for an API (UTC) timestamp,
 * computed against "now" in the business timezone.
 */
export const getApiDateGroupLabel = (
  value: string | Date | null | undefined,
  timezone: string,
  emptyLabel = 'Earlier'
): string => {
  if (value === null || value === undefined || value === '') return emptyLabel;
  const target = getBusinessCalendarParts(value, timezone);
  const now = getBusinessCalendarParts(new Date(), timezone);
  if (!target || !now) return emptyLabel;

  const toUtcDay = (p: { year: number; month: number; day: number }) =>
    Date.UTC(p.year, p.month - 1, p.day) / (1000 * 60 * 60 * 24);
  const diffDays = Math.round(toUtcDay(now) - toUtcDay(target));

  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays > 1 && diffDays < 7) {
    return formatApiDateOnly(value, timezone, { weekday: 'long', month: undefined, day: undefined, year: undefined });
  }
  return formatApiDateOnly(value, timezone);
};

/** Minute bucket for chat clustering, in business timezone. */
export const getApiMinuteKey = (value: string | Date, timezone: string): string => {
  const parts = getBusinessCalendarParts(value, timezone);
  if (!parts) return String(value);
  return `${parts.year}-${parts.month}-${parts.day}-${parts.hour}:${parts.minute}`;
};
