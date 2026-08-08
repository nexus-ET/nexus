import { NavLink, Outlet, useOutletContext, Navigate, useLocation } from 'react-router-dom';
import { GitBranch } from 'lucide-react';
import { FLOWX_NAV_GROUPS } from '../../config/flowxNav';
import { isAllowedRoute } from '../../utils/routeAccess';
import HeadlessScrollArea from '../../components/HeadlessScrollArea';

interface ShellContext {
  allowedRoutes?: string[] | null;
  sessionReady?: boolean;
  currentUser?: {
    role?: string | null;
    admin_role?: { name?: string | null } | null;
    is_superuser?: boolean;
  } | null;
}

const FlowxShell: React.FC = () => {
  const context = useOutletContext<ShellContext>();
  const location = useLocation();
  const isWide =
    location.pathname === '/flowx' ||
    location.pathname === '/flowx/ops' ||
    location.pathname.startsWith('/flowx/ops/') ||
    location.pathname === '/flowx/board' ||
    location.pathname === '/flowx/master' ||
    location.pathname === '/flowx/countries' ||
    location.pathname === '/flowx/journeys' ||
    location.pathname.startsWith('/flowx/journeys/') ||
    location.pathname.startsWith('/flowx/countries/');

  if (context?.sessionReady === false) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-text-muted">Loading…</div>
    );
  }

  if (context?.allowedRoutes && !isAllowedRoute('/flowx', context.allowedRoutes)) {
    return <Navigate to="/" replace />;
  }

  const role = context?.currentUser?.admin_role?.name || context?.currentUser?.role || '';
  const canSeeMaster =
    Boolean(context?.currentUser?.is_superuser) || role === 'Super Admin';

  return (
    <div className="relative z-10 mx-auto flex h-full min-h-0 w-full max-w-none flex-col gap-3">
      <header className={`shrink-0 space-y-2 ${isWide ? 'pb-0' : ''}`}>
        <div className="inline-flex items-center gap-2 rounded-full border border-border-subtle bg-card px-3 py-1 text-xs font-semibold uppercase tracking-wide text-text-muted">
          <GitBranch size={14} />
          Overseas process engine
        </div>
        <h1 className={`font-extrabold tracking-tight text-text-main ${isWide ? 'text-xl' : 'text-2xl'}`}>
          FlowX
        </h1>
        {!isWide ? (
          <p className="max-w-3xl text-sm text-text-muted">
            Operate candidate journeys country-by-country, or configure Master and country process
            templates.
          </p>
        ) : null}
      </header>

      <nav
        className={`flex shrink-0 flex-col gap-2 border-b border-border-subtle ${
          isWide ? 'pb-2' : 'pb-3'
        }`}
      >
        {FLOWX_NAV_GROUPS.map(group => {
          const items = group.items.filter(item => !item.superAdminOnly || canSeeMaster);
          if (!items.length) return null;
          return (
            <div key={group.key} className="flex min-w-0 items-center gap-2 overflow-x-auto [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
              <span className="shrink-0 text-[10px] font-bold uppercase tracking-wide text-text-muted">
                {group.label}
              </span>
              <div className="flex gap-2">
                {items.map(item => {
                  const Icon = item.icon;
                  const active =
                    item.key === 'ops'
                      ? location.pathname === '/flowx' ||
                        location.pathname === '/flowx/ops' ||
                        /^\/flowx\/ops\/[A-Za-z]{2}$/i.test(location.pathname)
                      : item.key === 'countries'
                        ? location.pathname === '/flowx/countries' ||
                          location.pathname.startsWith('/flowx/countries/')
                        : location.pathname === item.path ||
                          location.pathname.startsWith(`${item.path}/`);
                  return (
                    <NavLink
                      key={item.key}
                      to={item.path}
                      className={`inline-flex shrink-0 items-center gap-2 rounded-xl border px-3 py-2 text-sm font-semibold transition-colors ${
                        active
                          ? 'border-accent/40 bg-accent/10 text-text-main'
                          : 'border-border-subtle bg-card text-text-muted hover:text-text-main'
                      }`}
                    >
                      <Icon size={15} />
                      {item.label}
                    </NavLink>
                  );
                })}
              </div>
            </div>
          );
        })}
      </nav>

      {isWide ? (
        <div className="min-h-0 flex-1 overflow-hidden">
          <Outlet context={context} />
        </div>
      ) : (
        <HeadlessScrollArea className="min-h-0 flex-1" viewportClassName="pb-8 pr-1">
          <Outlet context={context} />
        </HeadlessScrollArea>
      )}
    </div>
  );
};

export default FlowxShell;
