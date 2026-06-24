const minuteKey = (iso: string): string => {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}-${date.getHours()}:${date.getMinutes()}`;
};

/**
 * Show timestamp (outgoing) or sender name + avatar + timestamp (incoming)
 * on the first message of each consecutive run with the same sender and minute.
 */
export const shouldShowMessageTimestamp = <T>(
  messages: T[],
  index: number,
  getSenderId: (message: T) => number,
  getCreatedAt: (message: T) => string
): boolean => {
  const current = messages[index];
  if (!current) return false;

  const previous = messages[index - 1];
  if (!previous) return true;

  const sameSender = getSenderId(current) === getSenderId(previous);
  const sameMinute = minuteKey(getCreatedAt(current)) === minuteKey(getCreatedAt(previous));

  return !(sameSender && sameMinute);
};

export const formatMessageTime = (iso: string): string =>
  new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

/**
 * Show sender name, avatar, and timestamp on the first message of each
 * consecutive run that shares the same sender and clock minute.
 */
export const shouldShowMessageClusterHeader = shouldShowMessageTimestamp;
