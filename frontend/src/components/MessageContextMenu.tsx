import React, { useEffect } from 'react';
import { CornerUpLeft, Pin } from 'lucide-react';
import { InternalMessage } from '../hooks/useMessagingHub';
import { QUICK_REACTIONS } from '../utils/chatEmotes';

interface MessageContextMenuState {
  x: number;
  y: number;
  message: InternalMessage;
}

interface MessageContextMenuProps {
  menu: MessageContextMenuState | null;
  onClose: () => void;
  onReply: (message: InternalMessage) => void;
  onPin: (message: InternalMessage) => void;
  onReact: (message: InternalMessage, emoji: string) => void;
}

const MessageContextMenu: React.FC<MessageContextMenuProps> = ({
  menu,
  onClose,
  onReply,
  onPin,
  onReact,
}) => {
  useEffect(() => {
    if (!menu) return;
    const close = () => onClose();
    window.addEventListener('click', close);
    window.addEventListener('scroll', close, true);
    return () => {
      window.removeEventListener('click', close);
      window.removeEventListener('scroll', close, true);
    };
  }, [menu, onClose]);

  if (!menu) return null;

  const clampedX = Math.min(menu.x, window.innerWidth - 240);
  const clampedY = Math.min(menu.y, window.innerHeight - 120);

  return (
    <div
      className="fixed z-50 min-w-[14rem] rounded-xl border border-border bg-white p-2 shadow-lg"
      style={{ top: clampedY, left: clampedX }}
      onClick={event => event.stopPropagation()}
      onContextMenu={event => event.preventDefault()}
    >
      <button
        type="button"
        className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-text-primary hover:bg-incoming"
        onClick={() => {
          onReply(menu.message);
          onClose();
        }}
      >
        <CornerUpLeft className="h-4 w-4 text-primary" />
        Reply
      </button>

      <button
        type="button"
        className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-text-primary hover:bg-incoming"
        onClick={() => {
          onPin(menu.message);
          onClose();
        }}
      >
        <Pin className="h-4 w-4 text-primary" />
        Pin
      </button>

      <div className="my-1 border-t border-border" />

      <p className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-wide text-text-primary/70">
        React
      </p>
      <div className="grid grid-cols-6 gap-1 px-1 pb-1">
        {QUICK_REACTIONS.map(emoji => (
          <button
            key={emoji}
            type="button"
            title={`React with ${emoji}`}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-xl hover:bg-outgoing active:scale-95"
            onClick={() => {
              onReact(menu.message, emoji);
              onClose();
            }}
          >
            {emoji}
          </button>
        ))}
      </div>
    </div>
  );
};

export type { MessageContextMenuState };
export default MessageContextMenu;
