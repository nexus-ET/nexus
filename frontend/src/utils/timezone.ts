let cachedBusinessTimezone: string | null = null;

export const fetchBusinessTimezone = async (): Promise<string> => {
  if (cachedBusinessTimezone) return cachedBusinessTimezone;
  try {
    const { apiFetch } = await import('./api');
    const data = (await apiFetch('settings/business-timezone')) as { timezone?: string };
    cachedBusinessTimezone = data.timezone || 'UTC';
    return cachedBusinessTimezone;
  } catch {
    return 'UTC';
  }
};

export const clearBusinessTimezoneCache = () => {
  cachedBusinessTimezone = null;
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

export const formatInBusinessTimezone = (
  value: string | Date,
  timezone: string,
  options?: Intl.DateTimeFormatOptions
): string => {
  const date = value instanceof Date ? value : parseApiDateTime(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString(undefined, {
    timeZone: timezone,
    day: 'numeric',
    month: 'short',
    hour: 'numeric',
    minute: '2-digit',
    ...options,
  });
};
