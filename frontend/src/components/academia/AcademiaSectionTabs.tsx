import type { ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { isRouteActive } from '../../utils/routeAccess';
import type { AcademiaSectionTab } from '../../config/academiaHubNav';

interface AcademiaSectionTabsProps {
  tabs: AcademiaSectionTab[];
  actions?: ReactNode;
}

const AcademiaSectionTabs: React.FC<AcademiaSectionTabsProps> = ({ tabs, actions }) => {
  const { pathname } = useLocation();

  return (
    <div className="flex flex-wrap items-center gap-3 border-b border-border-subtle">
      <nav className="-mb-px flex min-w-0 flex-wrap gap-1" aria-label="Section tabs">
        {tabs.map(tab => {
          const active = isRouteActive(pathname, tab.path);
          return (
            <Link
              key={tab.key}
              to={tab.path}
              className={`rounded-t-xl px-4 py-2.5 text-sm font-semibold transition-colors ${
                tab.nested ? 'ml-1' : ''
              } ${
                active
                  ? 'border border-b-0 border-border-subtle bg-card text-accent'
                  : 'text-text-muted hover:bg-surface-bg hover:text-text-main'
              }`}
            >
              {tab.label}
            </Link>
          );
        })}
      </nav>
      {actions ? <div className="ml-auto shrink-0 pb-2">{actions}</div> : null}
    </div>
  );
};

export default AcademiaSectionTabs;
