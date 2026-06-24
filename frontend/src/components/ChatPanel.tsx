import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Mic, Send, UserMinus, UserPlus, X } from 'lucide-react';
import { getStoredToken, resolveBaseUrl } from '../utils/api';
import MessageBody from '../utils/messageBody';
import { formatMessageTime, shouldShowMessageTimestamp } from '../utils/chatTimestamps';
import HeadlessScrollArea, { HeadlessScrollAreaHandle } from './HeadlessScrollArea';
import ChatHistorySearchBar from './ChatHistorySearchBar';
import ChatMessageInput from './ChatMessageInput';
import DirectionalMessageRow from './DirectionalMessageRow';
import EmotePicker from './EmotePicker';
import MessageContextMenu, { MessageContextMenuState } from './MessageContextMenu';
import PinnedMessageBar from './PinnedMessageBar';
import PresenceIndicator from './PresenceIndicator';
import { useChat, useChatHistorySearch } from '../hooks/useChat';
import { useHighlight } from '../hooks/useHighlight';
import {
  AdminSearchResult,
  getOtherParticipant,
  InternalMessage,
  useMessagingHub,
} from '../hooks/useMessagingHub';
import {
  hydratePinnedMessages,
  persistPinnedMessages,
  PinnedMessageSnapshot,
  snapshotFromMessage,
} from '../utils/chatPins';

const ChatPanel: React.FC = () => {
  const {
    activeConversation,
    activeConversationId,
    sortedInbox,
    currentUserId,
    messages,
    typingUserIds,
    sendTextMessage,
    sendVoiceMessage,
    toggleMessageReaction,
    sendTyping,
    markRead,
    addParticipant,
    removeParticipant,
    searchAdmins,
    sendError,
    clearSendError,
    presenceByUserId,
    jumpTarget,
    clearJumpTarget,
    jumpToSearchResult,
  } = useMessagingHub();

  const { chatMaxChars, loading: configLoading, overLimit } = useChat();
  const {
    query: historyQuery,
    setQuery: setHistoryQuery,
    results: historyResults,
    loading: historyLoading,
    error: historyError,
    recentSearches,
    showRecent,
    setShowRecent,
    recordRecentSearch,
    resultIndex,
    setResultIndex,
  } = useChatHistorySearch();
  const { highlightQuery, bubbleHighlightClassName } = useHighlight(
    historyQuery.trim() || jumpTarget?.query || null
  );
  const [draft, setDraft] = useState('');
  const [replyToMessage, setReplyToMessage] = useState<InternalMessage | null>(null);
  const [messageContextMenu, setMessageContextMenu] = useState<MessageContextMenuState | null>(null);
  const [pinnedByConversation, setPinnedByConversation] = useState<
    Record<number, PinnedMessageSnapshot>
  >(() => hydratePinnedMessages(currentUserId));
  const [recording, setRecording] = useState(false);
  const [groupAdminQuery, setGroupAdminQuery] = useState('');
  const [groupAdminResults, setGroupAdminResults] = useState<AdminSearchResult[]>([]);
  const [audioUrls, setAudioUrls] = useState<Record<number, string>>({});
  const scrollAreaRef = useRef<HeadlessScrollAreaHandle | null>(null);
  const prevMessageCountRef = useRef(0);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const typingTimer = useRef<number | null>(null);
  const holdTimer = useRef<number | null>(null);

  const panelConversation = useMemo(() => {
    if (activeConversation) return activeConversation;
    if (activeConversationId == null) return null;
    return sortedInbox.find(item => item.id === activeConversationId) ?? null;
  }, [activeConversation, activeConversationId, sortedInbox]);

  const conversationSearchResults = useMemo(() => {
    if (!panelConversation) return [];
    return historyResults.filter(result => result.conversation_id === panelConversation.id);
  }, [historyResults, panelConversation]);

  const lastJumpRef = useRef<string | null>(null);

  const safeMatchIndex =
    conversationSearchResults.length > 0
      ? Math.min(resultIndex, conversationSearchResults.length - 1)
      : 0;

  const handlePreviousMatch = useCallback(() => {
    setResultIndex(index => Math.max(0, index - 1));
  }, [setResultIndex]);

  const handleNextMatch = useCallback(() => {
    setResultIndex(index =>
      Math.min(Math.max(conversationSearchResults.length - 1, 0), index + 1)
    );
  }, [conversationSearchResults.length, setResultIndex]);

  const otherParticipant = getOtherParticipant(panelConversation, currentUserId);
  const headerPresence = otherParticipant
    ? {
        status: otherParticipant.status ?? 'offline',
        last_seen_at: otherParticipant.last_seen_at,
        last_active_at: otherParticipant.last_active_at,
        away_duration_seconds: otherParticipant.away_duration_seconds,
      }
    : null;

  const getSenderPresence = useCallback(
    (senderId: number) => {
      const live = presenceByUserId[senderId];
      if (live) return live;
      const participant = panelConversation?.participants.find(
        item => item.admin_id === senderId
      );
      if (!participant) return { status: 'offline' as const };
      return {
        status: participant.status ?? 'offline',
        last_seen_at: participant.last_seen_at,
        last_active_at: participant.last_active_at,
        away_duration_seconds: participant.away_duration_seconds,
      };
    },
    [presenceByUserId, panelConversation?.participants]
  );

  useEffect(() => {
    setAudioUrls({});
    setDraft('');
    setReplyToMessage(null);
    setMessageContextMenu(null);
    prevMessageCountRef.current = 0;
  }, [panelConversation?.id]);

  useEffect(() => {
    const count = messages.length;
    const previous = prevMessageCountRef.current;
    if (count === previous) return;
    prevMessageCountRef.current = count;

    if (jumpTarget && activeConversationId === jumpTarget.conversationId) {
      return;
    }

    requestAnimationFrame(() => {
      scrollAreaRef.current?.scrollToBottom('auto');
    });

    const last = messages[count - 1];
    if (last && last.sender_id !== currentUserId) {
      markRead();
    }
  }, [messages, markRead, currentUserId, jumpTarget, activeConversationId]);

  useEffect(() => {
    const token = getStoredToken();
    if (!token) return;

    messages
      .filter(message => message.content_type === 'audio' && message.media_url && !message.pending)
      .forEach(async message => {
        if (audioUrls[message.id]) return;
        const base = resolveBaseUrl().replace(/\/api\/v1\/?$/, '');
        const url = message.media_url!.startsWith('http')
          ? message.media_url!
          : `${base}${message.media_url}`;
        try {
          const response = await fetch(url, {
            headers: { Authorization: `Bearer ${token}`, 'ngrok-skip-browser-warning': 'true' },
          });
          if (!response.ok) return;
          const blob = await response.blob();
          setAudioUrls(prev => ({ ...prev, [message.id]: URL.createObjectURL(blob) }));
        } catch {
          // ignore
        }
      });
  }, [messages, audioUrls]);

  useEffect(() => {
    if (!groupAdminQuery.trim()) {
      setGroupAdminResults([]);
      return;
    }
    const timer = window.setTimeout(() => {
      void searchAdmins(groupAdminQuery).then(setGroupAdminResults);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [groupAdminQuery, searchAdmins]);

  const closeContextMenu = useCallback(() => setMessageContextMenu(null), []);

  const pinnedMessage =
    panelConversation?.id != null ? pinnedByConversation[panelConversation.id] ?? null : null;

  const pinMessage = useCallback(
    (message: InternalMessage) => {
      if (message.id <= 0 || panelConversation?.id == null) return;
      const snapshot = snapshotFromMessage(message);
      setPinnedByConversation(prev => {
        const next = { ...prev, [panelConversation.id]: snapshot };
        persistPinnedMessages(currentUserId, next);
        return next;
      });
    },
    [currentUserId, panelConversation?.id]
  );

  const unpinMessage = useCallback(() => {
    if (panelConversation?.id == null) return;
    setPinnedByConversation(prev => {
      const next = { ...prev };
      delete next[panelConversation.id];
      persistPinnedMessages(currentUserId, next);
      return next;
    });
  }, [currentUserId, panelConversation?.id]);

  const jumpToPinnedMessage = useCallback(() => {
    if (!pinnedMessage) return;
    scrollAreaRef.current?.scrollToSelector(
      `[data-message-id="${pinnedMessage.message_id}"]`
    );
  }, [pinnedMessage]);

  useEffect(() => {
    if (!historyQuery.trim()) {
      clearJumpTarget();
      lastJumpRef.current = null;
      return;
    }

    if (conversationSearchResults.length === 0) {
      clearJumpTarget();
      return;
    }

    const safeIndex = safeMatchIndex;
    const result = conversationSearchResults[safeIndex];
    if (!result) return;

    const jumpKey = `${result.message_id}:${historyQuery.trim()}:${safeIndex}`;
    if (lastJumpRef.current === jumpKey) return;
    lastJumpRef.current = jumpKey;

    jumpToSearchResult(result.conversation_id, result.message_id, historyQuery);
    recordRecentSearch(historyQuery);
  }, [
    historyQuery,
    conversationSearchResults,
    safeMatchIndex,
    jumpToSearchResult,
    clearJumpTarget,
    recordRecentSearch,
  ]);

  useEffect(() => {
    if (!jumpTarget || activeConversationId !== jumpTarget.conversationId) return;
    if (messages.length === 0) return;

    const frame = requestAnimationFrame(() => {
      scrollAreaRef.current?.scrollToSelector(
        `[data-message-id="${jumpTarget.messageId}"]`,
        'smooth'
      );
    });

    return () => cancelAnimationFrame(frame);
  }, [jumpTarget, activeConversationId, messages]);

  useEffect(() => {
    setPinnedByConversation(hydratePinnedMessages(currentUserId));
  }, [currentUserId]);

  const replyPreview = useMemo(() => {
    if (!replyToMessage) return null;
    return {
      senderLabel:
        replyToMessage.sender_id === currentUserId
          ? 'You'
          : replyToMessage.sender_name,
      content:
        replyToMessage.content_type === 'audio'
          ? 'Voice note'
          : replyToMessage.content,
    };
  }, [replyToMessage, currentUserId]);

  const handleMessageContextMenu = (event: React.MouseEvent, message: InternalMessage) => {
    event.preventDefault();
    setMessageContextMenu({ x: event.clientX, y: event.clientY, message });
  };

  const handleSend = () => {
    const text = draft.trim();
    if (!text || configLoading || chatMaxChars <= 0 || overLimit(draft)) return;
    clearSendError();
    const replyId = replyToMessage?.id ?? null;
    setDraft('');
    setReplyToMessage(null);
    if (typingTimer.current) window.clearTimeout(typingTimer.current);
    sendTyping(false);
    sendTextMessage(text, replyId);
  };

  const handleDraftChange = (value: string) => {
    if (chatMaxChars > 0 && value.length > chatMaxChars) return;
    if (sendError) clearSendError();
    setDraft(value);
    if (!value.trim()) {
      sendTyping(false);
      return;
    }
    if (typingTimer.current) window.clearTimeout(typingTimer.current);
    typingTimer.current = window.setTimeout(() => sendTyping(true), 350);
  };

  const insertEmote = (emote: string) => {
    if (configLoading || chatMaxChars <= 0) return;
    const next = draft + emote;
    if (next.length > chatMaxChars) return;
    if (sendError) clearSendError();
    setDraft(next);
  };

  const startRecording = async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const recorder = new MediaRecorder(stream);
    chunksRef.current = [];
    recorder.ondataavailable = event => {
      if (event.data.size > 0) chunksRef.current.push(event.data);
    };
    recorder.onstop = async () => {
      stream.getTracks().forEach(track => track.stop());
      const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' });
      await sendVoiceMessage(blob);
    };
    recorderRef.current = recorder;
    recorder.start();
    setRecording(true);
  };

  const stopRecording = () => {
    recorderRef.current?.stop();
    setRecording(false);
  };

  if (!panelConversation && messages.length === 0) {
    return (
      <div className="flex h-full items-center justify-center rounded-xl border border-dashed border-border bg-white p-8 text-center">
        <div>
          <p className="text-lg font-semibold text-text-primary">Select a conversation</p>
          <p className="mt-2 text-sm text-text-primary/70">
            Choose a thread from your inbox or search for an admin to start chatting.
          </p>
        </div>
      </div>
    );
  }

  if (!panelConversation) {
    return (
      <div className="flex h-full items-center justify-center rounded-xl border border-dashed border-border bg-white p-8 text-center">
        <div>
          <p className="text-lg font-semibold text-text-primary">Select a conversation</p>
          <p className="mt-2 text-sm text-text-primary/70">
            Choose a thread from your inbox or search for an admin to start chatting.
          </p>
        </div>
      </div>
    );
  }

  const isGroup = panelConversation.type === 'group';
  const canSend =
    !configLoading && chatMaxChars > 0 && draft.trim().length > 0 && !overLimit(draft);

  return (
    <div
      key={panelConversation.id}
      className="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-border bg-white shadow-sm"
    >
      <div className="border-b border-border px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <h2 className="min-w-0 flex-1 truncate text-left text-sm font-semibold text-text-primary">
            {isGroup ? panelConversation.name || panelConversation.display_name : panelConversation.display_name}
          </h2>
          {!isGroup && headerPresence && (
            <span className="shrink-0">
              <PresenceIndicator presence={headerPresence} />
            </span>
          )}
        </div>
        <p className="text-left text-xs text-text-primary/70">
          {panelConversation.participants.length} participants
          {typingUserIds.length > 0 ? ` · ${typingUserIds.length} typing` : ''}
        </p>

        {isGroup && (
          <div className="mt-3 space-y-2">
            <div className="flex flex-wrap gap-2">
              {panelConversation.participants.map(participant => (
                <span
                  key={participant.admin_id}
                  className="inline-flex items-center gap-1 rounded-full bg-incoming px-2 py-1 text-[10px] text-text-primary"
                >
                  <PresenceIndicator
                    presence={{
                      status: participant.status ?? 'offline',
                      last_seen_at: participant.last_seen_at,
                      last_active_at: participant.last_active_at,
                      away_duration_seconds: participant.away_duration_seconds,
                    }}
                  />
                  {participant.full_name}
                  <button
                    type="button"
                    onClick={() => void removeParticipant(participant.admin_id)}
                    className="text-text-primary/70 hover:text-red-500"
                    title="Remove participant"
                  >
                    <UserMinus className="h-3 w-3" />
                  </button>
                </span>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <input
                value={groupAdminQuery}
                onChange={event => setGroupAdminQuery(event.target.value)}
                placeholder="Add admin to group..."
                className="flex-1 rounded-lg border border-border px-3 py-2 text-xs text-text-primary outline-none focus:border-primary focus:ring-2 focus:ring-primary"
              />
              {groupAdminResults.slice(0, 3).map(admin => (
                <button
                  key={admin.id}
                  type="button"
                  onClick={() => {
                    void addParticipant(admin.id);
                    setGroupAdminQuery('');
                    setGroupAdminResults([]);
                  }}
                  className="inline-flex items-center gap-1 rounded-md bg-primary px-2 py-1 text-[10px] text-white"
                >
                  <UserPlus className="h-3 w-3" />
                  {admin.full_name}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="flex min-h-0 flex-1 flex-col">
        <ChatHistorySearchBar
          query={historyQuery}
          onQueryChange={setHistoryQuery}
          loading={historyLoading}
          error={historyError}
          matchCount={conversationSearchResults.length}
          matchIndex={safeMatchIndex}
          onPrevious={handlePreviousMatch}
          onNext={handleNextMatch}
          recentSearches={recentSearches}
          showRecent={showRecent}
          onFocus={() => setShowRecent(true)}
          onBlur={() => window.setTimeout(() => setShowRecent(false), 150)}
          onSelectRecent={setHistoryQuery}
        />

        {pinnedMessage && (
          <PinnedMessageBar
            pinned={pinnedMessage}
            currentUserId={currentUserId}
            onClose={unpinMessage}
            onJumpToMessage={jumpToPinnedMessage}
          />
        )}

        <HeadlessScrollArea ref={scrollAreaRef} className="chat-message-stream min-h-0 flex-1 bg-white">
          <div className="chat-message-stream-inner">
          {messages.map((message: InternalMessage, index: number) => {
          const isOutgoing = currentUserId != null && message.sender_id === currentUserId;
          const showTimestamp = shouldShowMessageTimestamp(
            messages,
            index,
            item => item.sender_id,
            item => item.created_at
          );
          const messageTime = formatMessageTime(message.created_at);
          const isJumpTarget = jumpTarget?.messageId === message.id;
          const bubbleBg = isOutgoing ? 'bg-outgoing' : 'bg-incoming';
          const bubbleTone = isJumpTarget ? bubbleHighlightClassName : '';

          return (
            <DirectionalMessageRow
              key={message.id}
              isOutgoing={isOutgoing}
              senderName={message.sender_name}
              senderPresence={!isOutgoing ? getSenderPresence(message.sender_id) : null}
              showTimestamp={showTimestamp}
              clusterGap={showTimestamp && index > 0}
              bubbleClassName={`${bubbleBg} ${bubbleTone}`.trim()}
              timestamp={messageTime}
              dataMessageId={message.id}
              onContextMenu={event => handleMessageContextMenu(event, message)}
            >
              {message.reply_to && (
                <div className="mb-1 rounded-lg border-l-4 border-primary/50 bg-white/70 px-2 py-1 text-left">
                  <p className="truncate text-[10px] font-semibold text-text-primary/80">
                    {message.reply_to.sender_id === currentUserId
                      ? 'You'
                      : message.reply_to.sender_name}
                  </p>
                  <p className="max-h-32 overflow-y-auto whitespace-pre-wrap break-words text-xs text-text-primary/70">
                    {message.reply_to.content_type === 'audio'
                      ? 'Voice note'
                      : message.reply_to.content}
                  </p>
                </div>
              )}

              {message.content_type === 'audio' && message.media_url ? (
                <audio controls className="mt-1 w-full min-w-[220px]" src={audioUrls[message.id]} />
              ) : (
                <MessageBody text={message.content} highlightQuery={highlightQuery} />
              )}

              {message.reactions && message.reactions.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-0.5">
                  {message.reactions.map(reaction => (
                    <button
                      key={reaction.emoji}
                      type="button"
                      title={`React with ${reaction.emoji}`}
                      onClick={() => {
                        if (message.id > 0) {
                          void toggleMessageReaction(message.id, reaction.emoji);
                        }
                      }}
                      className={`inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-xs transition-colors ${
                        reaction.reacted_by_me
                          ? 'bg-primary/15 ring-1 ring-primary/40'
                          : 'bg-white/60 hover:bg-white/90'
                      }`}
                    >
                      <span className="text-base leading-none">{reaction.emoji}</span>
                      {reaction.count > 1 && (
                        <span className="text-[10px] font-medium text-text-primary/80">
                          {reaction.count}
                        </span>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </DirectionalMessageRow>
          );
          })}
          </div>
        </HeadlessScrollArea>
      </div>

      <div className="shrink-0 border-t border-border bg-white p-3">
        <div
          className={`flex gap-2 ${replyToMessage ? 'flex-col sm:flex-row sm:items-end' : 'items-center'}`}
        >
          <div className={`flex items-center gap-2 ${replyToMessage ? 'shrink-0' : ''}`}>
            <button
              type="button"
              onMouseDown={() => {
                holdTimer.current = window.setTimeout(() => void startRecording(), 200);
              }}
              onMouseUp={() => {
                if (holdTimer.current) window.clearTimeout(holdTimer.current);
                if (recording) stopRecording();
              }}
              onMouseLeave={() => {
                if (holdTimer.current) window.clearTimeout(holdTimer.current);
                if (recording) stopRecording();
              }}
              onTouchStart={() => {
                holdTimer.current = window.setTimeout(() => void startRecording(), 200);
              }}
              onTouchEnd={() => {
                if (holdTimer.current) window.clearTimeout(holdTimer.current);
                if (recording) stopRecording();
              }}
              className={`rounded-lg p-2 ${recording ? 'bg-red-500 text-white' : 'bg-primary/10 text-primary'}`}
              title="Hold to record"
            >
              {recording ? <X className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
            </button>
            <EmotePicker
              onPick={insertEmote}
              disabled={configLoading || chatMaxChars <= 0}
            />
          </div>
          <ChatMessageInput
            value={draft}
            onChange={handleDraftChange}
            onKeyDown={event => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                if (canSend) handleSend();
              }
            }}
            canSend={canSend}
            chatMaxChars={chatMaxChars}
            loading={configLoading}
            replyPreview={replyPreview}
            onClearReply={() => setReplyToMessage(null)}
            className={replyToMessage ? 'w-full sm:flex-[2]' : ''}
          />
          <button
            type="button"
            onClick={handleSend}
            disabled={!canSend}
            className={`shrink-0 rounded-lg bg-primary p-2 text-white hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50 ${
              replyToMessage ? 'self-end' : ''
            }`}
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
        {sendError && <p className="mt-1 text-xs text-red-600">{sendError}</p>}
        {recording && <p className="mt-2 text-xs text-red-500">Recording… release to send</p>}
      </div>

      <MessageContextMenu
        menu={messageContextMenu}
        onClose={closeContextMenu}
        onReply={message => setReplyToMessage(message)}
        onPin={pinMessage}
        onReact={(message, emoji) => {
          if (message.id > 0) {
            void toggleMessageReaction(message.id, emoji);
          }
        }}
      />
    </div>
  );
};

export default ChatPanel;
