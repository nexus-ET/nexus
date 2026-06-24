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

export const formatInBusinessTimezone = (
  value: string | Date,
  timezone: string,
  options?: Intl.DateTimeFormatOptions
): string => {
  const date = value instanceof Date ? value : new Date(value);
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
