import { useEffect } from 'react';
import { Outlet, useLocation, useOutletContext } from 'react-router-dom';
import { Search } from 'lucide-react';
import AcademiaBreadcrumbs from './AcademiaBreadcrumbs';

interface AcademiaHubLayoutProps {
  onOpenCommandPalette?: () => void;
}

const AcademiaHubLayout: React.FC<AcademiaHubLayoutProps> = ({ onOpenCommandPalette }) => {
  const outletContext = useOutletContext();
  const location = useLocation();

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        onOpenCommandPalette?.();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onOpenCommandPalette]);

  return (
    <div className="relative z-10 mx-auto flex h-full min-h-0 w-full max-w-none flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-2">
          <AcademiaBreadcrumbs
            items={[
              { label: 'Academia Hub', path: '/academia' },
            ]}
          />
          <div>
            <h1 className="text-2xl font-extrabold tracking-tight text-text-main">Academia Hub</h1>
            <p className="text-sm text-text-muted">
              Manage geography, institutions, and academic framework catalogs.
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={onOpenCommandPalette}
          className="inline-flex items-center gap-2 rounded-xl border border-border-subtle bg-card px-4 py-2 text-sm text-text-muted transition-colors hover:border-accent/40 hover:text-text-main"
        >
          <Search size={16} />
          <span>Search entities</span>
          <kbd className="rounded border border-border-subtle bg-surface-bg px-1.5 py-0.5 text-[10px] font-semibold uppercase">
            Ctrl+K
          </kbd>
        </button>
      </div>
      <Outlet key={location.pathname} context={outletContext} />
    </div>
  );
};

export default AcademiaHubLayout;
