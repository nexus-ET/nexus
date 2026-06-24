import React, { useEffect, useRef } from 'react';
import { X } from 'lucide-react';

export interface ChatReplyPreview {
  senderLabel: string;
  content: string;
}

interface ChatMessageInputProps {
  value: string;
  onChange: (value: string) => void;
  onKeyDown?: (event: React.KeyboardEvent<HTMLInputElement>) => void;
  onSend?: () => void;
  canSend: boolean;
  chatMaxChars: number;
  loading?: boolean;
  disabled?: boolean;
  className?: string;
  replyPreview?: ChatReplyPreview | null;
  onClearReply?: () => void;
}

const ChatMessageInput: React.FC<ChatMessageInputProps> = ({
  value,
  onChange,
  onKeyDown,
  canSend,
  chatMaxChars,
  loading = false,
  disabled = false,
  className = '',
  replyPreview = null,
  onClearReply,
}) => {
  const inputRef = useRef<HTMLInputElement>(null);
  const limitReady = !loading && chatMaxChars > 0;
  const hintText = limitReady
    ? value.length > 0
      ? `${value.length}/${chatMaxChars}`
      : `Only ${chatMaxChars} characters can be sent`
    : 'Loading limit…';

  const hasReply = Boolean(replyPreview);

  useEffect(() => {
    if (!replyPreview || !limitReady) return;
    const frame = requestAnimationFrame(() => {
      inputRef.current?.focus();
    });
    return () => cancelAnimationFrame(frame);
  }, [replyPreview?.senderLabel, replyPreview?.content, limitReady]);

  return (
    <div
      className={`relative min-w-0 flex-1 ${hasReply ? 'min-w-[min(100%,28rem)]' : ''} ${className}`}
    >
      <div
        className={`relative w-full rounded-lg border border-border bg-white focus-within:border-primary focus-within:ring-2 focus-within:ring-primary ${
          hasReply ? 'pt-0' : ''
        }`}
      >
        {replyPreview && (
          <div className="relative border-b border-border bg-incoming px-3 py-2 pr-10 text-left">
            <p className="truncate text-[11px] font-semibold text-text-primary/80">
              {replyPreview.senderLabel}
            </p>
            <p className="max-h-36 overflow-y-auto whitespace-pre-wrap break-words text-xs text-text-primary/70">
              {replyPreview.content}
            </p>
            {onClearReply && (
              <button
                type="button"
                onClick={onClearReply}
                className="absolute right-1.5 top-1.5 rounded p-1 text-text-primary/70 hover:bg-outgoing"
                title="Cancel reply"
                aria-label="Cancel reply"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
        )}

        <div className="relative">
          <input
            ref={inputRef}
            value={value}
            onChange={event => onChange(event.target.value)}
            onKeyDown={onKeyDown}
            disabled={disabled || loading || !limitReady}
            maxLength={limitReady ? chatMaxChars : undefined}
            placeholder={limitReady ? 'Type a message…' : 'Loading message limits…'}
            className={`w-full bg-transparent py-2 pl-3 pr-[11.5rem] text-sm text-text-primary outline-none focus-visible:ring-0 disabled:cursor-wait disabled:opacity-60 ${
              hasReply ? 'rounded-b-lg' : 'rounded-lg'
            }`}
          />
          <span
            aria-live="polite"
            className={`pointer-events-none absolute right-3 top-1/2 max-w-[10.5rem] -translate-y-1/2 truncate text-right text-[11px] ${
              limitReady && value.length >= chatMaxChars
                ? 'text-red-600'
                : limitReady && value.length >= chatMaxChars * 0.9
                  ? 'text-amber-600'
                  : 'text-text-primary/50'
            }`}
          >
            {hintText}
          </span>
        </div>
      </div>
    </div>
  );
};

export default ChatMessageInput;
