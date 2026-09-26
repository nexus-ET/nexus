export type ScheduledTimeTone =
  | 'today-upcoming'
  | 'today-overdue'
  | 'tomorrow'
  | 'day-after-tomorrow'
  | 'upcoming'
  | 'past';

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'] as const;
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'] as const;

export const SCHEDULED_TIME_BADGE_CLASS: Record<ScheduledTimeTone, string> = {
  'today-upcoming': 'text-amber-700 bg-amber-50 border-amber-200',
  'today-overdue': 'text-red-700 bg-red-50 border-red-200',
  tomorrow: 'text-emerald-700 bg-emerald-50 border-emerald-200',
  'day-after-tomorrow': 'text-blue-700 bg-blue-50 border-blue-200',
  upcoming: 'text-slate-600 bg-slate-100 border-slate-300',
  past: 'text-gray-400 bg-gray-50 border-gray-200',
};

/** Wall-clock appointment fields as a local Date (browser calendar, no UTC shift). */
export function parseScheduledWallClock(value: string | null | undefined): Date | null {
  if (!value) return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  const match = trimmed.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
  if (match) {
    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    const hour = Number(match[4]);
    const minute = Number(match[5]);
    const date = new Date(year, month - 1, day, hour, minute, 0, 0);
    if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) {
      return null;
    }
    return date;
  }
  const fallback = new Date(trimmed);
  return Number.isNaN(fallback.getTime()) ? null : fallback;
}

function pad2(value: number): string {
  return String(value).padStart(2, '0');
}

function formatClock(date: Date): string {
  return `${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
}

/** Same short names as Scheduled Time: Sun, Mon, Tue, Wed, Thu, Fri, Sat. */
export function scheduledWeekdayShort(date: Date): string {
  return WEEKDAYS[date.getDay()];
}

/** Example: Tue, 22-Sep-26 (11:00 - 11:30). */
export function formatScheduledTimeRange(start: Date, end: Date): string {
  const weekday = scheduledWeekdayShort(start);
  const day = pad2(start.getDate());
  const month = MONTHS[start.getMonth()];
  const year = pad2(start.getFullYear() % 100);
  return `${weekday}, ${day}-${month}-${year} (${formatClock(start)} - ${formatClock(end)})`;
}

/** Date-only tones. Today is never overdue: there is no time of day. */
export type FollowupDateTone = Exclude<ScheduledTimeTone, 'today-overdue'>;

/**
 * Whole local calendar days from `now` to `target`, with the clock stripped.
 * Uses the local year/month/day of each instant so a future day is never
 * scored from leftover hours, including across daylight-saving boundaries.
 */
export function localCalendarDayDiff(target: Date, now: Date): number {
  const targetDay = Date.UTC(target.getFullYear(), target.getMonth(), target.getDate());
  const today = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((targetDay - today) / 86_400_000);
}

/** Calendar-day tone. Today is upcoming here; overdue is applied only by the clock classifier. */
export function classifyCalendarDay(diffDays: number): FollowupDateTone {
  if (diffDays === 0) return 'today-upcoming';
  if (diffDays === 1) return 'tomorrow';
  if (diffDays === 2) return 'day-after-tomorrow';
  if (diffDays >= 3) return 'upcoming';
  return 'past';
}

/**
 * Booking date and time. Overdue only when the local calendar day is today
 * and the scheduled start is already before now.
 */
export function classifyScheduledTime(start: Date, now: Date): ScheduledTimeTone {
  const diffDays = localCalendarDayDiff(start, now);
  if (diffDays === 0) {
    return start.getTime() < now.getTime() ? 'today-overdue' : 'today-upcoming';
  }
  return classifyCalendarDay(diffDays);
}

/** Local calendar date from YYYY-MM-DD (optional time suffix ignored). */
function parseFollowupCalendarDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const match = value.trim().match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(year, month - 1, day);
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) {
    return null;
  }
  return date;
}

/**
 * Date-only follow-up. Today stays upcoming. The clock is ignored, so a future
 * calendar day is never overdue.
 */
export function classifyFollowupDate(
  value: string | null | undefined,
  now: Date
): FollowupDateTone | null {
  const diffDays = followupCalendarDayDiff(value, now);
  if (diffDays === null) return null;
  return classifyCalendarDay(diffDays);
}

/** Local calendar-day offset for a follow-up date, or null when there is no date. */
export function followupCalendarDayDiff(
  value: string | null | undefined,
  now: Date
): number | null {
  const date = parseFollowupCalendarDate(value);
  if (!date) return null;
  return localCalendarDayDiff(date, now);
}

export type DateFilterColumn = 'booking' | 'followup';

const DATE_FILTER_KEYWORDS = [
  'today',
  'tomorrow',
  'day after tomorrow',
  'upcoming',
  'overdue',
  'completed',
] as const;

export type DateFilterKeyword = (typeof DATE_FILTER_KEYWORDS)[number];

/**
 * Keywords the typed text should include. The query matches a keyword when it
 * is a prefix of that phrase or of any word in it, so partials of all six work:
 * "t"/"to" hit Today, Tomorrow, and Day after tomorrow; "o"/"ov" hit only
 * Overdue; "c" hits only Completed; "u" hits only Upcoming; "day"/"after" hit
 * Day after tomorrow. Several hits are unioned. Empty text matches nothing.
 */
export function calendarDateKeywordsForQuery(raw: string): DateFilterKeyword[] {
  const query = raw.trim().toLowerCase().replace(/\s+/g, ' ');
  if (!query) return [];
  return DATE_FILTER_KEYWORDS.filter(keyword => {
    if (keyword.startsWith(query)) return true;
    return keyword.split(' ').some(word => word.startsWith(query));
  });
}

function keywordMatchesDayDiff(
  keyword: DateFilterKeyword,
  diffDays: number,
  options: { column: DateFilterColumn; startHasPassed?: boolean }
): boolean {
  if (keyword === 'overdue') {
    if (options.column === 'followup') return false;
    return diffDays === 0 && options.startHasPassed === true;
  }
  if (keyword === 'today') return diffDays === 0;
  if (keyword === 'tomorrow') return diffDays === 1;
  if (keyword === 'day after tomorrow') return diffDays === 2;
  if (keyword === 'upcoming') return diffDays >= 1;
  return diffDays < 0;
}

/**
 * Union of every keyword the typed text hits.
 * Null means the text is not part of any keyword (search the visible cell instead).
 * False means it is a keyword, but this row's calendar day is outside those buckets.
 */
export function matchCalendarDateKeyword(
  raw: string,
  diffDays: number | null,
  options: { column: DateFilterColumn; startHasPassed?: boolean }
): boolean | null {
  const keywords = calendarDateKeywordsForQuery(raw);
  if (keywords.length === 0) return null;
  if (diffDays === null) return false;
  return keywords.some(keyword => keywordMatchesDayDiff(keyword, diffDays, options));
}

/** True when the text is a partial or full date keyword, so the table walks every page. */
export function isCalendarDateKeyword(raw: string, _column: DateFilterColumn): boolean {
  return calendarDateKeywordsForQuery(raw).length > 0;
}
