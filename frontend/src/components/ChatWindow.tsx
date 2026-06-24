import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Check, CheckCheck, Mic, Send, Square, UserPlus } from 'lucide-react';
import { apiUpload, getCurrentUserId, getStoredToken, resolveBaseUrl } from '../utils/api';
import MessageBody from '../utils/messageBody';
import { formatMessageTime, shouldShowMessageTimestamp } from '../utils/chatTimestamps';
import ChatMessageInput from './ChatMessageInput';
import DirectionalMessageRow from './DirectionalMessageRow';
import EmotePicker from './EmotePicker';
import { PresenceInfo } from './PresenceIndicator';
import { useChat } from '../hooks/useChat';
import { useHighlight } from '../hooks/useHighlight';
import { ChatMessage, useNexusState } from '../hooks/useNexusState';

interface ContextMenuState {
  x: number;
  y: number;
  message: ChatMessage;
}

const deliveryIcon = (status: string) => {
  if (status === 'read') return <CheckCheck className="h-3 w-3 text-primary" />;
  if (status === 'delivered') return <CheckCheck className="h-3 w-3 text-primary/70" />;
  return <Check className="h-3 w-3 text-primary/50" />;
};

const ChatWindow: React.FC = () => {
  const {
    messages,
    selectedLeadId,
    highlightedLeadId,
    highlightedCandidateName,
    typingUserIds,
    onlineUserIds,
    sendMessage,
    assignLeadToMe,
    markMessagesRead,
    sendTyping,
    setSelectedLeadId,
  } = useNexusState();

  const { chatMaxChars, loading: configLoading, overLimit } = useChat();
  const { highlightQuery, bubbleHighlightClassName } = useHighlight();
  const [draft, setDraft] = useState('');
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
  const [recording, setRecording] = useState(false);
  const [uploadingVoice, setUploadingVoice] = useState(false);
  const [audioUrls, setAudioUrls] = useState<Record<number, string>>({});
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const typingTimer = useRef<number | null>(null);

  const contextLeadId = useMemo(() => selectedLeadId, [selectedLeadId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    const last = messages[messages.length - 1];
    if (last) markMessagesRead(last.id);
  }, [messages, markMessagesRead]);

  useEffect(() => {
    const closeMenu = () => setContextMenu(null);
    window.addEventListener('click', closeMenu);
    return () => window.removeEventListener('click', closeMenu);
  }, []);

  const handleSend = () => {
    const text = draft.trim();
    if (!text || configLoading || chatMaxChars <= 0 || overLimit(draft)) return;
    setDraft('');
    if (typingTimer.current) window.clearTimeout(typingTimer.current);
    sendTyping(false);
    void sendMessage(text, contextLeadId);
  };

  const handleDraftChange = (value: string) => {
    if (chatMaxChars > 0 && value.length > chatMaxChars) return;
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
      const formData = new FormData();
      formData.append('file', blob, 'voice-note.webm');
      if (contextLeadId) formData.append('lead_id', String(contextLeadId));
      setUploadingVoice(true);
      try {
        await apiUpload(
          contextLeadId ? `chat/voice?lead_id=${contextLeadId}` : 'chat/voice',
          formData
        );
      } finally {
        setUploadingVoice(false);
      }
    };
    recorderRef.current = recorder;
    recorder.start();
    setRecording(true);
  };

  const stopRecording = () => {
    recorderRef.current?.stop();
    setRecording(false);
  };

  const resolveMediaUrl = (url?: string | null) => {
    if (!url) return '';
    if (url.startsWith('http')) return url;
    const base = resolveBaseUrl().replace(/\/api\/v1\/?$/, '');
    return `${base}${url}`;
  };

  useEffect(() => {
    const token = getStoredToken();
    if (!token) return;

    const voiceMessages = messages.filter(message => message.message_type === 'voice' && message.media_url);
    let cancelled = false;

    voiceMessages.forEach(async message => {
      if (audioUrls[message.id]) return;
      try {
        const response = await fetch(resolveMediaUrl(message.media_url), {
          headers: {
            Authorization: `Bearer ${token}`,
            'ngrok-skip-browser-warning': 'true',
          },
        });
        if (!response.ok || cancelled) return;
        const blob = await response.blob();
        const objectUrl = URL.createObjectURL(blob);
        if (!cancelled) {
          setAudioUrls(prev => ({ ...prev, [message.id]: objectUrl }));
        }
      } catch {
        // playback unavailable
      }
    });

    return () => {
      cancelled = true;
    };
  }, [messages, audioUrls]);

  const canSend =
    !configLoading && chatMaxChars > 0 && draft.trim().length > 0 && !overLimit(draft);

  const currentUserId = getCurrentUserId();

  const getSenderPresence = (senderUserId: number): PresenceInfo => ({
    status: onlineUserIds.includes(senderUserId) ? 'online' : 'offline',
  });

  return (
    <div className="flex h-full flex-col rounded-xl border border-border bg-white shadow-sm">
      <div className="border-b border-border px-4 py-3">
        <h2 className="text-sm font-semibold text-text-primary">Team Collaboration</h2>
        <p className="text-xs text-text-primary/70">
          {onlineUserIds.length} online
          {typingUserIds.length > 0 ? ` · ${typingUserIds.length} typing` : ''}
        </p>
        {selectedLeadId && (
          <button
            type="button"
            onClick={() => setSelectedLeadId(null)}
            className="mt-2 rounded-md bg-primary/10 px-2 py-1 text-[10px] font-medium text-primary"
          >
            Discussing lead #{selectedLeadId} (clear)
          </button>
        )}
      </div>

      <div className="custom-scrollbar chat-message-stream flex-1 overflow-y-auto">
        <div className="chat-message-stream-inner">
        {messages.map((message, index) => {
          const isOutgoing =
            currentUserId != null && message.sender_user_id === currentUserId;
          const showTimestamp = shouldShowMessageTimestamp(
            messages,
            index,
            item => item.sender_user_id,
            item => item.created_at
          );
          const isHighlighted =
            (highlightedLeadId !== null && message.lead_id === highlightedLeadId) ||
            (highlightedCandidateName !== null &&
              message.text.toLowerCase().includes(highlightedCandidateName.toLowerCase()));
          const messageTime = formatMessageTime(message.created_at);

          if (message.message_type === 'system') {
            return (
              <DirectionalMessageRow
                key={message.id}
                isOutgoing={false}
                fullWidth
                bubbleClassName="bg-incoming text-center"
              >
                <MessageBody text={message.text} className="chat-message-meta" />
              </DirectionalMessageRow>
            );
          }

          const bubbleTone = isHighlighted
            ? 'border-primary/40 ring-1 ring-primary/30'
            : highlightQuery && message.text.toLowerCase().includes(highlightQuery.toLowerCase())
              ? bubbleHighlightClassName
              : '';
          const bubbleBg = isOutgoing ? 'bg-outgoing' : 'bg-incoming';

          return (
            <DirectionalMessageRow
              key={message.id}
              isOutgoing={isOutgoing}
              senderName={message.sender_name}
              senderPresence={!isOutgoing ? getSenderPresence(message.sender_user_id) : null}
              showTimestamp={showTimestamp}
              clusterGap={showTimestamp && index > 0}
              bubbleClassName={`${bubbleBg} ${bubbleTone}`}
              timestamp={messageTime}
              trailingMeta={isOutgoing ? deliveryIcon(message.delivery_status) : undefined}
              onContextMenu={event => {
                event.preventDefault();
                setContextMenu({ x: event.clientX, y: event.clientY, message });
              }}
            >
              {message.message_type === 'voice' && message.media_url ? (
                <audio controls className="mt-1 w-full" src={audioUrls[message.id] ?? undefined} />
              ) : (
                <MessageBody text={message.text} highlightQuery={highlightQuery} />
              )}
            </DirectionalMessageRow>
          );
        })}
        <div ref={bottomRef} />
        </div>
      </div>

      <div className="border-t border-border bg-white p-3">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={recording ? stopRecording : () => void startRecording()}
            disabled={uploadingVoice}
            className={`rounded-lg p-2 ${
              recording ? 'bg-red-500 text-white' : 'bg-primary/10 text-primary'
            }`}
            title={recording ? 'Stop recording' : 'Record voice note'}
          >
            {recording ? <Square className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
          </button>
          <EmotePicker
            onPick={insertEmote}
            disabled={configLoading || chatMaxChars <= 0}
          />
          <ChatMessageInput
            value={draft}
            onChange={handleDraftChange}
            onKeyDown={event => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                if (canSend) void handleSend();
              }
            }}
            canSend={canSend}
            chatMaxChars={chatMaxChars}
            loading={configLoading}
          />
          <button
            type="button"
            onClick={() => void handleSend()}
            disabled={!canSend}
            className="rounded-lg bg-primary p-2 text-white hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
      </div>

      {contextMenu && (
        <div
          className="fixed z-50 min-w-[160px] rounded-lg border border-border bg-white py-1 shadow-lg"
          style={{ top: contextMenu.y, left: contextMenu.x }}
          onClick={event => event.stopPropagation()}
        >
          {contextMenu.message.lead_id && (
            <button
              type="button"
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-text-primary hover:bg-incoming"
              onClick={() => {
                void assignLeadToMe(contextMenu.message.lead_id!);
                setContextMenu(null);
              }}
            >
              <UserPlus className="h-4 w-4" />
              Assign to Me
            </button>
          )}
          <button
            type="button"
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-text-primary hover:bg-incoming"
            onClick={() => {
              if (contextMenu.message.lead_id) setSelectedLeadId(contextMenu.message.lead_id);
              setContextMenu(null);
            }}
          >
            Discuss candidate
          </button>
        </div>
      )}
    </div>
  );
};

export default ChatWindow;
