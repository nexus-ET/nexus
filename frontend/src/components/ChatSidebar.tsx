import React, { useEffect, useRef, useState } from 'react';
import { Loader2, Search, UserPlus } from 'lucide-react';
import HeadlessScrollArea from './HeadlessScrollArea';
import { MessageSenderAvatar, initialsFromName } from './PresenceIndicator';
import {
  AdminSearchResult,
  Conversation,
  getOtherParticipant,
  useMessagingHub,
} from '../hooks/useMessagingHub';

interface ChatSidebarProps {
  onSelectConversation: (conversation: Conversation) => void;
}

const formatTime = (value?: string | null) => {
  if (!value) return '';
  const date = new Date(value);
  const now = new Date();
  const sameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate();
  if (sameDay) {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
  return date.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const ChatSidebar: React.FC<ChatSidebarProps> = ({ onSelectConversation }) => {
  const {
    sortedInbox,
    activeConversationId,
    currentUserId,
    presenceByUserId,
    getOrCreateDirect,
    searchAdmins,
    inboxReady,
    getConversationPreview,
  } = useMessagingHub();

  const [adminQuery, setAdminQuery] = useState('');
  const [adminResults, setAdminResults] = useState<AdminSearchResult[]>([]);
  const [loadingAdmin, setLoadingAdmin] = useState(false);
  const [selectingAdminId, setSelectingAdminId] = useState<number | null>(null);
  const [selectError, setSelectError] = useState<string | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const adminSearchRef = useRef<HTMLInputElement | null>(null);
  const pickerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!pickerOpen) return;
    const timer = window.setTimeout(() => {
      setLoadingAdmin(true);
      void searchAdmins(adminQuery)
        .then(results => results.filter(admin => admin.id !== currentUserId))
        .then(setAdminResults)
        .catch(error =>
          setSelectError(error instanceof Error ? error.message : 'Could not load admins.')
        )
        .finally(() => setLoadingAdmin(false));
    }, adminQuery.trim() ? 250 : 0);
    return () => window.clearTimeout(timer);
  }, [adminQuery, currentUserId, pickerOpen, searchAdmins]);

  const openPicker = () => {
    setPickerOpen(true);
    setSelectError(null);
    adminSearchRef.current?.focus();
  };

  const handleSelectAdmin = async (admin: AdminSearchResult) => {
    if (selectingAdminId != null) return;
    try {
      setSelectingAdminId(admin.id);
      setSelectError(null);
      const conversation = await getOrCreateDirect(Number(admin.id));
      onSelectConversation(conversation);
      setAdminQuery('');
      setAdminResults([]);
      setPickerOpen(false);
    } catch (error) {
      setSelectError(error instanceof Error ? error.message : 'Could not start that conversation.');
    } finally {
      setSelectingAdminId(null);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-border bg-white shadow-sm">
      <div className="shrink-0 border-b border-border px-4 py-3">
        <div className="flex items-center justify-between gap-2">
          <div>
            <h2 className="text-sm font-semibold text-text-primary">Inbox</h2>
            <p className="text-xs text-text-primary/70">{sortedInbox.length} active conversations</p>
          </div>
          <button
            type="button"
            onClick={openPicker}
            className="inline-flex items-center gap-1 rounded-lg border border-border px-2 py-1 text-xs font-medium text-text-primary hover:bg-incoming"
          >
            <UserPlus className="h-3.5 w-3.5" />
            New chat
          </button>
        </div>

        <div ref={pickerRef} className="relative mt-3">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-primary/60" />
          <input
            ref={adminSearchRef}
            value={adminQuery}
            onChange={event => setAdminQuery(event.target.value)}
            onFocus={() => setPickerOpen(true)}
            onBlur={event => {
              const next = event.relatedTarget as Node | null;
              if (next && pickerRef.current?.contains(next)) return;
              window.setTimeout(() => setPickerOpen(false), 150);
            }}
            placeholder="Search admins (online or offline)..."
            className="w-full rounded-lg border border-border py-2 pl-9 pr-8 text-sm text-text-primary outline-none focus:border-primary focus:ring-2 focus:ring-primary"
          />
          {loadingAdmin && (
            <Loader2 className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-primary" />
          )}

          {pickerOpen && (
            <div className="absolute z-30 mt-1 max-h-56 w-full overflow-y-auto rounded-lg border border-border bg-white shadow-lg">
              {loadingAdmin && adminResults.length === 0 ? (
                <p className="px-3 py-2 text-xs text-text-primary/70">Loading admins...</p>
              ) : adminResults.length === 0 ? (
                <p className="px-3 py-2 text-xs text-text-primary/70">
                  {adminQuery.trim() ? 'No admins match that search.' : 'No admins available.'}
                </p>
              ) : (
                adminResults.map(admin => {
                  const isOffline = (admin.status ?? 'offline') === 'offline';
                  return (
                    <button
                      key={admin.id}
                      type="button"
                      disabled={selectingAdminId === admin.id}
                      onMouseDown={event => {
                        event.preventDefault();
                        void handleSelectAdmin(admin);
                      }}
                      className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-incoming disabled:opacity-60"
                    >
                      <MessageSenderAvatar
                        initials={initialsFromName(admin.full_name)}
                        senderName={admin.full_name}
                        presence={{
                          status: admin.status ?? 'offline',
                          last_seen_at: admin.last_seen_at,
                          last_active_at: admin.last_active_at,
                          away_duration_seconds: admin.away_duration_seconds,
                        }}
                      />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-medium text-text-primary">
                          {admin.full_name}
                        </span>
                        <span className="block truncate text-xs text-text-primary/70">{admin.email}</span>
                      </span>
                      {isOffline && (
                        <span className="shrink-0 text-[10px] text-text-primary/60">Offline OK</span>
                      )}
                      {selectingAdminId === admin.id && (
                        <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-primary" />
                      )}
                    </button>
                  );
                })
              )}
              <p className="border-t border-border px-3 py-2 text-[10px] text-text-primary/60">
                You can message admins while they are offline.
              </p>
            </div>
          )}
        </div>

        {selectError && <p className="mt-2 text-xs text-red-600">{selectError}</p>}
      </div>

      <HeadlessScrollArea className="min-h-0 flex-1">
        {sortedInbox.length === 0 && inboxReady ? (
          <p className="px-4 py-6 text-sm text-text-primary/70">
            Click <span className="font-medium">New chat</span> or search an admin above to start a
            conversation.
          </p>
        ) : (
          sortedInbox.map((conversation: Conversation) => {
            const other = getOtherParticipant(conversation, currentUserId);
            const livePresence = other ? presenceByUserId[other.admin_id] : null;
            const presence = other
              ? livePresence ?? {
                  status: other.status ?? 'offline',
                  last_seen_at: other.last_seen_at,
                  last_active_at: other.last_active_at,
                  away_duration_seconds: other.away_duration_seconds,
                }
              : null;

            return (
              <button
                key={conversation.id}
                type="button"
                onClick={() => onSelectConversation(conversation)}
                className={`flex w-full items-start gap-3 border-b border-border px-4 py-3 text-left transition hover:bg-incoming ${
                  activeConversationId === conversation.id
                    ? 'bg-outgoing ring-1 ring-inset ring-primary/30'
                    : ''
                }`}
              >
                <div className="mt-0.5 shrink-0">
                  {other ? (
                    <MessageSenderAvatar
                      initials={initialsFromName(conversation.display_name)}
                      senderName={conversation.display_name}
                      presence={presence}
                    />
                  ) : (
                    <div className="message-sender-avatar" aria-hidden>
                      <span>?</span>
                    </div>
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex w-full items-center justify-between gap-2">
                    <p className="min-w-0 flex-1 truncate text-left text-sm font-semibold text-text-primary">
                      {conversation.display_name}
                    </p>
                    <div className="flex shrink-0 items-center gap-1.5 text-right">
                      {conversation.unread_count > 0 && (
                        <span className="rounded-full bg-primary px-2 py-0.5 text-[10px] font-semibold text-white">
                          {conversation.unread_count}
                        </span>
                      )}
                      <span className="whitespace-nowrap text-[10px] text-text-primary/60">
                        {formatTime(conversation.last_message_at)}
                      </span>
                    </div>
                  </div>
                  <p className="truncate text-left text-xs text-text-primary/70">
                    {getConversationPreview(conversation)}
                  </p>
                </div>
              </button>
            );
          })
        )}
      </HeadlessScrollArea>
    </div>
  );
};

export default ChatSidebar;
