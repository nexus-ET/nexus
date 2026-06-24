import React from 'react';
import { MessageSenderAvatar, PresenceInfo, initialsFromName } from './PresenceIndicator';

const MESSAGE_BUBBLE_CAP = 'max-w-[90%] sm:max-w-[70%]';
const AVATAR_SIZE = 'h-8 w-8';
const BUBBLE_COLUMN_CLASS = `flex w-fit min-w-0 flex-col ${MESSAGE_BUBBLE_CAP}`;

interface DirectionalMessageRowProps {
  isOutgoing: boolean;
  senderName?: string;
  showAvatar?: boolean;
  showTimestamp?: boolean;
  children: React.ReactNode;
  timestamp?: React.ReactNode;
  /** Rendered below the bubble, bottom-right (e.g. read receipts). */
  trailingMeta?: React.ReactNode;
  bubbleClassName?: string;
  onContextMenu?: (event: React.MouseEvent) => void;
  dataMessageId?: number;
  fullWidth?: boolean;
  /** Extra top spacing when a new sender/minute cluster begins. */
  clusterGap?: boolean;
  senderPresence?: PresenceInfo | null;
}

const DirectionalMessageRow: React.FC<DirectionalMessageRowProps> = ({
  isOutgoing,
  senderName,
  showAvatar = true,
  showTimestamp = true,
  children,
  timestamp,
  trailingMeta,
  bubbleClassName = '',
  onContextMenu,
  dataMessageId,
  fullWidth = false,
  clusterGap = false,
  senderPresence = null,
}) => {
  if (fullWidth) {
    return (
      <div className="mb-1 flex justify-center" data-message-id={dataMessageId}>
        <div
          className={`chat-message-meta w-full rounded-lg border border-border px-2 py-1 shadow-sm ${bubbleClassName}`}
          onContextMenu={onContextMenu}
        >
          {children}
        </div>
      </div>
    );
  }

  const bubbleCorners = isOutgoing
    ? 'rounded-xl rounded-tr-sm'
    : 'rounded-xl rounded-tl-sm';

  const displayTimestamp = showTimestamp ? timestamp : undefined;
  const showIncomingHeader = !isOutgoing && showTimestamp;

  const bubble = (
    <div
      className={`${bubbleCorners} w-fit min-w-0 max-w-full border border-border px-2 py-1 shadow-sm ${bubbleClassName}`}
    >
      {children}
    </div>
  );

  if (isOutgoing) {
    return (
      <div
        className={`mb-1 flex w-full justify-end ${clusterGap ? 'mt-3' : ''}`}
        data-message-id={dataMessageId}
      >
        <div
          className={`${BUBBLE_COLUMN_CLASS} items-end`}
          onContextMenu={onContextMenu}
        >
          {displayTimestamp && (
            <div className="mb-px flex justify-end">
              <p className="chat-message-meta shrink-0 whitespace-nowrap">{displayTimestamp}</p>
            </div>
          )}
          {bubble}
          {trailingMeta && (
            <div className="chat-message-meta mt-px flex items-center justify-end gap-0.5">
              {trailingMeta}
            </div>
          )}
        </div>
      </div>
    );
  }

  const avatarSlot =
    showIncomingHeader && senderName && showAvatar ? (
      <MessageSenderAvatar
        initials={initialsFromName(senderName)}
        senderName={senderName}
        presence={senderPresence}
      />
    ) : (
      <div className={`${AVATAR_SIZE} shrink-0`} aria-hidden />
    );

  return (
    <div
      className={`mb-1 flex w-full justify-start ${clusterGap ? 'mt-3' : ''}`}
      data-message-id={dataMessageId}
    >
      <div className="flex w-full min-w-0 flex-col items-start">
        {showIncomingHeader && senderName && (
          <div className="mb-px flex items-center gap-1.5 pl-9">
            <p className="chat-sender-name min-w-0 truncate text-left">{senderName}</p>
            {displayTimestamp && (
              <p className="chat-message-meta shrink-0 whitespace-nowrap">{displayTimestamp}</p>
            )}
          </div>
        )}

        <div className="flex w-full min-w-0 items-start gap-1">
          {senderName && avatarSlot}
          <div className={`${BUBBLE_COLUMN_CLASS} items-start`} onContextMenu={onContextMenu}>
            {bubble}
          </div>
        </div>
      </div>
    </div>
  );
};

export { MESSAGE_BUBBLE_CAP as MESSAGE_BUBBLE_MAX };
export default DirectionalMessageRow;
