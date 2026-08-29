import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Bell, Loader2 } from 'lucide-react';
import { apiFetch, hasValidSession } from '../utils/api';
import { useBusinessTimezone } from '../context/BusinessTimezoneContext';

interface NotificationInboxItem {
  id: number;
  title: string;
  message: string;
  channel: string;
  status: string;
  priority: 'urgent' | 'important' | 'normal' | string;
  sent_at: string;
  booking_id?: number | null;
}

interface NotificationInboxResponse {
  notifications: NotificationInboxItem[];
  unread_count: number;
}

const priorityStyles: Record<string, string> = {
  urgent: 'border-l-red-500 bg-red-50',
  important: 'border-l-amber-500 bg-amber-50',
  normal: 'border-l-border-subtle bg-card',
};

const channelLabels: Record<string, string> = {
  in_app: 'In-app',
  push: 'Push',
  email: 'Email',
  whatsapp: 'WhatsApp',
};

const priorityLabel: Record<string, string> = {
  urgent: 'Urgent',
  important: 'Important',
  normal: 'Normal',
};

const NotificationBell: React.FC<{ onDarkHeader?: boolean }> = ({ onDarkHeader = false }) => {
  const { formatDateTime } = useBusinessTimezone();
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<NotificationInboxItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const panelRef = useRef<HTMLDivElement | null>(null);

  const loadInbox = useCallback(async () => {
    if (!hasValidSession()) return;
    try {
      setLoading(true);
      const data = (await apiFetch('notifications/inbox', {
        authRedirect: false,
      })) as NotificationInboxResponse;
      setItems(Array.isArray(data.notifications) ? data.notifications : []);
      setUnreadCount(data.unread_count ?? 0);
    } catch {
      setItems([]);
      setUnreadCount(0);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadInbox();
    const interval = setInterval(loadInbox, 30000);
    const refreshHandler = () => loadInbox();
    window.addEventListener('nexus:notifications-refresh', refreshHandler);
    return () => {
      clearInterval(interval);
      window.removeEventListener('nexus:notifications-refresh', refreshHandler);
    };
  }, [loadInbox]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    if (open) {
      window.addEventListener('click', handleClickOutside);
    }
    return () => window.removeEventListener('click', handleClickOutside);
  }, [open]);

  return (
    <div className="relative" ref={panelRef}>
      <button
        type="button"
        onClick={() => {
          setOpen(prev => !prev);
          if (!open) loadInbox();
        }}
        className={`relative p-2 rounded-full transition-colors ${
          onDarkHeader
            ? 'text-white/85 hover:bg-white/10 hover:text-white'
            : 'text-text-muted hover:bg-surface-bg'
        }`}
        aria-label="Notifications"
      >
        <Bell size={20} />
        {unreadCount > 0 && (
          <span className={`absolute top-1.5 right-1.5 min-w-[16px] h-4 px-1 bg-alert rounded-full border-2 text-[9px] font-bold text-white flex items-center justify-center ${
            onDarkHeader ? 'border-canvas' : 'border-card'
          }`}>
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-80 max-w-[90vw] rounded-xl border border-border-subtle bg-card shadow-xl z-50 overflow-hidden">
          <div className="px-4 py-3 border-b border-border-subtle bg-surface-bg">
            <p className="text-sm font-semibold text-text-main">Notifications</p>
            <p className="text-[11px] text-text-muted">Appointments, assignments, and alerts</p>
          </div>

          <div className="max-h-96 overflow-y-auto custom-scrollbar">
            {loading ? (
              <div className="flex items-center justify-center py-8 text-text-muted text-sm">
                <Loader2 size={16} className="animate-spin mr-2" />
                Loading...
              </div>
            ) : items.length === 0 ? (
              <p className="px-4 py-6 text-xs text-text-muted italic text-center">No notifications yet.</p>
            ) : (
              items.map(item => (
                <div
                  key={item.id}
                  className={`px-4 py-3 border-b border-border-subtle/60 border-l-4 ${
                    priorityStyles[item.priority] || priorityStyles.normal
                  }`}
                >
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <p className="text-xs font-semibold text-text-main truncate">{item.title}</p>
                    <span className="text-[10px] font-bold uppercase text-text-muted shrink-0">
                      {priorityLabel[item.priority] || item.priority}
                    </span>
                  </div>
                  <p className="text-xs text-text-muted">{item.message}</p>
                  <p className="text-[10px] text-text-muted mt-1">
                    {formatDateTime(item.sent_at)} · {channelLabels[item.channel] || item.channel}
                  </p>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default NotificationBell;
