import React, { useCallback, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { MessageSquare, X } from 'lucide-react';
import { apiFetch } from '../utils/api';
import { useNexusSession } from '../context/NexusSessionContext';

const TOAST_DISMISS_MS = 6000;
const MESSAGING_HUB_PATH = '/messaging-hub';

const NotificationToast: React.FC = () => {
  const navigate = useNavigate();
  const { activeToast, dismissMessageToast, refreshUnreadMessageCount } = useNexusSession();
  const dismissTimerRef = useRef<number | null>(null);
  const isHoveredRef = useRef(false);

  const clearDismissTimer = useCallback(() => {
    if (dismissTimerRef.current != null) {
      window.clearTimeout(dismissTimerRef.current);
      dismissTimerRef.current = null;
    }
  }, []);

  const scheduleDismiss = useCallback(() => {
    if (!activeToast || isHoveredRef.current) return;
    clearDismissTimer();
    dismissTimerRef.current = window.setTimeout(() => {
      dismissMessageToast();
    }, TOAST_DISMISS_MS);
  }, [activeToast, clearDismissTimer, dismissMessageToast]);

  useEffect(() => {
    if (!activeToast) {
      clearDismissTimer();
      return;
    }
    isHoveredRef.current = false;
    scheduleDismiss();
    return clearDismissTimer;
  }, [activeToast, scheduleDismiss, clearDismissTimer]);

  const handleMouseEnter = () => {
    isHoveredRef.current = true;
    clearDismissTimer();
  };

  const handleMouseLeave = () => {
    isHoveredRef.current = false;
    scheduleDismiss();
  };

  const handleNavigate = async () => {
    if (!activeToast) return;

    const { conversationId, messageId } = activeToast;
    dismissMessageToast();
    clearDismissTimer();

    try {
      await apiFetch(`chat/conversations/${conversationId}/read`, {
        method: 'POST',
        body: JSON.stringify({}),
      });
      await refreshUnreadMessageCount();
    } catch {
      // Still navigate if mark-read fails.
    }

    const params = new URLSearchParams({
      conversation_id: String(conversationId),
    });
    if (messageId > 0) {
      params.set('message', String(messageId));
    }
    navigate(`${MESSAGING_HUB_PATH}?${params.toString()}`);
  };

  if (!activeToast) return null;

  return (
    <button
      type="button"
      onClick={() => void handleNavigate()}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      className="notification-toast flex max-w-sm cursor-pointer items-start gap-3 rounded-xl border-l-4 border-yellow-400 bg-indigo-700 p-4 text-left shadow-2xl transition hover:bg-indigo-600"
      aria-live="polite"
    >
      <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white/15 text-white">
        <MessageSquare className="h-4 w-4" />
      </span>
      <span className="min-w-0 flex-1">
        <p className="text-sm font-bold text-white">
          New message from {activeToast.senderName}
        </p>
        <p className="mt-1 line-clamp-2 text-sm font-bold text-white/95">{activeToast.snippet}</p>
      </span>
      <span
        role="button"
        tabIndex={0}
        onClick={event => {
          event.stopPropagation();
          clearDismissTimer();
          dismissMessageToast();
        }}
        onKeyDown={event => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            event.stopPropagation();
            clearDismissTimer();
            dismissMessageToast();
          }
        }}
        className="shrink-0 rounded p-0.5 text-lg leading-none text-white/80 hover:text-white"
        aria-label="Dismiss notification"
      >
        <X className="h-4 w-4" />
      </span>
    </button>
  );
};

export default NotificationToast;
