import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { apiFetch, getStoredToken } from '../utils/api';

export interface ChatHistorySearchResult {
  message_id: number;
  conversation_id: number;
  snippet: string;
  timestamp: string;
  conversation_name: string;
}

const RECENT_SEARCHES_KEY = 'nexus.chat.recentSearches';
const MAX_RECENT_SEARCHES = 8;

const loadRecentSearches = (): string[] => {
  try {
    const raw = localStorage.getItem(RECENT_SEARCHES_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed)
      ? parsed.filter((item): item is string => typeof item === 'string').slice(0, MAX_RECENT_SEARCHES)
      : [];
  } catch {
    return [];
  }
};

const persistRecentSearch = (query: string): string[] => {
  const trimmed = query.trim();
  if (!trimmed) return loadRecentSearches();
  const next = [trimmed, ...loadRecentSearches().filter(item => item.toLowerCase() !== trimmed.toLowerCase())].slice(
    0,
    MAX_RECENT_SEARCHES
  );
  localStorage.setItem(RECENT_SEARCHES_KEY, JSON.stringify(next));
  return next;
};

export async function fetchChatHistorySearch(query: string): Promise<ChatHistorySearchResult[]> {
  const data = await apiFetch(`chat/search?query=${encodeURIComponent(query.trim())}`);
  return Array.isArray(data)
    ? (data as ChatHistorySearchResult[])
    : ((data as { results?: ChatHistorySearchResult[] }).results ?? []);
}

export function useChatHistorySearch() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<ChatHistorySearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recentSearches, setRecentSearches] = useState<string[]>(() => loadRecentSearches());
  const [showRecent, setShowRecent] = useState(false);
  const [resultIndex, setResultIndex] = useState(0);

  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      setError(null);
      setLoading(false);
      setResultIndex(0);
      return;
    }

    setLoading(true);
    setError(null);
    const timer = window.setTimeout(() => {
      void fetchChatHistorySearch(query)
        .then(nextResults => {
          setResults(nextResults);
          setResultIndex(0);
        })
        .catch(err => {
          setResults([]);
          setResultIndex(0);
          setError(err instanceof Error ? err.message : 'Message search failed.');
        })
        .finally(() => setLoading(false));
    }, 300);

    return () => window.clearTimeout(timer);
  }, [query]);

  const recordRecentSearch = useCallback((value: string) => {
    const trimmed = value.trim();
    if (!trimmed) return;
    setRecentSearches(persistRecentSearch(trimmed));
  }, []);

  const goToPrevious = useCallback(() => {
    setResultIndex(index => Math.max(0, index - 1));
  }, []);

  const goToNext = useCallback(() => {
    setResultIndex(index => Math.min(Math.max(results.length - 1, 0), index + 1));
  }, [results.length]);

  return {
    query,
    setQuery,
    results,
    loading,
    error,
    recentSearches,
    showRecent,
    setShowRecent,
    recordRecentSearch,
    resultIndex,
    setResultIndex,
    goToPrevious,
    goToNext,
  };
}

interface ChatConfigContextValue {
  chatMaxChars: number;
  loading: boolean;
  error: string | null;
  atLimit: (value: string) => boolean;
  overLimit: (value: string) => boolean;
  charsRemaining: (value: string) => number;
  refreshChatConfig: () => Promise<void>;
}

const ChatConfigContext = createContext<ChatConfigContextValue | null>(null);

async function loadChatMaxChars(): Promise<number> {
  const data = await apiFetch('chat/config');
  const max = Number((data as { chat_max_chars?: number }).chat_max_chars);
  if (!Number.isFinite(max) || max < 1) {
    throw new Error('Invalid chat config from server');
  }
  return max;
}

export const ChatConfigProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [chatMaxChars, setChatMaxChars] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refreshChatConfig = async () => {
    if (!getStoredToken()) {
      setLoading(false);
      setError('Not signed in');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const max = await loadChatMaxChars();
      setChatMaxChars(max);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load chat limits');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refreshChatConfig();
  }, []);

  const value = useMemo<ChatConfigContextValue>(() => {
    const limit = chatMaxChars > 0 ? chatMaxChars : 0;
    return {
      chatMaxChars: limit,
      loading,
      error,
      atLimit: (v: string) => limit > 0 && v.length >= limit,
      overLimit: (v: string) => limit > 0 && v.length > limit,
      charsRemaining: (v: string) => (limit > 0 ? Math.max(0, limit - v.length) : 0),
      refreshChatConfig,
    };
  }, [chatMaxChars, loading, error]);

  return <ChatConfigContext.Provider value={value}>{children}</ChatConfigContext.Provider>;
};

export function useChat(): ChatConfigContextValue {
  const context = useContext(ChatConfigContext);
  if (!context) {
    throw new Error('useChat must be used within ChatConfigProvider');
  }
  return context;
}
