import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { apiFetch, apiUpload, getCurrentUserId, getStoredToken } from '../utils/api';
import { connectNexusWebSocket, NexusSocketHandle } from '../utils/nexusWebSocket';
import {
  INCOMING_MESSAGE_EVENT,
  readCachedConversationMessages,
  upsertCachedMessage,
} from '../utils/messagingMessageCache';
import { PresenceInfo } from '../components/PresenceIndicator';

export interface AdminSearchResult {
  id: number;
  full_name: string;
  email: string;
  status?: string;
  last_seen_at?: string | null;
  last_active_at?: string | null;
  away_duration_seconds?: number | null;
}

export interface ConversationParticipant {
  admin_id: number;
  full_name: string;
  email: string;
  last_read_at?: string | null;
  status?: string;
  last_seen_at?: string | null;
  last_active_at?: string | null;
  away_duration_seconds?: number | null;
}

export interface Conversation {
  id: number;
  type: 'direct' | 'group' | string;
  name?: string | null;
  display_name: string;
  last_message_at?: string | null;
  last_message_snippet?: string | null;
  unread_count: number;
  participants: ConversationParticipant[];
  /** Client-only sort hint for empty threads opened offline. */
  opened_at?: number;
}

export interface ReplyToMessage {
  id: number;
  sender_id: number;
  sender_name: string;
  content: string;
  content_type: string;
}

export interface MessageReaction {
  emoji: string;
  count: number;
  user_ids: number[];
  reacted_by_me?: boolean;
}

export interface InternalMessage {
  id: number;
  conversation_id: number;
  sender_id: number;
  sender_name: string;
  content: string;
  content_type: string;
  media_url?: string | null;
  reply_to_message_id?: number | null;
  reply_to?: ReplyToMessage | null;
  reactions?: MessageReaction[];
  created_at: string;
  pending?: boolean;
}

export interface JumpTarget {
  messageId: number;
  conversationId: number;
  query: string;
}

interface MessagingHubState {
  connected: boolean;
  conversations: Conversation[];
  sortedInbox: Conversation[];
  activeConversation: Conversation | null;
  activeConversationId: number | null;
  messages: InternalMessage[];
  typingUserIds: number[];
  presenceByUserId: Record<number, PresenceInfo>;
  jumpTarget: JumpTarget | null;
  currentUserId: number | null;
  setActiveConversationId: (id: number | null) => void;
  selectConversation: (conversation: Conversation) => void;
  jumpToSearchResult: (conversationId: number, messageId: number, query: string) => void;
  clearJumpTarget: () => void;
  refreshConversations: () => Promise<void>;
  getOrCreateDirect: (adminId: number) => Promise<Conversation>;
  sendTextMessage: (content: string, replyToMessageId?: number | null) => void;
  sendVoiceMessage: (blob: Blob) => Promise<void>;
  toggleMessageReaction: (messageId: number, emoji: string) => Promise<void>;
  markRead: () => void;
  sendTyping: (isTyping: boolean) => void;
  searchAdmins: (query: string) => Promise<AdminSearchResult[]>;
  addParticipant: (adminId: number) => Promise<void>;
  removeParticipant: (adminId: number) => Promise<void>;
  sendError: string | null;
  clearSendError: () => void;
  inboxReady: boolean;
  getConversationPreview: (conversation: Conversation) => string;
}

const MessagingHubContext = createContext<MessagingHubState | null>(null);

const MESSAGING_STORAGE_PREFIX = 'messaging-hub';
const MAX_CACHED_MESSAGES = 300;

const storageKey = (userId: number, suffix: string) =>
  `${MESSAGING_STORAGE_PREFIX}:${suffix}:${userId}`;

const readStoredActiveConversationId = (userId: number | null): number | null => {
  if (!userId) return null;
  const raw = sessionStorage.getItem(storageKey(userId, 'active'));
  if (!raw) return null;
  const id = Number(raw);
  return Number.isFinite(id) ? id : null;
};

const writeStoredActiveConversationId = (
  userId: number | null,
  conversationId: number | null
): void => {
  if (!userId) return;
  const key = storageKey(userId, 'active');
  if (conversationId == null) sessionStorage.removeItem(key);
  else sessionStorage.setItem(key, String(conversationId));
};

const hydrateMessageCache = (userId: number | null): Map<number, InternalMessage[]> => {
  const map = new Map<number, InternalMessage[]>();
  if (!userId) return map;
  try {
    const raw = sessionStorage.getItem(storageKey(userId, 'cache'));
    if (!raw) return map;
    const parsed = JSON.parse(raw) as Record<string, InternalMessage[]>;
    Object.entries(parsed).forEach(([id, items]) => {
      if (Array.isArray(items) && items.length > 0) {
        map.set(Number(id), items);
      }
    });
  } catch {
    // ignore corrupt cache
  }
  return map;
};

const persistMessageCache = (
  userId: number | null,
  cache: Map<number, InternalMessage[]>
): void => {
  if (!userId) return;
  try {
    const payload: Record<string, InternalMessage[]> = {};
    cache.forEach((items, id) => {
      payload[String(id)] = items.slice(-MAX_CACHED_MESSAGES);
    });
    sessionStorage.setItem(storageKey(userId, 'cache'), JSON.stringify(payload));
  } catch {
    // sessionStorage quota exceeded
  }
};

const hydrateInbox = (userId: number | null): Conversation[] => {
  if (!userId) return [];
  try {
    const raw = sessionStorage.getItem(storageKey(userId, 'inbox'));
    if (!raw) return [];
    return parseConversationsResponse(JSON.parse(raw));
  } catch {
    return [];
  }
};

const persistInbox = (userId: number | null, conversations: Conversation[]): void => {
  if (!userId || conversations.length === 0) return;
  try {
    sessionStorage.setItem(storageKey(userId, 'inbox'), JSON.stringify(conversations));
  } catch {
    // sessionStorage quota exceeded
  }
};

const previewFromMessages = (items: InternalMessage[] | undefined): string | null => {
  if (!items?.length) return null;
  const last = items[items.length - 1];
  if (last.content_type === 'audio') return 'Voice note';
  const text = (last.content || '').trim();
  return text ? text.slice(0, 120) : null;
};

const normalizeParticipant = (participant: ConversationParticipant): ConversationParticipant => ({
  ...participant,
  admin_id: Number(participant.admin_id),
});

const normalizeConversation = (
  raw: Partial<Conversation> & { id?: unknown },
  extras?: Partial<Conversation>
): Conversation => {
  const id = Number(raw.id);
  return {
    id,
    type: raw.type ?? 'direct',
    name: raw.name ?? null,
    display_name: (raw.display_name || 'Admin').trim() || 'Admin',
    last_message_at: raw.last_message_at ?? null,
    last_message_snippet: raw.last_message_snippet ?? null,
    unread_count: Number(raw.unread_count ?? 0),
    participants: Array.isArray(raw.participants)
      ? raw.participants.map(item => normalizeParticipant(item as ConversationParticipant))
      : [],
    ...extras,
  };
};

const conversationSortTime = (conversation: Conversation): number => {
  const messageTime = conversation.last_message_at
    ? new Date(conversation.last_message_at).getTime()
    : 0;
  const openedTime = conversation.opened_at ?? 0;
  return Math.max(messageTime, openedTime);
};

const parseConversationResponse = (data: unknown): Partial<Conversation> => {
  if (!data || typeof data !== 'object') return {};
  if ('id' in data) return data as Partial<Conversation>;
  if ('conversation' in data && (data as { conversation?: unknown }).conversation) {
    return (data as { conversation: Partial<Conversation> }).conversation;
  }
  return data as Partial<Conversation>;
};

const parseConversationsResponse = (data: unknown): Conversation[] => {
  const rawList = Array.isArray(data)
    ? data
    : data && typeof data === 'object' && Array.isArray((data as { conversations?: unknown[] }).conversations)
      ? (data as { conversations: unknown[] }).conversations
      : [];

  return rawList
    .map(item => normalizeConversation(item as Partial<Conversation>))
    .filter(item => Number.isFinite(item.id));
};

const putConversationFirst = (list: Conversation[], conversation: Conversation): Conversation[] => {
  const normalized = normalizeConversation(conversation);
  const rest = list.filter(item => item.id !== normalized.id);
  return sortConversations([normalized, ...rest]);
};

const sortConversations = (list: Conversation[]): Conversation[] =>
  [...list].sort((a, b) => {
    const aTime = conversationSortTime(a);
    const bTime = conversationSortTime(b);
    if (bTime !== aTime) return bTime - aTime;
    return b.id - a.id;
  });

const upsertConversation = (list: Conversation[], conversation: Conversation): Conversation[] => {
  const normalized = normalizeConversation(conversation);
  const index = list.findIndex(item => item.id === normalized.id);
  if (index === -1) {
    return sortConversations([normalized, ...list]);
  }
  const next = [...list];
  next[index] = { ...next[index], ...normalized };
  return sortConversations(next);
};

const mergeConversationLists = (
  previous: Conversation[],
  incoming: Conversation[],
  pinned?: Map<number, Conversation>
): Conversation[] => {
  const merged = new Map<number, Conversation>();

  const absorb = (item: Conversation) => {
    const normalized = normalizeConversation(item);
    if (!Number.isFinite(normalized.id)) return;
    const existing = merged.get(normalized.id);
    merged.set(
      normalized.id,
      existing
        ? {
            ...existing,
            ...normalized,
            opened_at: Math.max(existing.opened_at ?? 0, normalized.opened_at ?? 0) || undefined,
          }
        : normalized
    );
  };

  previous.forEach(absorb);
  pinned?.forEach(item => absorb(item));
  incoming.forEach(absorb);

  return sortConversations(Array.from(merged.values()));
};

const upsertMessage = (prev: InternalMessage[], message: InternalMessage): InternalMessage[] =>
  upsertCachedMessage(prev, message) as InternalMessage[];

const sortMessagesByTime = (items: InternalMessage[]): InternalMessage[] =>
  [...items].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
  );

const mergeMessageLists = (base: InternalMessage[], incoming: InternalMessage[]): InternalMessage[] =>
  sortMessagesByTime(
    incoming.reduce(
      (acc, message) => upsertMessage(acc, message),
      base
    )
  );

const replaceTempMessage = (
  prev: InternalMessage[],
  tempId: number,
  message: InternalMessage
): InternalMessage[] => prev.map(item => (item.id === tempId ? { ...message, pending: false } : item));

const formatSendError = (error: unknown): string => {
  if (error instanceof Error && error.message) return error.message;
  return 'Failed to send message';
};

export const MessagingHubProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const initialSnapshotRef = useRef<{
    userId: number | null;
    activeId: number | null;
    inbox: Conversation[];
    messageCache: Map<number, InternalMessage[]>;
  } | null>(null);

  if (!initialSnapshotRef.current) {
    const userId = getCurrentUserId();
    initialSnapshotRef.current = {
      userId,
      activeId: readStoredActiveConversationId(userId),
      inbox: hydrateInbox(userId),
      messageCache: hydrateMessageCache(userId),
    };
  }

  const {
    userId: initialUserId,
    activeId: initialActiveId,
    inbox: initialInbox,
    messageCache: initialMessageCache,
  } = initialSnapshotRef.current;

  const hadCachedInboxRef = useRef(initialInbox.length > 0);

  const [currentUserId] = useState<number | null>(() => initialUserId);

  const [connected, setConnected] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>(() => initialInbox);
  const [inboxReady, setInboxReady] = useState(() => initialInbox.length > 0);
  const [activeConversation, setActiveConversation] = useState<Conversation | null>(() => {
    if (!initialActiveId) return null;
    return initialInbox.find(item => item.id === initialActiveId) ?? null;
  });
  const [activeConversationId, setActiveConversationIdInternal] = useState<number | null>(
    () => initialActiveId
  );
  const [messages, setMessages] = useState<InternalMessage[]>(() => {
    if (!initialActiveId) return [];
    return initialMessageCache.get(initialActiveId) ?? [];
  });
  const [typingUserIds, setTypingUserIds] = useState<number[]>([]);
  const [presenceByUserId, setPresenceByUserId] = useState<Record<number, PresenceInfo>>({});
  const [jumpTarget, setJumpTarget] = useState<JumpTarget | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const socketHandleRef = useRef<NexusSocketHandle | null>(null);
  const activeConversationRef = useRef<number | null>(initialActiveId);
  const loadRequestRef = useRef(0);
  const messagesCacheRef = useRef<Map<number, InternalMessage[]>>(initialMessageCache);
  const localConversationsRef = useRef<Map<number, Conversation>>(new Map());
  const markReadTimer = useRef<number | null>(null);
  const tempMessageCounter = useRef(0);
  const typingActiveRef = useRef(false);
  const hasRestoredInboxRef = useRef(false);
  const persistCacheTimer = useRef<number | null>(null);
  const persistInboxTimer = useRef<number | null>(null);
  const socketHandlersRef = useRef<{
    applyPresence: (userId: number, presence: PresenceInfo) => void;
    bumpConversationActivity: (conversationId: number, patch: Partial<Conversation>) => void;
    refreshConversations: () => Promise<void>;
  } | null>(null);
  const applyIncomingMessageRef = useRef<(message: InternalMessage) => void>(() => {});
  const bumpConversationActivityRef =
    useRef<(conversationId: number, patch: Partial<Conversation>) => void>(() => {});

  const setActiveConversationId = useCallback(
    (id: number | null) => {
      setActiveConversationIdInternal(id);
      writeStoredActiveConversationId(currentUserId, id);
      activeConversationRef.current = id;
    },
    [currentUserId]
  );

  useEffect(() => {
    activeConversationRef.current = activeConversationId;
    setTypingUserIds([]);
    typingActiveRef.current = false;
  }, [activeConversationId]);

  const applyPresence = useCallback((userId: number, presence: PresenceInfo) => {
    setPresenceByUserId(prev => ({ ...prev, [userId]: presence }));
  }, []);

  const ingestConversations = useCallback((items: Conversation[]) => {
    const normalized = parseConversationsResponse({ conversations: items });

    normalized.forEach(item => localConversationsRef.current.delete(item.id));

    const presenceMap: Record<number, PresenceInfo> = {};
    normalized.forEach(conversation => {
      conversation.participants.forEach(participant => {
        presenceMap[participant.admin_id] = {
          status: participant.status ?? 'offline',
          last_seen_at: participant.last_seen_at,
          last_active_at: participant.last_active_at,
          away_duration_seconds: participant.away_duration_seconds,
        };
      });
    });
    setPresenceByUserId(prev => ({ ...prev, ...presenceMap }));
    setConversations(prev =>
      mergeConversationLists(prev, normalized, localConversationsRef.current)
    );
  }, []);

  const bumpConversationActivity = useCallback(
    (conversationId: number, patch: Partial<Conversation>) => {
      setConversations(prev => {
        const index = prev.findIndex(item => item.id === conversationId);
        if (index === -1) return prev;
        const updated = normalizeConversation({ ...prev[index], ...patch });
        return putConversationFirst(prev, updated);
      });
    },
    []
  );
  bumpConversationActivityRef.current = bumpConversationActivity;

  const applyIncomingMessage = useCallback((message: InternalMessage) => {
    if (!message?.id || !message.conversation_id) return;

    const conversationId = message.conversation_id;
    const cached = messagesCacheRef.current.get(conversationId) ?? [];
    messagesCacheRef.current.set(conversationId, upsertMessage(cached, message));

    if (conversationId === activeConversationRef.current) {
      setMessages(prev => upsertMessage(prev, message));
    }

    const selfId = getCurrentUserId();
    if (selfId === null || message.sender_id !== selfId) {
      bumpConversationActivityRef.current(conversationId, {
        last_message_at: message.created_at,
        last_message_snippet:
          message.content_type === 'audio'
            ? 'Voice note'
            : (message.content || '').slice(0, 120) || null,
      });
    }
  }, []);

  useEffect(() => {
    applyIncomingMessageRef.current = applyIncomingMessage;
  }, [applyIncomingMessage]);

  const refreshConversations = useCallback(async () => {
    try {
      const data = await apiFetch('chat/conversations');
      const items = parseConversationsResponse(data);
      ingestConversations(items);

      if (!hasRestoredInboxRef.current) {
        hasRestoredInboxRef.current = true;
        if (items.length === 0) {
          if (!hadCachedInboxRef.current) {
            setActiveConversation(null);
            setActiveConversationId(null);
            setMessages([]);
          }
          return;
        }

        const storedId = readStoredActiveConversationId(currentUserId);
        let target = storedId ? items.find(item => item.id === storedId) : undefined;
        if (!target) {
          target = sortConversations([...items])[0];
        }
        if (!target) return;

        const cached = messagesCacheRef.current.get(target.id);
        setActiveConversation(target);
        setActiveConversationId(target.id);
        if (cached?.length) setMessages(cached);
        return;
      }

      if (activeConversationRef.current) {
        const refreshed = items.find(item => item.id === activeConversationRef.current);
        if (refreshed) setActiveConversation(refreshed);
      }
    } finally {
      setInboxReady(true);
    }
  }, [currentUserId, ingestConversations, setActiveConversationId]);

  useEffect(() => {
    socketHandlersRef.current = {
      applyPresence,
      bumpConversationActivity,
      refreshConversations,
    };
  }, [applyPresence, bumpConversationActivity, refreshConversations]);

  const loadConversation = useCallback(async (conversationId: number) => {
    const requestId = ++loadRequestRef.current;
    const stored = readCachedConversationMessages(conversationId, currentUserId) as InternalMessage[];
    const cached = mergeMessageLists(
      messagesCacheRef.current.get(conversationId) ?? [],
      stored
    );

    if (cached.length) {
      messagesCacheRef.current.set(conversationId, cached);
    }

    if (activeConversationRef.current === conversationId) {
      setMessages(prev =>
        prev.length > 0 && prev[0]?.conversation_id === conversationId
          ? mergeMessageLists(prev, cached)
          : cached
      );
    }

    try {
      const data = await apiFetch(`chat/conversations/${conversationId}/messages`);
      if (
        loadRequestRef.current !== requestId ||
        activeConversationRef.current !== conversationId
      ) {
        return;
      }

      const fetched = ((data as { messages: InternalMessage[] }).messages ?? []).filter(
        message => message.conversation_id === conversationId
      );
      const merged = mergeMessageLists(cached, fetched);
      messagesCacheRef.current.set(conversationId, merged);
      setMessages(merged);

      void apiFetch(`chat/conversations/${conversationId}/read`, {
        method: 'POST',
        body: JSON.stringify({}),
      });
    } catch {
      if (
        loadRequestRef.current === requestId &&
        activeConversationRef.current === conversationId &&
        cached.length
      ) {
        setMessages(cached);
      } else if (
        loadRequestRef.current === requestId &&
        activeConversationRef.current === conversationId
      ) {
        setMessages([]);
      }
    }
  }, [currentUserId]);

  const getConversationPreview = useCallback((conversation: Conversation) => {
    if (conversation.last_message_snippet) return conversation.last_message_snippet;
    const fromCache = previewFromMessages(messagesCacheRef.current.get(conversation.id));
    if (fromCache) return fromCache;
    return 'Start a conversation';
  }, []);

  const selectConversation = useCallback((conversation: Conversation) => {
    const opened = normalizeConversation(conversation, {
      opened_at: Date.now(),
    });
    loadRequestRef.current += 1;
    const cached = messagesCacheRef.current.get(opened.id);
    setMessages(cached ?? []);
    setConversations(prev => putConversationFirst(prev, opened));
    setActiveConversation(opened);
    setActiveConversationId(opened.id);
  }, [setActiveConversationId]);

  const jumpToSearchResult = useCallback(
    (conversationId: number, messageId: number, query: string) => {
      const trimmedQuery = query.trim();
      const match = conversations.find(item => item.id === conversationId);
      if (match) {
        selectConversation(match);
      } else {
        setActiveConversationId(conversationId);
      }
      setJumpTarget({
        messageId,
        conversationId,
        query: trimmedQuery,
      });
    },
    [conversations, selectConversation, setActiveConversationId]
  );

  const clearJumpTarget = useCallback(() => setJumpTarget(null), []);

  const getOrCreateDirect = useCallback(
    async (adminId: number) => {
      const raw = await apiFetch('chat/conversations/direct', {
        method: 'POST',
        body: JSON.stringify({ admin_id: Number(adminId) }),
      });

      const conversation = normalizeConversation(parseConversationResponse(raw), {
        opened_at: Date.now(),
      });

      if (!Number.isFinite(conversation.id)) {
        throw new Error('Could not start conversation. Please try again.');
      }

      setPresenceByUserId(prev => {
        const next = { ...prev };
        conversation.participants.forEach(participant => {
          next[participant.admin_id] = {
            status: participant.status ?? 'offline',
            last_seen_at: participant.last_seen_at,
            last_active_at: participant.last_active_at,
            away_duration_seconds: participant.away_duration_seconds,
          };
        });
        return next;
      });

      setConversations(prev => putConversationFirst(prev, conversation));
      loadRequestRef.current += 1;
      const cached = messagesCacheRef.current.get(conversation.id);
      setMessages(cached ?? []);
      setActiveConversation(conversation);
      setActiveConversationId(conversation.id);

      void refreshConversations();

      return conversation;
    },
    [refreshConversations, setActiveConversationId]
  );

  const sendTextMessage = useCallback(
    (content: string, replyToMessageId?: number | null) => {
      const conversationId = activeConversationRef.current;
      const trimmed = content.trim();
      if (!conversationId || !trimmed || currentUserId == null) return;

      const replyTarget =
        replyToMessageId != null
          ? messagesCacheRef.current
              .get(conversationId)
              ?.find(item => item.id === replyToMessageId) ?? null
          : null;

      const tempId = -(Date.now() + tempMessageCounter.current++);
      const optimistic: InternalMessage = {
        id: tempId,
        conversation_id: conversationId,
        sender_id: currentUserId,
        sender_name: 'You',
        content: trimmed,
        content_type: 'text',
        reply_to_message_id: replyToMessageId ?? null,
        reply_to: replyTarget
          ? {
              id: replyTarget.id,
              sender_id: replyTarget.sender_id,
              sender_name: replyTarget.sender_name,
              content:
                replyTarget.content_type === 'audio'
                  ? 'Voice note'
                  : replyTarget.content,
              content_type: replyTarget.content_type,
            }
          : null,
        created_at: new Date().toISOString(),
        pending: true,
        reactions: [],
      };
      setMessages(prev => [...prev, optimistic]);
      bumpConversationActivity(conversationId, {
        last_message_at: optimistic.created_at,
        last_message_snippet: trimmed.slice(0, 120) || null,
      });

      void (async () => {
        try {
          const message = (await apiFetch(`chat/conversations/${conversationId}/messages`, {
            method: 'POST',
            body: JSON.stringify({
              content: trimmed,
              reply_to_message_id: replyToMessageId ?? null,
            }),
          })) as InternalMessage;
          setMessages(prev => replaceTempMessage(prev, tempId, message));
          bumpConversationActivity(conversationId, {
            last_message_at: message.created_at,
            last_message_snippet: (message.content || '').slice(0, 120) || null,
          });
        } catch (error) {
          setMessages(prev => prev.filter(item => item.id !== tempId));
          setSendError(formatSendError(error));
          void refreshConversations();
        }
      })();
    },
    [currentUserId, bumpConversationActivity, refreshConversations]
  );

  const toggleMessageReaction = useCallback(async (messageId: number, emoji: string) => {
    const conversationId = activeConversationRef.current;
    if (!conversationId || messageId <= 0) return;

    try {
      const updated = (await apiFetch(
        `chat/conversations/${conversationId}/messages/${messageId}/reactions`,
        {
          method: 'POST',
          body: JSON.stringify({ emoji }),
        }
      )) as InternalMessage;

      setMessages(prev => upsertMessage(prev, updated));
      const cached = messagesCacheRef.current.get(conversationId) ?? [];
      messagesCacheRef.current.set(
        conversationId,
        upsertMessage(cached, updated)
      );
    } catch (error) {
      setSendError(formatSendError(error));
    }
  }, []);

  const sendVoiceMessage = useCallback(
    async (blob: Blob) => {
      const conversationId = activeConversationRef.current;
      if (!conversationId || currentUserId == null) return;

      const tempId = -(Date.now() + tempMessageCounter.current++);
      const optimistic: InternalMessage = {
        id: tempId,
        conversation_id: conversationId,
        sender_id: currentUserId,
        sender_name: 'You',
        content: 'Voice note',
        content_type: 'audio',
        created_at: new Date().toISOString(),
        pending: true,
      };
      setMessages(prev => [...prev, optimistic]);
      bumpConversationActivity(conversationId, {
        last_message_at: optimistic.created_at,
        last_message_snippet: 'Voice note',
      });

      try {
        const formData = new FormData();
        formData.append('file', blob, 'voice-note.webm');
        const message = (await apiUpload(
          `chat/conversations/${conversationId}/voice`,
          formData
        )) as InternalMessage;
        setMessages(prev => replaceTempMessage(prev, tempId, message));
        bumpConversationActivity(conversationId, {
          last_message_at: message.created_at,
          last_message_snippet: 'Voice note',
        });
      } catch {
        setMessages(prev => prev.filter(item => item.id !== tempId));
      }
    },
    [currentUserId, bumpConversationActivity]
  );

  const markRead = useCallback(() => {
    const conversationId = activeConversationRef.current;
    if (!conversationId) return;
    if (markReadTimer.current) window.clearTimeout(markReadTimer.current);
    markReadTimer.current = window.setTimeout(() => {
      void apiFetch(`chat/conversations/${conversationId}/read`, {
        method: 'POST',
        body: JSON.stringify({}),
      });
    }, 800);
  }, []);

  const sendTyping = useCallback((isTyping: boolean) => {
    const conversationId = activeConversationRef.current;
    if (!conversationId) return;
    if (isTyping === typingActiveRef.current) return;
    typingActiveRef.current = isTyping;
    void apiFetch('chat/messaging/typing', {
      method: 'POST',
      body: JSON.stringify({ conversation_id: conversationId, is_typing: isTyping }),
    });
  }, []);

  const searchAdmins = useCallback(async (query: string) => {
    const data = await apiFetch(`chat/admins/search?q=${encodeURIComponent(query)}`);
    const admins = (data as { admins: AdminSearchResult[] }).admins ?? [];
    admins.forEach(admin => {
      applyPresence(admin.id, {
        status: admin.status ?? 'offline',
        last_seen_at: admin.last_seen_at,
        last_active_at: admin.last_active_at,
        away_duration_seconds: admin.away_duration_seconds,
      });
    });
    return admins;
  }, [applyPresence]);

  const addParticipant = useCallback(
    async (adminId: number) => {
      if (!activeConversationId) return;
      const updated = (await apiFetch(`chat/conversations/${activeConversationId}/participants`, {
        method: 'POST',
        body: JSON.stringify({ admin_id: adminId }),
      })) as Conversation;
      setConversations(prev => upsertConversation(prev, updated));
      setActiveConversation(updated);
    },
    [activeConversationId]
  );

  const removeParticipant = useCallback(
    async (adminId: number) => {
      if (!activeConversationId) return;
      const updated = (await apiFetch(
        `chat/conversations/${activeConversationId}/participants/${adminId}`,
        { method: 'DELETE' }
      )) as Conversation;
      setConversations(prev => upsertConversation(prev, updated));
      setActiveConversation(updated);
    },
    [activeConversationId]
  );

  const connectSocket = useCallback(() => {
    socketHandleRef.current?.close();
    socketHandleRef.current = connectNexusWebSocket({
      onOpen: () => {
        setConnected(true);
        socketHandleRef.current?.send({ type: 'ping' });
      },
      onClose: () => setConnected(false),
      onMessage: event => {
        const handlers = socketHandlersRef.current;
        try {
          const payload = JSON.parse(event.data);
          const type = payload.type as string;
          const data = payload.data ?? payload;
          const selfId = getCurrentUserId();

          if (type === 'connection.ready' || type === 'presence.online' || type === 'presence.offline') {
            return;
          }

          if (type === 'presence.updated') {
            const userId = Number(data.user_id);
            handlers?.applyPresence(userId, {
              status: data.status ?? 'offline',
              last_seen_at: data.last_seen_at,
              last_active_at: data.last_active_at,
              away_duration_seconds: data.away_duration_seconds,
            });
            return;
          }

          if (type === 'messaging.message') {
            applyIncomingMessageRef.current(data as InternalMessage);
            return;
          }

          if (type === 'messaging.typing' && data.conversation_id === activeConversationRef.current) {
            const userId = Number(data.user_id);
            if (selfId !== null && userId === selfId) return;
            setTypingUserIds(prev => {
              if (!data.is_typing) return prev.filter(id => id !== userId);
              return prev.includes(userId) ? prev : [...prev, userId];
            });
            return;
          }

          if (type === 'messaging.reaction') {
            const message = data as InternalMessage;
            const conversationId = message.conversation_id;
            const cached = messagesCacheRef.current.get(conversationId) ?? [];
            messagesCacheRef.current.set(conversationId, upsertMessage(cached, message));
            if (conversationId === activeConversationRef.current) {
              setMessages(prev => upsertMessage(prev, message));
            }
            return;
          }

          if (type === 'messaging.read') {
            return;
          }
        } catch {
          // ignore malformed frames
        }
      },
    });
  }, []);

  useEffect(() => {
    void refreshConversations();
  }, [refreshConversations]);

  useEffect(() => {
    if (!getStoredToken()) return;
    connectSocket();
    return () => {
      if (markReadTimer.current) window.clearTimeout(markReadTimer.current);
      socketHandleRef.current?.close();
      socketHandleRef.current = null;
    };
    // Mount once — socket handlers read latest callbacks via refs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const onIncomingMessage = (event: Event) => {
      const detail = (event as CustomEvent<{ message?: InternalMessage }>).detail;
      if (!detail?.message) return;
      applyIncomingMessageRef.current(detail.message as InternalMessage);
    };

    window.addEventListener(INCOMING_MESSAGE_EVENT, onIncomingMessage);
    return () => window.removeEventListener(INCOMING_MESSAGE_EVENT, onIncomingMessage);
  }, []);

  useEffect(() => {
    if (!activeConversationId) return;
    messagesCacheRef.current.set(activeConversationId, messages);
    if (!currentUserId) return;
    if (persistCacheTimer.current) window.clearTimeout(persistCacheTimer.current);
    persistCacheTimer.current = window.setTimeout(() => {
      persistMessageCache(currentUserId, messagesCacheRef.current);
    }, 400);
    return () => {
      if (persistCacheTimer.current) window.clearTimeout(persistCacheTimer.current);
    };
  }, [messages, activeConversationId, currentUserId]);

  useEffect(() => {
    if (!currentUserId || conversations.length === 0) return;
    if (persistInboxTimer.current) window.clearTimeout(persistInboxTimer.current);
    persistInboxTimer.current = window.setTimeout(() => {
      persistInbox(currentUserId, conversations);
    }, 400);
    return () => {
      if (persistInboxTimer.current) window.clearTimeout(persistInboxTimer.current);
    };
  }, [conversations, currentUserId]);

  useEffect(() => {
    if (activeConversationId) {
      void loadConversation(activeConversationId);
    } else if (!initialActiveId) {
      setMessages([]);
      setActiveConversation(null);
    }
  }, [activeConversationId, loadConversation, initialActiveId]);

  const sortedInbox = useMemo(() => {
    let list = [...conversations];
    if (
      activeConversation &&
      Number.isFinite(activeConversation.id) &&
      !list.some(item => item.id === activeConversation.id)
    ) {
      list = putConversationFirst(list, activeConversation);
    }
    return sortConversations(list);
  }, [conversations, activeConversation]);

  const clearSendError = useCallback(() => setSendError(null), []);

  const value = useMemo<MessagingHubState>(
    () => ({
      connected,
      conversations,
      sortedInbox,
      activeConversation,
      activeConversationId,
      messages,
      typingUserIds,
      presenceByUserId,
      jumpTarget,
      currentUserId,
      setActiveConversationId,
      selectConversation,
      jumpToSearchResult,
      clearJumpTarget,
      refreshConversations,
      getOrCreateDirect,
      sendTextMessage,
      sendVoiceMessage,
      toggleMessageReaction,
      markRead,
      sendTyping,
      searchAdmins,
      addParticipant,
      removeParticipant,
      sendError,
      clearSendError,
      inboxReady,
      getConversationPreview,
    }),
    [
      connected,
      conversations,
      sortedInbox,
      activeConversation,
      activeConversationId,
      messages,
      typingUserIds,
      presenceByUserId,
      jumpTarget,
      currentUserId,
      inboxReady,
      sendError,
      clearSendError,
      getConversationPreview,
      selectConversation,
      jumpToSearchResult,
      clearJumpTarget,
      refreshConversations,
      getOrCreateDirect,
      sendTextMessage,
      sendVoiceMessage,
      toggleMessageReaction,
      markRead,
      sendTyping,
      searchAdmins,
      addParticipant,
      removeParticipant,
    ]
  );

  return <MessagingHubContext.Provider value={value}>{children}</MessagingHubContext.Provider>;
};

export const useMessagingHub = (): MessagingHubState => {
  const context = useContext(MessagingHubContext);
  if (!context) {
    throw new Error('useMessagingHub must be used within MessagingHubProvider');
  }
  return context;
};

export const getOtherParticipant = (
  conversation: Conversation | null,
  currentUserId: number | null
): ConversationParticipant | null => {
  if (!conversation || currentUserId == null) return null;
  return conversation.participants.find(participant => participant.admin_id !== currentUserId) ?? null;
};
