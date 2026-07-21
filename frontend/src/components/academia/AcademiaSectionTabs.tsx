import { Link, useLocation } from 'react-router-dom';
import { isRouteActive } from '../../utils/routeAccess';
import type { AcademiaSectionTab } from '../../config/academiaHubNav';

interface AcademiaSectionTabsProps {
  tabs: AcademiaSectionTab[];
}

const AcademiaSectionTabs: React.FC<AcademiaSectionTabsProps> = ({ tabs }) => {
  const { pathname } = useLocation();

  return (
    <div className="border-b border-border-subtle">
      <nav className="-mb-px flex flex-wrap gap-1" aria-label="Section tabs">
        {tabs.map(tab => {
          const active = isRouteActive(pathname, tab.path);
          return (
            <Link
              key={tab.key}
              to={tab.path}
              className={`rounded-t-xl px-4 py-2.5 text-sm font-semibold transition-colors ${
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
    </div>
  );
};

export default AcademiaSectionTabs;
