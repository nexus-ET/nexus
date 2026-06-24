import React from 'react';

export interface PresenceInfo {
  status: 'online' | 'away' | 'offline' | string;
  last_seen_at?: string | null;
  last_active_at?: string | null;
  away_duration_seconds?: number | null;
}

export const formatAwayDuration = (seconds?: number | null): string => {
  if (seconds == null || seconds <= 0) return '';
  if (seconds < 60) return 'just now';
  if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60);
    return `${minutes}m`;
  }
  if (seconds < 86400) {
    const hours = Math.floor(seconds / 3600);
    return `${hours}h`;
  }
  const days = Math.floor(seconds / 86400);
  return `${days}d`;
};

const statusStyles: Record<string, { gloss: string; label: string }> = {
  online: {
    gloss: 'presence-gloss-dot--online',
    label: 'Online',
  },
  away: {
    gloss: 'presence-gloss-dot--away',
    label: 'Away',
  },
  offline: {
    gloss: 'presence-gloss-dot--offline',
    label: 'Offline',
  },
};

export const avatarPresenceLabel = (status?: string | null): string =>
  statusStyles[status ?? 'offline']?.label ?? statusStyles.offline.label;

export const initialsFromName = (name: string): string => {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) {
    return `${parts[0][0] ?? ''}${parts[parts.length - 1][0] ?? ''}`.toUpperCase();
  }
  return (name.slice(0, 2) || '?').toUpperCase();
};

const glossDotClass = (status?: string | null): string =>
  statusStyles[status ?? 'offline']?.gloss ?? statusStyles.offline.gloss;

interface MessageSenderAvatarProps {
  initials: string;
  senderName: string;
  presence?: PresenceInfo | null;
}

export const MessageSenderAvatar: React.FC<MessageSenderAvatarProps> = ({
  initials,
  senderName,
  presence = null,
}) => {
  const status = presence?.status ?? 'offline';
  const label = avatarPresenceLabel(status);

  return (
    <div
      className="message-sender-avatar"
      title={`${senderName} · ${label}`}
      aria-label={`${senderName}, ${label}`}
    >
      <span aria-hidden>{initials}</span>
      <span
        aria-hidden
        className={`presence-gloss-dot absolute -bottom-0.5 -right-0.5 h-3 w-3 ${glossDotClass(status)}`}
      />
    </div>
  );
};

interface PresenceIndicatorProps {
  presence?: PresenceInfo | null;
  size?: 'sm' | 'md';
  showLabel?: boolean;
}

const PresenceIndicator: React.FC<PresenceIndicatorProps> = ({
  presence,
  size = 'sm',
  showLabel = false,
}) => {
  const status = presence?.status ?? 'offline';
  const label = avatarPresenceLabel(status);
  const dotSize = size === 'md' ? 'h-3 w-3' : 'h-2.5 w-2.5';
  const awayLabel =
    status === 'away'
      ? formatAwayDuration(presence?.away_duration_seconds)
      : status === 'offline'
        ? formatAwayDuration(presence?.away_duration_seconds)
        : '';

  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className={`presence-gloss-dot ${dotSize} ${glossDotClass(status)}`}
        title={
          status === 'online'
            ? 'Online'
            : status === 'away'
              ? `Away for ${awayLabel || 'a while'}`
              : `Offline${awayLabel ? ` · last seen ${awayLabel} ago` : ''}`
        }
      />
      {showLabel && (
        <span className="text-[10px] font-medium text-gray-500">
          {status === 'online' && 'Online'}
          {status === 'away' && `Away · ${awayLabel}`}
          {status === 'offline' && (awayLabel ? `Offline · ${awayLabel}` : 'Offline')}
        </span>
      )}
    </span>
  );
};

export default PresenceIndicator;
