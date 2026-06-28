import React, { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Wifi, WifiOff } from 'lucide-react';
import ChatPanel from '../components/ChatPanel';
import ChatSidebar from '../components/ChatSidebar';
import { useNexusSession } from '../context/NexusSessionContext';
import { ChatConfigProvider } from '../hooks/useChat';
import { MessagingHubProvider, useMessagingHub } from '../hooks/useMessagingHub';

const MessagingHubHeader: React.FC = () => {
  const { connected } = useMessagingHub();

  return (
    <div className="shrink-0 rounded-xl border border-border bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Chat</h1>
          <p className="text-sm text-text-primary/70">
            Use the search bar above the chat to find messages, then use the arrows to step through
            each match.
          </p>
        </div>
        <span className="inline-flex items-center gap-1 rounded-full bg-incoming px-3 py-1 text-xs text-text-primary/70">
          {connected ? <Wifi className="h-3.5 w-3.5 text-primary" /> : <WifiOff className="h-3.5 w-3.5 text-red-500" />}
          {connected ? 'Connected' : 'Reconnecting'}
        </span>
      </div>
    </div>
  );
};

const MessagingHubLayout: React.FC = () => {
  const { selectConversation, conversations, setActiveConversationId, jumpToSearchResult } =
    useMessagingHub();
  const { refreshUnreadMessageCount } = useNexusSession();
  const [searchParams] = useSearchParams();

  useEffect(() => {
    void refreshUnreadMessageCount();
  }, [refreshUnreadMessageCount]);

  useEffect(() => {
    const conversationId = Number(
      searchParams.get('conversation_id') ?? searchParams.get('conversation')
    );
    const messageId = Number(searchParams.get('message'));
    if (!Number.isFinite(conversationId) || conversationId <= 0) return;

    const match = conversations.find(item => item.id === conversationId);
    if (match) {
      selectConversation(match);
    } else {
      setActiveConversationId(conversationId);
    }

    if (Number.isFinite(messageId) && messageId > 0) {
      jumpToSearchResult(conversationId, messageId, '');
    }
  }, [
    searchParams,
    conversations,
    selectConversation,
    setActiveConversationId,
    jumpToSearchResult,
  ]);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden bg-white">
      <MessagingHubHeader />

      <div className="grid min-h-0 flex-1 gap-4 overflow-hidden lg:grid-cols-[320px_minmax(0,1fr)]">
        <ChatSidebar onSelectConversation={selectConversation} />
        <ChatPanel />
      </div>
    </div>
  );
};

const MessagingHub: React.FC = () => (
  <ChatConfigProvider>
    <MessagingHubProvider>
      <MessagingHubLayout />
    </MessagingHubProvider>
  </ChatConfigProvider>
);

export default MessagingHub;
