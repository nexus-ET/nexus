import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { apiFetch, getCurrentUserId, getStoredToken } from '../utils/api';
import { connectNexusWebSocket, NexusSocketHandle } from '../utils/nexusWebSocket';

export interface OperationalPulse {
  pending_review: number;
  stalled_candidates: number;
  open_tasks: number;
  scheduled_sessions: number;
  awaiting_docs_reminders: number;
  security_status: string;
  security_healthy: boolean;
  security_run_id?: number | null;
  security_checked_at?: string | null;
}

export interface PipelineStage {
  key: string;
  label: string;
}

export interface PipelineCard {
  lead_id: number;
  full_name: string;
  email?: string | null;
  phone_number?: string | null;
  admission_stage: string;
  assigned_advisor_id?: number | null;
  is_stalled: boolean;
  latest_booking_id?: number | null;
  updated_at?: string | null;
}

export interface TaskItem {
  id: number;
  lead_id: number;
  booking_id?: number | null;
  title: string;
  status: string;
  candidate_name: string;
  created_at: string;
}

export interface ChatMessage {
  id: number;
  sender_user_id: number;
  sender_name: string;
  text: string;
  lead_id?: number | null;
  media_url?: string | null;
  file_name?: string | null;
  message_type: string;
  delivery_status: string;
  read_at?: string | null;
  created_at: string;
}

interface PipelineBoardState {
  stages: PipelineStage[];
  columns: Record<string, PipelineCard[]>;
}

interface NexusStateValue {
  connected: boolean;
  pulse: OperationalPulse | null;
  pipeline: PipelineBoardState | null;
  tasks: TaskItem[];
  messages: ChatMessage[];
  onlineUserIds: number[];
  typingUserIds: number[];
  selectedLeadId: number | null;
  highlightedLeadId: number | null;
  highlightedCandidateName: string | null;
  setSelectedLeadId: (leadId: number | null) => void;
  highlightLeadInChat: (leadId: number, candidateName?: string) => void;
  refreshPulse: () => Promise<void>;
  refreshPipeline: () => Promise<void>;
  refreshTasks: () => Promise<void>;
  refreshMessages: () => Promise<void>;
  sendMessage: (text: string, leadId?: number | null) => Promise<void>;
  assignLeadToMe: (leadId: number) => Promise<void>;
  moveCandidate: (leadId: number, stage: string) => Promise<void>;
  markMessagesRead: (upToMessageId: number) => Promise<void>;
  sendTyping: (isTyping: boolean) => void;
}

const NexusStateContext = createContext<NexusStateValue | null>(null);

const upsertChatMessage = (prev: ChatMessage[], message: ChatMessage): ChatMessage[] => {
  if (!message?.id) return prev;
  if (prev.some(item => item.id === message.id)) return prev;
  return [...prev, message];
};

export const NexusStateProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [connected, setConnected] = useState(false);
  const [pulse, setPulse] = useState<OperationalPulse | null>(null);
  const [pipeline, setPipeline] = useState<PipelineBoardState | null>(null);
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [onlineUserIds, setOnlineUserIds] = useState<number[]>([]);
  const [typingUserIds, setTypingUserIds] = useState<number[]>([]);
  const [selectedLeadId, setSelectedLeadId] = useState<number | null>(null);
  const [highlightedLeadId, setHighlightedLeadId] = useState<number | null>(null);
  const [highlightedCandidateName, setHighlightedCandidateName] = useState<string | null>(null);
  const socketHandleRef = useRef<NexusSocketHandle | null>(null);
  const markReadTimer = useRef<number | null>(null);
  const socketHandlersRef = useRef<{
    refreshPipeline: () => Promise<void>;
    refreshPulse: () => Promise<void>;
    refreshTasks: () => Promise<void>;
  } | null>(null);

  const refreshPulse = useCallback(async () => {
    const data = await apiFetch('command-center/pulse');
    setPulse(data as OperationalPulse);
  }, []);

  const refreshPipeline = useCallback(async () => {
    const data = await apiFetch('command-center/pipeline');
    setPipeline(data as PipelineBoardState);
  }, []);

  const refreshTasks = useCallback(async () => {
    const data = await apiFetch('command-center/tasks');
    setTasks((data as { tasks: TaskItem[] }).tasks ?? []);
  }, []);

  const refreshMessages = useCallback(async () => {
    const data = await apiFetch('chat/messages');
    setMessages((data as { messages: ChatMessage[] }).messages ?? []);
  }, []);

  const bootstrap = useCallback(async () => {
    await Promise.all([refreshPulse(), refreshPipeline(), refreshTasks(), refreshMessages()]);
  }, [refreshMessages, refreshPipeline, refreshPulse, refreshTasks]);

  useEffect(() => {
    socketHandlersRef.current = {
      refreshPipeline,
      refreshPulse,
      refreshTasks,
    };
  }, [refreshPipeline, refreshPulse, refreshTasks]);

  const highlightLeadInChat = useCallback((leadId: number, candidateName?: string) => {
    setSelectedLeadId(leadId);
    setHighlightedLeadId(leadId);
    setHighlightedCandidateName(candidateName?.trim() || null);
    window.setTimeout(() => {
      setHighlightedLeadId(null);
      setHighlightedCandidateName(null);
    }, 4000);
  }, []);

  const connectSocket = useCallback(() => {
    socketHandleRef.current?.close();
    socketHandleRef.current = connectNexusWebSocket({
      onOpen: () => setConnected(true),
      onClose: () => setConnected(false),
      onMessage: event => {
        const handlers = socketHandlersRef.current;
        try {
          const payload = JSON.parse(event.data);
          const type = payload.type as string;
          const data = payload.data ?? payload;

          if (type === 'connection.ready') {
            setOnlineUserIds(data.online_user_ids ?? []);
            return;
          }
          if (type === 'presence.online' || type === 'presence.offline') {
            setOnlineUserIds(data.online_user_ids ?? []);
            return;
          }
          if (type === 'chat.message') {
            const message = (data.id ? data : payload) as ChatMessage;
            setMessages(prev => upsertChatMessage(prev, message));
            return;
          }
          if (type === 'chat.read') {
            setMessages(prev =>
              prev.map(item =>
                item.id <= data.up_to_message_id && item.sender_user_id !== data.reader_user_id
                  ? { ...item, delivery_status: 'read', read_at: new Date().toISOString() }
                  : item
              )
            );
            return;
          }
          if (type === 'chat.typing') {
            const userId = Number(data.user_id);
            const selfId = getCurrentUserId();
            if (selfId !== null && userId === selfId) return;
            setTypingUserIds(prev => {
              if (!data.is_typing) return prev.filter(id => id !== userId);
              return prev.includes(userId) ? prev : [...prev, userId];
            });
            return;
          }
          if (
            handlers &&
            (type === 'pipeline.updated' || type === 'lead.assigned' || type === 'tasks.updated')
          ) {
            void handlers.refreshPipeline();
            void handlers.refreshPulse();
            void handlers.refreshTasks();
          }
        } catch {
          // ignore malformed frames
        }
      },
    });
  }, []);

  useEffect(() => {
    void bootstrap();
    if (getStoredToken()) {
      connectSocket();
    }
    const pulseTimer = window.setInterval(() => void refreshPulse(), 60000);
    return () => {
      if (markReadTimer.current) window.clearTimeout(markReadTimer.current);
      window.clearInterval(pulseTimer);
      socketHandleRef.current?.close();
      socketHandleRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const sendMessage = useCallback(async (text: string, leadId?: number | null) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    const message = (await apiFetch('chat/messages', {
      method: 'POST',
      body: JSON.stringify({ text: trimmed, lead_id: leadId ?? null }),
    })) as ChatMessage;
    setMessages(prev => upsertChatMessage(prev, message));
  }, []);

  const assignLeadToMe = useCallback(
    async (leadId: number) => {
      await apiFetch('chat/assign-lead', {
        method: 'POST',
        body: JSON.stringify({ lead_id: leadId }),
      });
      await refreshPipeline();
    },
    [refreshPipeline]
  );

  const moveCandidate = useCallback(
    async (leadId: number, stage: string) => {
      await apiFetch('command-center/pipeline/move', {
        method: 'POST',
        body: JSON.stringify({ lead_id: leadId, stage }),
      });
      await refreshPipeline();
    },
    [refreshPipeline]
  );

  const markMessagesRead = useCallback((upToMessageId: number) => {
    if (markReadTimer.current) window.clearTimeout(markReadTimer.current);
    markReadTimer.current = window.setTimeout(() => {
      void apiFetch('chat/messages/read', {
        method: 'POST',
        body: JSON.stringify({ up_to_message_id: upToMessageId }),
      });
    }, 400);
  }, []);

  const sendTyping = useCallback((isTyping: boolean) => {
    void apiFetch('chat/typing', {
      method: 'POST',
      body: JSON.stringify({ is_typing: isTyping }),
    });
  }, []);

  const value = useMemo<NexusStateValue>(
    () => ({
      connected,
      pulse,
      pipeline,
      tasks,
      messages,
      onlineUserIds,
      typingUserIds,
      selectedLeadId,
      highlightedLeadId,
      highlightedCandidateName,
      setSelectedLeadId,
      highlightLeadInChat,
      refreshPulse,
      refreshPipeline,
      refreshTasks,
      refreshMessages,
      sendMessage,
      assignLeadToMe,
      moveCandidate,
      markMessagesRead,
      sendTyping,
    }),
    [
      connected,
      pulse,
      pipeline,
      tasks,
      messages,
      onlineUserIds,
      typingUserIds,
      selectedLeadId,
      highlightedLeadId,
      highlightedCandidateName,
      highlightLeadInChat,
      refreshPulse,
      refreshPipeline,
      refreshTasks,
      refreshMessages,
      sendMessage,
      assignLeadToMe,
      moveCandidate,
      markMessagesRead,
      sendTyping,
    ]
  );

  return <NexusStateContext.Provider value={value}>{children}</NexusStateContext.Provider>;
};

export const useNexusState = (): NexusStateValue => {
  const context = useContext(NexusStateContext);
  if (!context) {
    throw new Error('useNexusState must be used within NexusStateProvider');
  }
  return context;
};
