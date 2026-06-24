import { InternalMessage } from '../hooks/useMessagingHub';

export interface PinnedMessageSnapshot {
  message_id: number;
  conversation_id: number;
  sender_id: number;
  sender_name: string;
  content: string;
  content_type: string;
  created_at: string;
}

const STORAGE_PREFIX = 'messaging-hub:pins';

const storageKey = (userId: number) => `${STORAGE_PREFIX}:${userId}`;

export const snapshotFromMessage = (message: InternalMessage): PinnedMessageSnapshot => ({
  message_id: message.id,
  conversation_id: message.conversation_id,
  sender_id: message.sender_id,
  sender_name: message.sender_name,
  content:
    message.content_type === 'audio' ? 'Voice note' : message.content,
  content_type: message.content_type,
  created_at: message.created_at,
});

export const hydratePinnedMessages = (
  userId: number | null
): Record<number, PinnedMessageSnapshot> => {
  if (!userId) return {};
  try {
    const raw = sessionStorage.getItem(storageKey(userId));
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, PinnedMessageSnapshot>;
    const result: Record<number, PinnedMessageSnapshot> = {};
    Object.entries(parsed).forEach(([conversationId, snapshot]) => {
      if (snapshot && Number.isFinite(Number(conversationId))) {
        result[Number(conversationId)] = snapshot;
      }
    });
    return result;
  } catch {
    return {};
  }
};

export const persistPinnedMessages = (
  userId: number | null,
  pins: Record<number, PinnedMessageSnapshot>
): void => {
  if (!userId) return;
  try {
    const payload: Record<string, PinnedMessageSnapshot> = {};
    Object.entries(pins).forEach(([conversationId, snapshot]) => {
      payload[conversationId] = snapshot;
    });
    sessionStorage.setItem(storageKey(userId), JSON.stringify(payload));
  } catch {
    // ignore quota errors
  }
};
