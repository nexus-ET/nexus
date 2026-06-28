import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { fetchBusinessTimezone, formatAuditReportTimestamp, formatInBusinessTimezone } from '../utils/timezone';
import { hasValidSession } from '../utils/api';

const DEFAULT_OPTIONS: Intl.DateTimeFormatOptions = {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
  second: '2-digit',
};

interface BusinessTimezoneContextValue {
  timezone: string;
  loading: boolean;
  formatDateTime: (
    value: string | Date | null | undefined,
    options?: Intl.DateTimeFormatOptions
  ) => string;
  /** Audit log rows are stored in business-local wall-clock time. */
  formatAuditDateTime: (
    value: string | Date | null | undefined,
    options?: Intl.DateTimeFormatOptions
  ) => string;
  refreshTimezone: () => Promise<void>;
}

const BusinessTimezoneContext = createContext<BusinessTimezoneContextValue>({
  timezone: 'UTC',
  loading: true,
  formatDateTime: value => (value ? String(value) : '—'),
  formatAuditDateTime: value => (value ? String(value) : '—'),
  refreshTimezone: async () => {},
});

export const BusinessTimezoneProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [timezone, setTimezone] = useState('UTC');
  const [loading, setLoading] = useState(true);

  const refreshTimezone = useCallback(async () => {
    if (!hasValidSession()) {
      setTimezone('UTC');
      setLoading(false);
      return;
    }
    setLoading(true);
    const tz = await fetchBusinessTimezone();
    setTimezone(tz);
    setLoading(false);
  }, []);

  useEffect(() => {
    void refreshTimezone();
  }, [refreshTimezone]);

  const formatDateTime = useCallback(
    (value: string | Date | null | undefined, options?: Intl.DateTimeFormatOptions) => {
      if (value === null || value === undefined || value === '') return '—';
      return formatInBusinessTimezone(value, timezone, { ...DEFAULT_OPTIONS, ...options });
    },
    [timezone]
  );

  const formatAuditDateTime = useCallback(
    (value: string | Date | null | undefined, options?: Intl.DateTimeFormatOptions) => {
      if (value === null || value === undefined || value === '') return '—';
      return formatAuditReportTimestamp(value, timezone, options);
    },
    [timezone]
  );

  const value = useMemo(
    () => ({ timezone, loading, formatDateTime, formatAuditDateTime, refreshTimezone }),
    [timezone, loading, formatDateTime, formatAuditDateTime, refreshTimezone]
  );

  return (
    <BusinessTimezoneContext.Provider value={value}>{children}</BusinessTimezoneContext.Provider>
  );
};

export const useBusinessTimezone = (): BusinessTimezoneContextValue =>
  useContext(BusinessTimezoneContext);
