import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../utils/api';
import type { AcademiaSearchResult } from '../types/academiaHub';

export function useAcademiaSearch(enabled: boolean) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<AcademiaSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled || query.trim().length < 2) {
      setResults([]);
      setLoading(false);
      setError(null);
      return undefined;
    }

    const controller = new AbortController();
    const timeout = window.setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const encoded = encodeURIComponent(query.trim());
        const data = await apiFetch<AcademiaSearchResult[]>(
          `academia/search?q=${encoded}&limit=25`,
          { signal: controller.signal }
        );
        setResults(Array.isArray(data) ? data : []);
      } catch (err) {
        if ((err as Error).name === 'AbortError') return;
        setResults([]);
        setError(err instanceof Error ? err.message : 'Search failed');
      } finally {
        setLoading(false);
      }
    }, 250);

    return () => {
      controller.abort();
      window.clearTimeout(timeout);
    };
  }, [enabled, query]);

  const reset = useCallback(() => {
    setQuery('');
    setResults([]);
    setError(null);
  }, []);

  return { query, setQuery, results, loading, error, reset };
}
