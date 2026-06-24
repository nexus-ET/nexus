import React, { useEffect, useRef, useState } from 'react';
import { Smile } from 'lucide-react';

const EMOTE_GROUPS = [
  {
    label: 'Smileys',
    emotes: ['😀', '😃', '😄', '😁', '😅', '😂', '🤣', '🙂', '😉', '😊', '😇', '🥰', '😍', '🤩', '😘', '😋', '😎', '🤔', '😐', '😑', '😶', '🙄', '😏', '😣', '😥', '😮', '🤐', '😴', '😭', '😤'],
  },
  {
    label: 'Gestures',
    emotes: ['👍', '👎', '👏', '🙌', '🤝', '🙏', '💪', '✌️', '🤞', '🤙', '👋', '🫶', '👌', '🤌', '✋', '🖐️', '👊', '🤜', '🤛', '☝️', '👆', '👇', '👈', '👉'],
  },
  {
    label: 'Hearts',
    emotes: ['❤️', '🧡', '💛', '💚', '💙', '💜', '🖤', '🤍', '🤎', '💔', '❣️', '💕', '💞', '💓', '💗', '💖', '💘', '💝', '💟', '♥️'],
  },
  {
    label: 'Objects',
    emotes: ['🎉', '🎊', '✨', '🔥', '⭐', '🌟', '💯', '✅', '❌', '⚠️', '💡', '📌', '📎', '📝', '💬', '📣', '🎓', '📚', '💼', '🏆', '🎯', '🚀', '⏰', '📅'],
  },
];

interface EmotePickerProps {
  onPick: (emote: string) => void;
  disabled?: boolean;
}

const EmotePicker: React.FC<EmotePickerProps> = ({ onPick, disabled = false }) => {
  const [open, setOpen] = useState(false);
  const [activeGroup, setActiveGroup] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [open]);

  const handlePick = (emote: string) => {
    onPick(emote);
    setOpen(false);
  };

  return (
    <div ref={rootRef} className="relative shrink-0">
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen(prev => !prev)}
        className={`rounded-lg p-2 ${
          open ? 'bg-primary/15 text-primary' : 'bg-primary/10 text-primary'
        } hover:bg-primary/15 disabled:cursor-not-allowed disabled:opacity-50`}
        title="Insert emoji"
        aria-label="Insert emoji"
        aria-expanded={open}
      >
        <Smile className="h-5 w-5" />
      </button>

      {open && (
        <div
          className="absolute bottom-full left-0 z-50 mb-2 w-[20.5rem] overflow-hidden rounded-xl border border-border bg-white shadow-lg"
          role="dialog"
          aria-label="Emoji picker"
        >
          <div className="flex gap-1 border-b border-border bg-incoming p-2">
            {EMOTE_GROUPS.map((group, index) => (
              <button
                key={group.label}
                type="button"
                onClick={() => setActiveGroup(index)}
                className={`rounded-md px-2.5 py-1.5 text-xs font-semibold ${
                  activeGroup === index
                    ? 'bg-white text-text-primary shadow-sm'
                    : 'text-text-primary/70 hover:bg-white/70'
                }`}
              >
                {group.label}
              </button>
            ))}
          </div>
          <div className="custom-scrollbar grid max-h-52 grid-cols-6 gap-1 overflow-y-auto p-2.5">
            {EMOTE_GROUPS[activeGroup].emotes.map(emote => (
              <button
                key={`${activeGroup}-${emote}`}
                type="button"
                onClick={() => handlePick(emote)}
                className="flex h-11 w-11 items-center justify-center rounded-lg text-[1.75rem] leading-none transition hover:bg-outgoing active:scale-95"
                title={emote}
              >
                {emote}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default EmotePicker;
