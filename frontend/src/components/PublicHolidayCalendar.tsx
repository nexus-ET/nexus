import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { CalendarDays, ChevronLeft, ChevronRight, Loader2, X } from 'lucide-react';
import { apiFetch } from '../utils/api';

interface PublicHolidayEntry {
  date: string;
  name?: string | null;
  label: string;
  is_private: boolean;
}

interface PublicHolidaysResponse {
  holidays: PublicHolidayEntry[];
  updated_at?: string | null;
  updated_by_first_name?: string | null;
  updated_by_last_name?: string | null;
}

interface MonthRef {
  year: number;
  month: number;
}

type BulkAction = 'public' | 'private' | null;

const PRIVATE_HOLIDAY_LABEL = 'Private holiday';

const MONTH_NAMES = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
];

const WEEKDAY_LABELS = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];

const toIsoDate = (year: number, month: number, day: number): string => {
  const monthPart = String(month + 1).padStart(2, '0');
  const dayPart = String(day).padStart(2, '0');
  return `${year}-${monthPart}-${dayPart}`;
};

const addMonths = (year: number, month: number, delta: number): MonthRef => {
  const next = new Date(year, month + delta, 1);
  return { year: next.getFullYear(), month: next.getMonth() };
};

const buildCalendarCells = (year: number, month: number): Array<number | null> => {
  const firstWeekday = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells: Array<number | null> = [];
  for (let index = 0; index < firstWeekday; index += 1) {
    cells.push(null);
  }
  for (let day = 1; day <= daysInMonth; day += 1) {
    cells.push(day);
  }
  return cells;
};

const formatModifiedBy = (response: PublicHolidaysResponse | null): string => {
  if (!response) return '—';
  const first = response.updated_by_first_name?.trim() ?? '';
  const last = response.updated_by_last_name?.trim() ?? '';
  const fullName = [first, last].filter(Boolean).join(' ');
  return fullName || '—';
};

const formatHolidayDate = (isoDate: string): string =>
  new Date(`${isoDate}T00:00:00`).toLocaleDateString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });

interface MonthCalendarProps {
  monthRef: MonthRef;
  holidayMap: Record<string, PublicHolidayEntry>;
  selectedDates: Set<string>;
  multiSelectMode: boolean;
  isCenter?: boolean;
  today: Date;
  onDayClick: (year: number, month: number, day: number) => void;
}

const MonthCalendar: React.FC<MonthCalendarProps> = ({
  monthRef,
  holidayMap,
  selectedDates,
  multiSelectMode,
  isCenter = false,
  today,
  onDayClick,
}) => {
  const cells = useMemo(
    () => buildCalendarCells(monthRef.year, monthRef.month),
    [monthRef.month, monthRef.year]
  );

  return (
    <div
      className={`rounded-lg border p-2 ${
        isCenter ? 'border-accent/40 bg-accent/5' : 'border-border-subtle bg-surface-bg'
      }`}
    >
      <div className="mb-2 text-center">
        <p className={`text-xs font-semibold ${isCenter ? 'text-text-main' : 'text-text-muted'}`}>
          {MONTH_NAMES[monthRef.month].slice(0, 3)} {monthRef.year}
        </p>
      </div>

      <div className="grid grid-cols-7 gap-0.5 mb-1">
        {WEEKDAY_LABELS.map((label, index) => (
          <div
            key={`${monthRef.year}-${monthRef.month}-${index}`}
            className="text-center text-[9px] font-semibold text-text-muted"
          >
            {label}
          </div>
        ))}
      </div>

      <div className="grid grid-cols-7 gap-0.5">
        {cells.map((day, index) => {
          if (day === null) {
            return <div key={`empty-${index}`} className="h-6" aria-hidden="true" />;
          }

          const isoDate = toIsoDate(monthRef.year, monthRef.month, day);
          const entry = holidayMap[isoDate];
          const isHoliday = Boolean(entry);
          const isPrivate = entry?.is_private ?? false;
          const isSelected = selectedDates.has(isoDate);
          const isToday =
            monthRef.year === today.getFullYear() &&
            monthRef.month === today.getMonth() &&
            day === today.getDate();

          return (
            <button
              key={isoDate}
              type="button"
              aria-pressed={multiSelectMode ? isSelected : isHoliday}
              title={
                multiSelectMode
                  ? isSelected
                    ? `${formatHolidayDate(isoDate)}: selected`
                    : `${formatHolidayDate(isoDate)}: click to select`
                  : isHoliday
                    ? `${formatHolidayDate(isoDate)}: ${entry?.label ?? PRIVATE_HOLIDAY_LABEL}`
                    : `${formatHolidayDate(isoDate)}: click to mark holiday`
              }
              onClick={() => onDayClick(monthRef.year, monthRef.month, day)}
              className={`h-6 w-full rounded text-[10px] font-medium leading-none transition-colors ${
                isHoliday
                  ? isPrivate
                    ? 'private-holiday-day'
                    : 'public-holiday-day'
                  : 'text-text-main hover:bg-card'
              } ${isSelected ? 'holiday-selection-day' : ''} ${
                isToday && !isHoliday && !isSelected ? 'ring-1 ring-accent/50' : ''
              }`}
            >
              {day}
            </button>
          );
        })}
      </div>
    </div>
  );
};

const PublicHolidayCalendar: React.FC = () => {
  const today = new Date();
  const [centerYear, setCenterYear] = useState(today.getFullYear());
  const [centerMonth, setCenterMonth] = useState(today.getMonth());
  const [holidayMap, setHolidayMap] = useState<Record<string, PublicHolidayEntry>>({});
  const [meta, setMeta] = useState<PublicHolidaysResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [multiSelectMode, setMultiSelectMode] = useState(false);
  const [selectedDates, setSelectedDates] = useState<Set<string>>(new Set());
  const [editorDate, setEditorDate] = useState<string | null>(null);
  const [editorName, setEditorName] = useState('');
  const [bulkAction, setBulkAction] = useState<BulkAction>(null);
  const [bulkName, setBulkName] = useState('');

  const visibleMonths = useMemo(
    () => [
      addMonths(centerYear, centerMonth, -1),
      { year: centerYear, month: centerMonth },
      addMonths(centerYear, centerMonth, 1),
    ],
    [centerMonth, centerYear]
  );

  const selectedDateList = useMemo(
    () => [...selectedDates].sort((left, right) => left.localeCompare(right)),
    [selectedDates]
  );

  const loadHolidays = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = (await apiFetch('settings/public-holidays')) as PublicHolidaysResponse;
      const items = Array.isArray(data.holidays) ? data.holidays : [];
      setHolidayMap(Object.fromEntries(items.map(item => [item.date, item])));
      setMeta(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load public holidays.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadHolidays();
  }, [loadHolidays]);

  const centerMonthHolidays = useMemo(() => {
    const prefix = `${centerYear}-${String(centerMonth + 1).padStart(2, '0')}-`;
    return Object.values(holidayMap)
      .filter(entry => entry.date.startsWith(prefix))
      .sort((left, right) => left.date.localeCompare(right.date));
  }, [centerMonth, centerYear, holidayMap]);

  const editorEntry = editorDate ? holidayMap[editorDate] : undefined;
  const previousMonth = visibleMonths[0];
  const nextMonth = visibleMonths[2];

  const goToPreviousMonth = () => {
    const previous = addMonths(centerYear, centerMonth, -1);
    setCenterYear(previous.year);
    setCenterMonth(previous.month);
  };

  const goToNextMonth = () => {
    const next = addMonths(centerYear, centerMonth, 1);
    setCenterYear(next.year);
    setCenterMonth(next.month);
  };

  const clearSelection = () => {
    setSelectedDates(new Set());
  };

  const toggleMultiSelectMode = () => {
    setMultiSelectMode(prev => !prev);
    clearSelection();
    closeEditor();
    setBulkAction(null);
    setBulkName('');
  };

  const handleDayClick = (year: number, month: number, day: number) => {
    const isoDate = toIsoDate(year, month, day);

    if (multiSelectMode) {
      setSelectedDates(prev => {
        const next = new Set(prev);
        if (next.has(isoDate)) {
          next.delete(isoDate);
        } else {
          next.add(isoDate);
        }
        return next;
      });
      setError(null);
      return;
    }

    const existing = holidayMap[isoDate];
    setEditorDate(isoDate);
    setEditorName(existing?.name ?? '');
    setError(null);
  };

  const closeEditor = () => {
    setEditorDate(null);
    setEditorName('');
  };

  const closeBulkModal = () => {
    setBulkAction(null);
    setBulkName('');
  };

  const applyHolidayResponse = (data: PublicHolidaysResponse) => {
    const items = Array.isArray(data.holidays) ? data.holidays : [];
    setHolidayMap(Object.fromEntries(items.map(item => [item.date, item])));
    setMeta(data);
  };

  const handleSaveHoliday = async () => {
    if (!editorDate) return;

    const previousMap = holidayMap;
    const previousMeta = meta;
    setSaving(true);
    setError(null);

    try {
      const data = (await apiFetch('settings/public-holidays/save', {
        method: 'POST',
        body: JSON.stringify({
          date: editorDate,
          name: editorName.trim() || null,
        }),
      })) as PublicHolidaysResponse;
      applyHolidayResponse(data);
      closeEditor();
    } catch (err: unknown) {
      setHolidayMap(previousMap);
      setMeta(previousMeta);
      setError(err instanceof Error ? err.message : 'Failed to save holiday.');
    } finally {
      setSaving(false);
    }
  };

  const handleRemoveHoliday = async () => {
    if (!editorDate) return;

    const previousMap = holidayMap;
    const previousMeta = meta;
    setSaving(true);
    setError(null);

    try {
      const data = (await apiFetch('settings/public-holidays/remove', {
        method: 'POST',
        body: JSON.stringify({ date: editorDate }),
      })) as PublicHolidaysResponse;
      applyHolidayResponse(data);
      closeEditor();
    } catch (err: unknown) {
      setHolidayMap(previousMap);
      setMeta(previousMeta);
      setError(err instanceof Error ? err.message : 'Failed to remove holiday.');
    } finally {
      setSaving(false);
    }
  };

  const handleBulkSave = async (name: string | null) => {
    if (selectedDateList.length === 0) return;

    const previousMap = holidayMap;
    const previousMeta = meta;
    setSaving(true);
    setError(null);

    try {
      const data = (await apiFetch('settings/public-holidays/bulk-save', {
        method: 'POST',
        body: JSON.stringify({
          dates: selectedDateList,
          name,
        }),
      })) as PublicHolidaysResponse;
      applyHolidayResponse(data);
      clearSelection();
      closeBulkModal();
    } catch (err: unknown) {
      setHolidayMap(previousMap);
      setMeta(previousMeta);
      setError(err instanceof Error ? err.message : 'Failed to save holidays.');
    } finally {
      setSaving(false);
    }
  };

  const handleBulkRemove = async () => {
    if (selectedDateList.length === 0) return;

    const previousMap = holidayMap;
    const previousMeta = meta;
    setSaving(true);
    setError(null);

    try {
      const data = (await apiFetch('settings/public-holidays/bulk-remove', {
        method: 'POST',
        body: JSON.stringify({ dates: selectedDateList }),
      })) as PublicHolidaysResponse;
      applyHolidayResponse(data);
      clearSelection();
    } catch (err: unknown) {
      setHolidayMap(previousMap);
      setMeta(previousMeta);
      setError(err instanceof Error ? err.message : 'Failed to remove holidays.');
    } finally {
      setSaving(false);
    }
  };

  const handleBulkPublicSubmit = async () => {
    const trimmedName = bulkName.trim();
    if (!trimmedName) {
      setError('Enter a holiday name to mark selected dates as public holidays.');
      return;
    }
    await handleBulkSave(trimmedName);
  };

  return (
    <div className="rounded-2xl border border-border-subtle bg-card overflow-hidden">
      <div className="border-b border-border-subtle bg-surface-bg px-4 py-3 md:px-5">
        <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
          <div>
            <h2 className="text-base font-semibold text-text-main flex items-center gap-2">
              <CalendarDays size={18} />
              Holiday Calendar
            </h2>
            <p className="text-xs text-text-muted mt-1 max-w-2xl">
              Block single or multiple dates when support is unavailable. Use multi-select to mark several days as public
              holidays (with a name) or private holidays.
            </p>
          </div>
          <div className="text-[11px] text-text-muted space-y-0.5 md:text-right">
            <p>Last updated: {meta?.updated_at ? new Date(meta.updated_at).toLocaleString() : 'Not saved yet'}</p>
            <p>Modified by: {formatModifiedBy(meta)}</p>
          </div>
        </div>
      </div>

      {error && (
        <div className="mx-4 mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 md:mx-5">
          {error}
        </div>
      )}

      <div className="p-4 md:p-5">
        {loading ? (
          <div className="flex items-center justify-center py-8 text-text-muted text-sm">
            <Loader2 size={18} className="animate-spin mr-2" />
            Loading holiday calendar...
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <button
                type="button"
                onClick={toggleMultiSelectMode}
                className={`inline-flex items-center rounded-md border px-2.5 py-1.5 text-xs font-semibold transition-colors ${
                  multiSelectMode
                    ? 'border-accent bg-accent text-text-dark-bg'
                    : 'border-border-subtle bg-card text-text-main hover:bg-surface-bg'
                }`}
              >
                {multiSelectMode ? 'Multi-select on' : 'Select multiple days'}
              </button>

              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={goToPreviousMonth}
                  className="inline-flex items-center gap-1 rounded-md border border-border-subtle px-2.5 py-1.5 text-xs font-medium text-text-main hover:bg-surface-bg"
                >
                  <ChevronLeft size={14} />
                  {MONTH_NAMES[previousMonth.month]} {previousMonth.year}
                </button>

                <p className="text-sm font-semibold text-text-main">
                  {MONTH_NAMES[centerMonth]} {centerYear}
                </p>

                <button
                  type="button"
                  onClick={goToNextMonth}
                  className="inline-flex items-center gap-1 rounded-md border border-border-subtle px-2.5 py-1.5 text-xs font-medium text-text-main hover:bg-surface-bg"
                >
                  {MONTH_NAMES[nextMonth.month]} {nextMonth.year}
                  <ChevronRight size={14} />
                </button>
              </div>
            </div>

            {multiSelectMode && (
              <div className="rounded-lg border border-border-subtle bg-surface-bg px-3 py-2.5 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-xs text-text-main">
                  {selectedDateList.length === 0
                    ? 'Click days on any visible month to select them.'
                    : `${selectedDateList.length} day${selectedDateList.length === 1 ? '' : 's'} selected`}
                </p>
                <div className="flex flex-wrap gap-1.5">
                  <button
                    type="button"
                    onClick={clearSelection}
                    disabled={selectedDateList.length === 0 || saving}
                    className="rounded-md border border-border-subtle px-2.5 py-1 text-[11px] font-semibold text-text-main hover:bg-card disabled:opacity-50"
                  >
                    Clear
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setBulkAction('public');
                      setBulkName('');
                      setError(null);
                    }}
                    disabled={selectedDateList.length === 0 || saving}
                    className="rounded-md border border-red-200 bg-red-50 px-2.5 py-1 text-[11px] font-semibold text-red-800 hover:bg-red-100 disabled:opacity-50"
                  >
                    Mark as public
                  </button>
                  <button
                    type="button"
                    onClick={() => handleBulkSave(null)}
                    disabled={selectedDateList.length === 0 || saving}
                    className="rounded-md border border-amber-200 bg-amber-50 px-2.5 py-1 text-[11px] font-semibold text-amber-900 hover:bg-amber-100 disabled:opacity-50"
                  >
                    Mark as private
                  </button>
                  <button
                    type="button"
                    onClick={handleBulkRemove}
                    disabled={selectedDateList.length === 0 || saving}
                    className="rounded-md border border-border-subtle px-2.5 py-1 text-[11px] font-semibold text-text-muted hover:bg-card disabled:opacity-50"
                  >
                    Remove blocked
                  </button>
                </div>
              </div>
            )}

            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              {visibleMonths.map(monthRef => (
                <MonthCalendar
                  key={`${monthRef.year}-${monthRef.month}`}
                  monthRef={monthRef}
                  holidayMap={holidayMap}
                  selectedDates={selectedDates}
                  multiSelectMode={multiSelectMode}
                  isCenter={monthRef.year === centerYear && monthRef.month === centerMonth}
                  today={today}
                  onDayClick={handleDayClick}
                />
              ))}
            </div>

            <div className="flex flex-wrap items-center gap-2 text-[11px] text-text-muted">
              <span className="inline-flex items-center gap-1">
                <span className="inline-block h-2.5 w-2.5 rounded-sm public-holiday-chip" />
                Public holiday
              </span>
              <span className="inline-flex items-center gap-1">
                <span className="inline-block h-2.5 w-2.5 rounded-sm private-holiday-chip" />
                Private holiday
              </span>
              {multiSelectMode && (
                <span className="inline-flex items-center gap-1">
                  <span className="inline-block h-2.5 w-2.5 rounded-sm holiday-selection-day bg-card" />
                  Selected
                </span>
              )}
              <span className="inline-flex items-center gap-1">
                <span className="inline-block h-2.5 w-2.5 rounded-sm ring-1 ring-accent/50 bg-card" />
                Today
              </span>
            </div>

            <div>
              <h3 className="text-xs font-semibold text-text-main mb-1.5">
                Holidays in {MONTH_NAMES[centerMonth]} {centerYear}
              </h3>
              {centerMonthHolidays.length === 0 ? (
                <p className="text-xs text-text-muted italic">No holidays marked for this month.</p>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {centerMonthHolidays.map(entry => (
                    <button
                      key={entry.date}
                      type="button"
                      onClick={() => {
                        if (multiSelectMode) {
                          setSelectedDates(prev => {
                            const next = new Set(prev);
                            if (next.has(entry.date)) {
                              next.delete(entry.date);
                            } else {
                              next.add(entry.date);
                            }
                            return next;
                          });
                          return;
                        }
                        setEditorDate(entry.date);
                        setEditorName(entry.name ?? '');
                        setError(null);
                      }}
                      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-medium transition-colors ${
                        entry.is_private ? 'private-holiday-chip' : 'public-holiday-chip'
                      } ${selectedDates.has(entry.date) ? 'holiday-selection-day' : ''}`}
                    >
                      {formatHolidayDate(entry.date)} · {entry.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {editorDate && !multiSelectMode && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <button
            type="button"
            className="absolute inset-0 bg-black/40"
            aria-label="Close holiday editor"
            disabled={saving}
            onClick={closeEditor}
          />
          <div className="relative w-full max-w-md rounded-2xl border border-border-subtle bg-card shadow-xl">
            <div className="flex items-start justify-between border-b border-border-subtle px-5 py-4">
              <div>
                <h3 className="text-base font-semibold text-text-main">
                  {editorEntry ? 'Edit holiday' : 'Mark holiday'}
                </h3>
                <p className="text-sm text-text-muted mt-1">{formatHolidayDate(editorDate)}</p>
              </div>
              <button
                type="button"
                onClick={closeEditor}
                disabled={saving}
                className="rounded-lg p-1 text-text-muted hover:bg-surface-bg hover:text-text-main disabled:opacity-50"
                aria-label="Close"
              >
                <X size={18} />
              </button>
            </div>

            <div className="px-5 py-4 space-y-4">
              <div>
                <label htmlFor="holiday-name" className="block text-sm font-medium text-text-main mb-1.5">
                  Holiday name
                </label>
                <input
                  id="holiday-name"
                  type="text"
                  value={editorName}
                  maxLength={100}
                  placeholder="e.g. Republic Day"
                  onChange={event => setEditorName(event.target.value)}
                  className="w-full rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm text-text-main focus:outline-none focus:border-accent focus:ring-4 focus:ring-accent/10"
                />
                <p className="text-xs text-text-muted mt-2">
                  Add a name for a public holiday, or leave blank to save as a{' '}
                  <span className="font-medium">{PRIVATE_HOLIDAY_LABEL.toLowerCase()}</span>.
                </p>
              </div>

              <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
                {editorEntry && (
                  <button
                    type="button"
                    onClick={handleRemoveHoliday}
                    disabled={saving}
                    className="inline-flex items-center justify-center rounded-lg border border-red-200 px-4 py-2 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50"
                  >
                    Remove
                  </button>
                )}
                <button
                  type="button"
                  onClick={closeEditor}
                  disabled={saving}
                  className="inline-flex items-center justify-center rounded-lg border border-border-subtle px-4 py-2 text-sm font-semibold text-text-main hover:bg-surface-bg disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleSaveHoliday}
                  disabled={saving}
                  className="inline-flex items-center justify-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg hover:opacity-90 disabled:opacity-50"
                >
                  {saving && <Loader2 size={16} className="animate-spin" />}
                  {editorName.trim() ? 'Save public holiday' : 'Save as private holiday'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {bulkAction === 'public' && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <button
            type="button"
            className="absolute inset-0 bg-black/40"
            aria-label="Close bulk holiday editor"
            disabled={saving}
            onClick={closeBulkModal}
          />
          <div className="relative w-full max-w-md rounded-2xl border border-border-subtle bg-card shadow-xl">
            <div className="flex items-start justify-between border-b border-border-subtle px-5 py-4">
              <div>
                <h3 className="text-base font-semibold text-text-main">Mark public holidays</h3>
                <p className="text-sm text-text-muted mt-1">
                  {selectedDateList.length} selected day{selectedDateList.length === 1 ? '' : 's'}
                </p>
              </div>
              <button
                type="button"
                onClick={closeBulkModal}
                disabled={saving}
                className="rounded-lg p-1 text-text-muted hover:bg-surface-bg hover:text-text-main disabled:opacity-50"
                aria-label="Close"
              >
                <X size={18} />
              </button>
            </div>

            <div className="px-5 py-4 space-y-4">
              <div className="max-h-28 overflow-y-auto rounded-lg border border-border-subtle bg-surface-bg px-3 py-2">
                <ul className="space-y-1 text-xs text-text-muted">
                  {selectedDateList.map(isoDate => (
                    <li key={isoDate}>{formatHolidayDate(isoDate)}</li>
                  ))}
                </ul>
              </div>

              <div>
                <label htmlFor="bulk-holiday-name" className="block text-sm font-medium text-text-main mb-1.5">
                  Holiday name
                </label>
                <input
                  id="bulk-holiday-name"
                  type="text"
                  value={bulkName}
                  maxLength={100}
                  placeholder="e.g. Christmas break"
                  onChange={event => setBulkName(event.target.value)}
                  className="w-full rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm text-text-main focus:outline-none focus:border-accent focus:ring-4 focus:ring-accent/10"
                />
                <p className="text-xs text-text-muted mt-2">
                  This name will apply to all selected dates as public holidays.
                </p>
              </div>

              <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
                <button
                  type="button"
                  onClick={closeBulkModal}
                  disabled={saving}
                  className="inline-flex items-center justify-center rounded-lg border border-border-subtle px-4 py-2 text-sm font-semibold text-text-main hover:bg-surface-bg disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleBulkPublicSubmit}
                  disabled={saving}
                  className="inline-flex items-center justify-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg hover:opacity-90 disabled:opacity-50"
                >
                  {saving && <Loader2 size={16} className="animate-spin" />}
                  Save public holidays
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default PublicHolidayCalendar;
