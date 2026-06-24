import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';
import { apiFetch } from '../utils/api';

export interface MessageToastPayload {
  id: string;
  senderName: string;
  snippet: string;
  conversationId: number;
  messageId: number;
}

interface NexusSessionContextValue {
  unreadMessageCount: number;
  setUnreadMessageCount: React.Dispatch<React.SetStateAction<number>>;
  refreshUnreadMessageCount: () => Promise<void>;
  messagingHubPulse: boolean;
  setMessagingHubPulse: React.Dispatch<React.SetStateAction<boolean>>;
  activeToast: MessageToastPayload | null;
  showMessageToast: (toast: Omit<MessageToastPayload, 'id'>) => void;
  dismissMessageToast: () => void;
}

const NexusSessionContext = createContext<NexusSessionContextValue | null>(null);

export const NexusSessionProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [unreadMessageCount, setUnreadMessageCount] = useState(0);
  const [messagingHubPulse, setMessagingHubPulse] = useState(false);
  const [activeToast, setActiveToast] = useState<MessageToastPayload | null>(null);

  const refreshUnreadMessageCount = useCallback(async () => {
    try {
      const data = await apiFetch('chat/conversations');
      const conversations =
        (data as { conversations?: Array<{ unread_count?: number }> }).conversations ?? [];
      const total = conversations.reduce(
        (sum, item) => sum + Number(item.unread_count ?? 0),
        0
      );
      setUnreadMessageCount(total);
      setMessagingHubPulse(total > 0);
    } catch {
      // User may not have messaging hub access.
    }
  }, []);

  const showMessageToast = useCallback((toast: Omit<MessageToastPayload, 'id'>) => {
    setActiveToast({
      ...toast,
      id: `${toast.messageId}-${Date.now()}`,
    });
  }, []);

  const dismissMessageToast = useCallback(() => {
    setActiveToast(null);
  }, []);

  const value = useMemo(
    () => ({
      unreadMessageCount,
      setUnreadMessageCount,
      refreshUnreadMessageCount,
      messagingHubPulse,
      setMessagingHubPulse,
      activeToast,
      showMessageToast,
      dismissMessageToast,
    }),
    [
      unreadMessageCount,
      refreshUnreadMessageCount,
      messagingHubPulse,
      activeToast,
      showMessageToast,
      dismissMessageToast,
    ]
  );

  return <NexusSessionContext.Provider value={value}>{children}</NexusSessionContext.Provider>;
};

export const useNexusSession = (): NexusSessionContextValue => {
  const context = useContext(NexusSessionContext);
  if (!context) {
    throw new Error('useNexusSession must be used within NexusSessionProvider');
  }
  return context;
};
