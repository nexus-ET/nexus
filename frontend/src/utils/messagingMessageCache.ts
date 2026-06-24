import { getCurrentUserId } from './api';

export interface CachedChatMessage {
  id: number;
  conversation_id: number;
  sender_id: number;
  sender_name?: string;
  content: string;
  content_type: string;
  media_url?: string | null;
  reply_to_message_id?: number | null;
  created_at: string;
  pending?: boolean;
  reactions?: unknown[];
  reply_to?: unknown | null;
}

const MESSAGING_STORAGE_PREFIX = 'messaging-hub';
const MAX_CACHED_MESSAGES = 300;

const storageKey = (userId: number, suffix: string) =>
  `${MESSAGING_STORAGE_PREFIX}:${suffix}:${userId}`;

export const upsertCachedMessage = <T extends CachedChatMessage>(
  prev: T[],
  message: T
): T[] => {
  if (!message?.id) return prev;
  const index = prev.findIndex(item => item.id === message.id);
  if (index !== -1) {
    const next = [...prev];
    next[index] = { ...next[index], ...message, pending: false };
    return next;
  }
  const tempIndex = prev.findIndex(
    item =>
      item.pending &&
      item.sender_id === message.sender_id &&
      item.content === message.content &&
      item.content_type === message.content_type &&
      (item.reply_to_message_id ?? null) === (message.reply_to_message_id ?? null)
  );
  if (tempIndex !== -1) {
    const next = [...prev];
    next[tempIndex] = { ...message, pending: false };
    return next;
  }
  return [...prev, message];
};

const readCacheRecord = (userId: number): Record<string, CachedChatMessage[]> => {
  try {
    const raw = sessionStorage.getItem(storageKey(userId, 'cache'));
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, CachedChatMessage[]>;
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
};

export const cacheIncomingMessage = (
  message: CachedChatMessage,
  userId: number | null = getCurrentUserId()
): void => {
  if (!userId || !message?.conversation_id) return;

  const record = readCacheRecord(userId);
  const key = String(message.conversation_id);
  const existing = Array.isArray(record[key]) ? record[key] : [];
  record[key] = upsertCachedMessage(existing, message).slice(-MAX_CACHED_MESSAGES);

  try {
    sessionStorage.setItem(storageKey(userId, 'cache'), JSON.stringify(record));
  } catch {
    // sessionStorage quota exceeded
  }

  window.dispatchEvent(
    new CustomEvent('nexus:incoming-message', {
      detail: { message },
    })
  );
};

export const readCachedConversationMessages = (
  conversationId: number,
  userId: number | null = getCurrentUserId()
): CachedChatMessage[] => {
  if (!userId) return [];
  const record = readCacheRecord(userId);
  const items = record[String(conversationId)];
  return Array.isArray(items) ? items : [];
};

export const INCOMING_MESSAGE_EVENT = 'nexus:incoming-message';
export const RELOAD_CONVERSATION_EVENT = 'nexus:reload-conversation';
