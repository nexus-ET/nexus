import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2, Search, X } from 'lucide-react';
import { useAcademiaSearch } from '../../hooks/useAcademiaSearch';

interface AcademiaCommandPaletteProps {
  open: boolean;
  onClose: () => void;
}

const AcademiaCommandPalette: React.FC<AcademiaCommandPaletteProps> = ({ open, onClose }) => {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const { query, setQuery, results, loading, error, reset } = useAcademiaSearch(open);

  useEffect(() => {
    if (!open) return undefined;
    reset();
    const timeout = window.setTimeout(() => inputRef.current?.focus(), 0);
    return () => window.clearTimeout(timeout);
  }, [open, reset]);

  useEffect(() => {
    if (!open) return undefined;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  const handleSelect = (path: string) => {
    onClose();
    navigate(path);
  };

  return (
    <div className="fixed inset-0 z-[120] flex items-start justify-center bg-black/50 p-4 pt-[12vh] backdrop-blur-sm">
      <div className="w-full max-w-2xl overflow-hidden rounded-2xl border border-border-subtle bg-card shadow-2xl">
        <div className="flex items-center gap-3 border-b border-border-subtle px-4 py-3">
          <Search size={18} className="text-text-muted" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={event => setQuery(event.target.value)}
            placeholder="Search countries, degrees, institutions, programs, courses..."
            className="flex-1 bg-transparent text-sm text-text-main outline-none placeholder:text-text-muted/70"
          />
          {loading && <Loader2 size={16} className="animate-spin text-text-muted" />}
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-text-muted transition-colors hover:bg-surface-bg hover:text-text-main"
            aria-label="Close search"
          >
            <X size={16} />
          </button>
        </div>

        <div className="max-h-[50vh] overflow-y-auto p-2">
          {query.trim().length < 2 ? (
            <div className="px-3 py-6 text-center text-sm text-text-muted">
              Type at least 2 characters to search Academia Hub entities.
            </div>
          ) : error ? (
            <div className="px-3 py-6 text-center text-sm text-alert">{error}</div>
          ) : results.length === 0 && !loading ? (
            <div className="px-3 py-6 text-center text-sm text-text-muted">No matching entities found.</div>
          ) : (
            <ul className="space-y-1">
              {results.map(result => (
                <li key={`${result.entity_type}-${result.id}`}>
                  <button
                    type="button"
                    onClick={() => handleSelect(result.path)}
                    className="flex w-full items-start justify-between gap-3 rounded-xl px-3 py-2.5 text-left transition-colors hover:bg-surface-bg"
                  >
                    <div className="min-w-0">
                      <div className="truncate text-sm font-semibold text-text-main">
                        {result.entity_label}: {result.title}
                      </div>
                      {result.subtitle ? (
                        <div className="truncate text-xs text-text-muted">{result.subtitle}</div>
                      ) : null}
                    </div>
                    <span className="shrink-0 rounded-full bg-accent/10 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-accent">
                      {result.category}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
};

export default AcademiaCommandPalette;
