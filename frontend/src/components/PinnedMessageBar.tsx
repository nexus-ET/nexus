import React from 'react';
import { Pin, X } from 'lucide-react';
import { messageBubbleTextClass } from '../utils/chatEmotes';
import { PinnedMessageSnapshot } from '../utils/chatPins';

interface PinnedMessageBarProps {
  pinned: PinnedMessageSnapshot;
  currentUserId: number | null;
  onClose: () => void;
  onJumpToMessage?: () => void;
}

const PinnedMessageBar: React.FC<PinnedMessageBarProps> = ({
  pinned,
  currentUserId,
  onClose,
  onJumpToMessage,
}) => {
  const senderLabel =
    pinned.sender_id === currentUserId ? 'You' : pinned.sender_name;

  return (
    <div className="shrink-0 border-b border-border bg-outgoing px-3 py-1.5">
      <div className="flex items-start gap-1.5">
        <Pin className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden />
        <button
          type="button"
          onClick={onJumpToMessage}
          className="min-w-0 flex-1 text-left hover:opacity-90"
          title="Jump to message"
        >
          <p className="chat-sender-name uppercase tracking-wide">
            Pinned message · {senderLabel}
          </p>
          <div className="truncate">
            <MessageBody text={pinned.content} />
          </div>
        </button>
        <button
          type="button"
          onClick={onClose}
          className="shrink-0 rounded p-1 text-text-primary/70 hover:bg-incoming"
          title="Unpin message"
          aria-label="Unpin message"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
};

export default PinnedMessageBar;
