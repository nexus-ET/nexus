import React, { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';

export const HIGHLIGHT_CLASS = 'chat-search-highlight';
export const BUBBLE_JUMP_CLASS = 'chat-message-jump-highlight';

export function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

export function renderHighlightedPlainText(
  text: string,
  query: string | null | undefined,
  keyPrefix: string
): React.ReactNode[] {
  const trimmed = query?.trim();
  if (!trimmed) return [text];

  const tokens = trimmed.split(/\s+/).filter(Boolean);
  const patternSource = tokens.map(escapeRegExp).join('|');
  if (!patternSource) return [text];

  const pattern = new RegExp(`(${patternSource})`, 'gi');
  const parts = text.split(pattern);
  if (parts.length === 1) return [text];

  return parts
    .map((part, index) => {
      if (!part) return null;
      if (index % 2 === 1) {
        return (
          <mark key={`${keyPrefix}-hl-${index}`} className={HIGHLIGHT_CLASS}>
            {part}
          </mark>
        );
      }
      return part;
    })
    .filter(Boolean) as React.ReactNode[];
}

export function useHighlight(queryOverride?: string | null) {
  const [searchParams] = useSearchParams();

  const highlightQuery = useMemo(() => {
    const fromState = queryOverride?.trim();
    const fromUrl = searchParams.get('q')?.trim();
    return fromState || fromUrl || null;
  }, [queryOverride, searchParams]);

  return {
    highlightQuery,
    highlightClassName: HIGHLIGHT_CLASS,
    bubbleHighlightClassName: BUBBLE_JUMP_CLASS,
  };
}
