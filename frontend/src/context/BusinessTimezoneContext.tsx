import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import {
  fetchBusinessTimezone,
  formatApiClockTime,
  formatApiDateOnly,
  formatAuditReportTimestamp,
  formatBusinessLocalTimestamp,
  formatInBusinessTimezone,
  getApiDateGroupLabel,
} from '../utils/timezone';
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
  /** API / event timestamps stored as UTC (naive ISO treated as UTC). */
  formatDateTime: (
    value: string | Date | null | undefined,
    options?: Intl.DateTimeFormatOptions
  ) => string;
  /** Clock time only (WhatsApp / chat bubbles). */
  formatTime: (
    value: string | Date | null | undefined,
    options?: Intl.DateTimeFormatOptions
  ) => string;
  /** Calendar date only for UTC/API instants. */
  formatDate: (
    value: string | Date | null | undefined,
    options?: Intl.DateTimeFormatOptions
  ) => string;
  /** Today / Yesterday / weekday grouping for chat sections. */
  formatDateGroup: (value: string | Date | null | undefined, emptyLabel?: string) => string;
  /**
   * Booking slots / office wall-clock values stored as business-local naive ISO
   * (not UTC). Prefer this for scheduled_time / consultation_scheduled_at.
   */
  formatBusinessLocal: (
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
  formatTime: value => (value ? String(value) : ''),
  formatDate: value => (value ? String(value) : '—'),
  formatDateGroup: () => 'Earlier',
  formatBusinessLocal: value => (value ? String(value) : '—'),
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

  const formatTime = useCallback(
    (value: string | Date | null | undefined, options?: Intl.DateTimeFormatOptions) => {
      if (value === null || value === undefined || value === '') return '';
      return formatApiClockTime(value, timezone, options);
    },
    [timezone]
  );

  const formatDate = useCallback(
    (value: string | Date | null | undefined, options?: Intl.DateTimeFormatOptions) => {
      if (value === null || value === undefined || value === '') return '—';
      return formatApiDateOnly(value, timezone, options);
    },
    [timezone]
  );

  const formatDateGroup = useCallback(
    (value: string | Date | null | undefined, emptyLabel = 'Earlier') =>
      getApiDateGroupLabel(value, timezone, emptyLabel),
    [timezone]
  );

  const formatBusinessLocal = useCallback(
    (value: string | Date | null | undefined, options?: Intl.DateTimeFormatOptions) => {
      if (value === null || value === undefined || value === '') return '—';
      const merged: Intl.DateTimeFormatOptions = { ...DEFAULT_OPTIONS, second: undefined, ...options };
      for (const key of Object.keys(merged) as (keyof Intl.DateTimeFormatOptions)[]) {
        if (merged[key] === undefined) {
          delete merged[key];
        }
      }
      return formatBusinessLocalTimestamp(value, timezone, merged);
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
    () => ({
      timezone,
      loading,
      formatDateTime,
      formatTime,
      formatDate,
      formatDateGroup,
      formatBusinessLocal,
      formatAuditDateTime,
      refreshTimezone,
    }),
    [
      timezone,
      loading,
      formatDateTime,
      formatTime,
      formatDate,
      formatDateGroup,
      formatBusinessLocal,
      formatAuditDateTime,
      refreshTimezone,
    ]
  );

  return (
    <BusinessTimezoneContext.Provider value={value}>{children}</BusinessTimezoneContext.Provider>
  );
};

export const useBusinessTimezone = (): BusinessTimezoneContextValue =>
  useContext(BusinessTimezoneContext);
