export function isEmojiOnlyText(text: string): boolean {
  const trimmed = text.trim();
  if (!trimmed) return false;

  const stripped = trimmed
    .replace(/[\p{Extended_Pictographic}\p{Emoji_Presentation}]/gu, '')
    .replace(/[\u200D\uFE0F\u20E3\uFE0E]/g, '')
    .replace(/\s/g, '');

  return stripped.length === 0;
}

/** Teams-style message body typography (14px / 1.5 line-height). */
export function messageBubbleTextClass(text: string): string {
  const base = 'chat-message-body whitespace-pre-wrap break-words';
  if (isEmojiOnlyText(text)) {
    return `${base} text-[1.875rem] leading-tight tracking-wide`;
  }
  return base;
}

export const QUICK_REACTIONS = ['👍', '❤️', '😂', '😮', '😢', '🙏'] as const;
