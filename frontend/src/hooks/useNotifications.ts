import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { getCurrentUserId, hasValidSession } from '../utils/api';
import { connectNexusWebSocket, NexusSocketHandle } from '../utils/nexusWebSocket';
import {
  cacheIncomingMessage,
  CachedChatMessage,
} from '../utils/messagingMessageCache';
import { useNexusSession } from '../context/NexusSessionContext';

const MESSAGING_HUB_PATH = '/messaging-hub';

interface IncomingMessagePayload {
  id?: number;
  conversation_id?: number;
  sender_id?: number;
  sender_name?: string;
  content?: string;
  content_type?: string;
  media_url?: string | null;
  reply_to_message_id?: number | null;
  created_at?: string;
}

const normalizeIncomingMessage = (data: IncomingMessagePayload): CachedChatMessage | null => {
  const id = Number(data.id);
  const conversationId = Number(data.conversation_id);
  const senderId = Number(data.sender_id);
  if (!Number.isFinite(id) || !Number.isFinite(conversationId) || !Number.isFinite(senderId)) {
    return null;
  }
  return {
    id,
    conversation_id: conversationId,
    sender_id: senderId,
    sender_name: data.sender_name,
    content: data.content ?? '',
    content_type: data.content_type ?? 'text',
    media_url: data.media_url ?? null,
    reply_to_message_id: data.reply_to_message_id ?? null,
    created_at:
      typeof data.created_at === 'string' ? data.created_at : new Date().toISOString(),
  };
};

/** Global messaging toasts + unread badge sync (outside Messaging Hub). */
export function useNotifications(enabled: boolean): void {
  const location = useLocation();
  const socketRef = useRef<NexusSocketHandle | null>(null);
  const {
    showMessageToast,
    dismissMessageToast,
    setUnreadMessageCount,
    setMessagingHubPulse,
    refreshUnreadMessageCount,
  } = useNexusSession();

  useEffect(() => {
    if (!enabled || !hasValidSession()) return;
    void refreshUnreadMessageCount();
  }, [enabled, refreshUnreadMessageCount]);

  useEffect(() => {
    const onMessagingHub = location.pathname.replace(/\/$/, '') === MESSAGING_HUB_PATH;
    if (onMessagingHub) {
      dismissMessageToast();
      setMessagingHubPulse(false);
    }
  }, [location.pathname, dismissMessageToast, setMessagingHubPulse]);

  useEffect(() => {
    if (!enabled || !hasValidSession()) return;

    socketRef.current = connectNexusWebSocket({
      onMessage: event => {
        try {
          const payload = JSON.parse(event.data as string);
          const type = payload.type as string;
          const data = payload.data ?? payload;

          if (type === 'unread_count_update') {
            const count = Number(data.unread_message_count ?? 0);
            setUnreadMessageCount(Number.isFinite(count) ? count : 0);
            const onHub = window.location.pathname.replace(/\/$/, '') === MESSAGING_HUB_PATH;
            setMessagingHubPulse(!onHub && count > 0);
            return;
          }

          if (type !== 'messaging.message') return;

          const message = data as IncomingMessagePayload;
          const selfId = getCurrentUserId();
          if (selfId != null && message.sender_id === selfId) return;

          const normalized = normalizeIncomingMessage(message);
          if (normalized) {
            cacheIncomingMessage(normalized);
          }

          const onHub = window.location.pathname.replace(/\/$/, '') === MESSAGING_HUB_PATH;
          if (onHub) return;

          const snippet =
            message.content_type === 'audio'
              ? 'Voice note'
              : (message.content || 'New message').slice(0, 120);

          showMessageToast({
            senderName: message.sender_name || 'Someone',
            snippet,
            conversationId: Number(message.conversation_id),
            messageId: Number(message.id),
          });
        } catch {
          // Ignore malformed websocket frames.
        }
      },
    });

    return () => {
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [enabled, showMessageToast, setUnreadMessageCount, setMessagingHubPulse]);
}
