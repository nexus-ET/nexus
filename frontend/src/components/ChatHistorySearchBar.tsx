import React from 'react';
import { ChevronDown, ChevronUp, Loader2, Search, X } from 'lucide-react';

interface ChatHistorySearchBarProps {
  query: string;
  onQueryChange: (value: string) => void;
  loading: boolean;
  error: string | null;
  matchCount: number;
  matchIndex: number;
  onPrevious: () => void;
  onNext: () => void;
  recentSearches?: string[];
  showRecent?: boolean;
  onFocus?: () => void;
  onBlur?: () => void;
  onSelectRecent?: (value: string) => void;
}

const ChatHistorySearchBar: React.FC<ChatHistorySearchBarProps> = ({
  query,
  onQueryChange,
  loading,
  error,
  matchCount,
  matchIndex,
  onPrevious,
  onNext,
  recentSearches = [],
  showRecent = false,
  onFocus,
  onBlur,
  onSelectRecent,
}) => {
  const hasQuery = Boolean(query.trim());
  const hasMatches = matchCount > 0;
  const atFirst = matchIndex <= 0;
  const atLast = matchIndex >= matchCount - 1;

  return (
    <div className="border-b border-border bg-incoming/40 px-3 py-2">
      <div className="flex items-center gap-2">
        <div className="relative min-w-0 flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-text-primary/60" />
          <input
            value={query}
            onChange={event => onQueryChange(event.target.value)}
            onFocus={onFocus}
            onBlur={onBlur}
            placeholder="Search this conversation..."
            className="w-full rounded-lg border border-border bg-white py-1.5 pl-8 pr-8 text-sm text-text-primary outline-none focus:border-primary focus:ring-2 focus:ring-primary"
          />
          {loading ? (
            <Loader2 className="absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-primary" />
          ) : (
            hasQuery && (
              <button
                type="button"
                onClick={() => onQueryChange('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 text-text-primary/60 hover:bg-outgoing hover:text-text-primary"
                title="Clear search"
                aria-label="Clear search"
              >
                <X className="h-4 w-4" />
              </button>
            )
          )}
        </div>

        {hasMatches && (
          <div className="flex shrink-0 items-center gap-1">
            <span className="min-w-[3.25rem] text-center text-[11px] font-medium tabular-nums text-text-primary/70">
              {matchIndex + 1}/{matchCount}
            </span>
            <button
              type="button"
              onClick={onPrevious}
              disabled={atFirst}
              className="rounded-md border border-border bg-white p-1 text-text-primary hover:bg-outgoing disabled:cursor-not-allowed disabled:opacity-40"
              title="Previous match"
              aria-label="Previous match"
            >
              <ChevronUp className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={onNext}
              disabled={atLast}
              className="rounded-md border border-border bg-white p-1 text-text-primary hover:bg-outgoing disabled:cursor-not-allowed disabled:opacity-40"
              title="Next match"
              aria-label="Next match"
            >
              <ChevronDown className="h-4 w-4" />
            </button>
          </div>
        )}
      </div>

      {showRecent && !hasQuery && recentSearches.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {recentSearches.map(item => (
            <button
              key={item}
              type="button"
              onMouseDown={event => {
                event.preventDefault();
                onSelectRecent?.(item);
              }}
              className="rounded-full border border-border bg-white px-2 py-0.5 text-[11px] text-text-primary hover:bg-outgoing"
            >
              {item}
            </button>
          ))}
        </div>
      )}

      {error && <p className="mt-1.5 text-xs text-red-600">{error}</p>}

      {!loading && !error && hasQuery && !hasMatches && (
        <p className="mt-1.5 text-xs text-text-primary/70">
          No messages match &ldquo;{query.trim()}&rdquo;. Check your spelling or try searching for a
          student name.
        </p>
      )}
    </div>
  );
};

export default ChatHistorySearchBar;
