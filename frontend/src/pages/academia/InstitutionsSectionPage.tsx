import { Link, Outlet, useLocation, useOutletContext } from 'react-router-dom';
import {
  INSTITUTIONS_SECTION_PATH,
  INSTITUTIONS_TABS,
  getAcademiaSectionLabel,
} from '../../config/academiaHubNav';
import { isRouteActive } from '../../utils/routeAccess';
import AcademiaBreadcrumbs from '../../components/academia/AcademiaBreadcrumbs';
import type { AcademiaSectionTab } from '../../config/academiaHubNav';

const isInstitutionsTabActive = (pathname: string, tab: AcademiaSectionTab): boolean => {
  if (tab.key === 'directory') {
    return pathname === tab.path || pathname === `${tab.path}/`;
  }
  return isRouteActive(pathname, tab.path);
};

const InstitutionsSectionPage: React.FC = () => {
  const outletContext = useOutletContext();
  const { pathname } = useLocation();
  const onInstitutionCalendar = /\/academia\/institutions\/\d+\/intakes$/.test(pathname);
  const onDirectory =
    pathname === INSTITUTIONS_SECTION_PATH || pathname === `${INSTITUTIONS_SECTION_PATH}/`;

  return (
    <div className="space-y-4">
      {!onDirectory ? (
        <AcademiaBreadcrumbs
          items={[
            { label: getAcademiaSectionLabel('institutions'), path: INSTITUTIONS_SECTION_PATH },
            ...(onInstitutionCalendar ? [{ label: 'Academic Calendar' }] : []),
          ]}
        />
      ) : null}
      <div className="rounded-2xl border border-border-subtle bg-card shadow-sm">
        {onDirectory ? null : (
          <div className="border-b border-border-subtle px-6 py-4">
            <h2 className="text-xl font-bold text-text-main">Institutions</h2>
          </div>
        )}
        {INSTITUTIONS_TABS.length > 1 ? (
          <div className="border-b border-border-subtle px-6 pt-4">
            <nav className="-mb-px flex flex-wrap gap-1" aria-label="Institutions section tabs">
              {INSTITUTIONS_TABS.map(tab => {
                const active = isInstitutionsTabActive(pathname, tab);
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
        ) : null}
        <div className="p-6 pt-4">
          <Outlet context={outletContext} />
        </div>
      </div>
    </div>
  );
};

export default InstitutionsSectionPage;
