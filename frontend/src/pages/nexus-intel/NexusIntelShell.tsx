import { NavLink, Outlet, useOutletContext, Navigate, useLocation } from 'react-router-dom';
import { Brain } from 'lucide-react';
import { NEXUS_INTEL_NAV } from '../../config/nexusIntelNav';
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

const NexusIntelShell: React.FC = () => {
  const context = useOutletContext<ShellContext>();
  const location = useLocation();
  const isChatWorkspace = /\/ai-assistant\/?$/.test(location.pathname);
  const isImmersiveWorkspace = isChatWorkspace;

  if (context?.sessionReady === false) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-text-muted">Loading…</div>
    );
  }

  if (context?.allowedRoutes && !isAllowedRoute('/nexus-intel', context.allowedRoutes)) {
    return <Navigate to="/" replace />;
  }

  return (
    <div className="relative z-10 mx-auto flex h-full min-h-0 w-full max-w-none flex-col gap-3">
      <header className={`shrink-0 space-y-2 ${isImmersiveWorkspace ? 'pb-0' : ''}`}>
        <div className="inline-flex items-center gap-2 rounded-full border border-border-subtle bg-card px-3 py-1 text-xs font-semibold uppercase tracking-wide text-text-muted">
          <Brain size={14} />
          Living knowledge hub
        </div>
        <h1 className={`font-extrabold tracking-tight text-text-main ${isImmersiveWorkspace ? 'text-xl' : 'text-2xl'}`}>
          IntelX
        </h1>
        {!isImmersiveWorkspace ? (
          <p className="max-w-3xl text-sm text-text-muted">
            Dynamic compliance terminology, workflow calculators, micro-learning, and regulatory
            change tracking for counselors.
          </p>
        ) : null}
      </header>

      <nav
        className={`flex shrink-0 gap-2 overflow-x-auto border-b border-border-subtle [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden ${
          isImmersiveWorkspace ? 'pb-2' : 'pb-3'
        }`}
      >
        {NEXUS_INTEL_NAV.filter(item => {
          if (item.key !== 'admin') return true;
          const role =
            context?.currentUser?.admin_role?.name || context?.currentUser?.role || '';
          return Boolean(context?.currentUser?.is_superuser) || role === 'Web Admin';
        }).map(item => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.key}
              to={item.path}
              className={({ isActive }) =>
                `inline-flex shrink-0 items-center gap-2 rounded-xl border px-3 py-2 text-sm font-semibold transition-colors ${
                  isActive
                    ? 'border-accent/40 bg-accent/10 text-text-main'
                    : 'border-border-subtle bg-card text-text-muted hover:text-text-main'
                }`
              }
            >
              <Icon size={15} />
              {item.label}
            </NavLink>
          );
        })}
      </nav>

      {isImmersiveWorkspace ? (
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

export default NexusIntelShell;
