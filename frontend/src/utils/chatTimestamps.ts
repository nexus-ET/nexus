import { getApiMinuteKey, formatApiClockTime } from './timezone';

/**
 * Show timestamp (outgoing) or sender name + avatar + timestamp (incoming)
 * on the first message of each consecutive run with the same sender and minute.
 *
 * Pass businessTimezone so clustering matches displayed clock times.
 */
export const shouldShowMessageTimestamp = <T>(
  messages: T[],
  index: number,
  getSenderId: (message: T) => number,
  getCreatedAt: (message: T) => string,
  businessTimezone = 'UTC'
): boolean => {
  const current = messages[index];
  if (!current) return false;

  const previous = messages[index - 1];
  if (!previous) return true;

  const sameSender = getSenderId(current) === getSenderId(previous);
  const sameMinute =
    getApiMinuteKey(getCreatedAt(current), businessTimezone) ===
    getApiMinuteKey(getCreatedAt(previous), businessTimezone);

  return !(sameSender && sameMinute);
};

export const formatMessageTime = (iso: string, businessTimezone = 'UTC'): string =>
  formatApiClockTime(iso, businessTimezone);

/**
 * Show sender name, avatar, and timestamp on the first message of each
 * consecutive run that shares the same sender and clock minute.
 */
export const shouldShowMessageClusterHeader = shouldShowMessageTimestamp;
