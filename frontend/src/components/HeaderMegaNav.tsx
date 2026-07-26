import React, { useEffect, useId, useMemo, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ChevronDown } from 'lucide-react';
import {
  findModuleForPath,
  getAppNavModules,
  isModuleActive,
  type NavAccessContext,
  type NavMegaLink,
  type NavMegaModule,
} from '../config/appNavModules';
import { isRouteActive, normalizePath } from '../utils/routeAccess';

interface HeaderMegaNavProps {
  allowedRoutes: string[] | null;
  currentUser: NavAccessContext['currentUser'];
  /** Currently selected top-level module shown in the left nav. */
  activeModuleId: string | null;
  onModuleSelect: (moduleId: string) => void;
}

/**
 * GitHub-style header mega menu: top labels open a wide panel, and also
 * load that module's sub-menus into the left sidebar.
 */
const HeaderMegaNav: React.FC<HeaderMegaNavProps> = ({
  allowedRoutes,
  currentUser,
  activeModuleId,
  onModuleSelect,
}) => {
  const location = useLocation();
  const currentPath = normalizePath(location.pathname);
  const [openId, setOpenId] = useState<string | null>(null);
  const rootRef = useRef<HTMLElement>(null);
  const baseId = useId();

  const roleName = currentUser?.admin_role?.name || currentUser?.role || '';
  const modules = useMemo(
    () =>
      getAppNavModules({
        allowedRoutes,
        roleName,
        currentUser,
      }),
    [allowedRoutes, roleName, currentUser]
  );

  useEffect(() => {
    setOpenId(null);
  }, [location.pathname]);

  useEffect(() => {
    if (!openId) return;

    const onPointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpenId(null);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpenId(null);
    };

    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [openId]);

  if (allowedRoutes === null || modules.length === 0) {
    return null;
  }

  const pathModule = findModuleForPath(modules, currentPath);
  const selectedId = activeModuleId ?? pathModule?.id ?? null;
  const openModule = modules.find(module => module.id === openId) ?? null;

  const handleModuleClick = (moduleId: string) => {
    const nextOpen = openId === moduleId ? null : moduleId;
    setOpenId(nextOpen);
    onModuleSelect(moduleId);
  };

  return (
    <nav ref={rootRef} className="relative hidden lg:flex items-center gap-0.5" aria-label="Primary">
      {modules.map(module => {
        const isOpen = openId === module.id;
        const isSelected = selectedId === module.id;
        const isActive = isModuleActive(module, currentPath);
        const panelId = `${baseId}-${module.id}-panel`;

        return (
          <div key={module.id} className="relative">
            <button
              type="button"
              aria-expanded={isOpen}
              aria-controls={panelId}
              aria-haspopup="true"
              aria-pressed={isSelected}
              onClick={() => handleModuleClick(module.id)}
              className={`inline-flex items-center gap-1 rounded-md px-2.5 py-1.5 text-base font-medium transition-colors ${
                isOpen || isSelected || isActive
                  ? 'bg-white/15 text-white'
                  : 'text-white/85 hover:bg-white/10 hover:text-white'
              }`}
            >
              {module.label}
              <ChevronDown
                size={15}
                className={`opacity-80 transition-transform ${isOpen ? 'rotate-180' : ''}`}
              />
            </button>
          </div>
        );
      })}

      {openModule && (
        <>
          <div
            className="fixed inset-0 top-16 z-30 bg-black/20"
            aria-hidden
            onClick={() => setOpenId(null)}
          />
          <div
            id={`${baseId}-${openModule.id}-panel`}
            role="region"
            aria-label={`${openModule.label} menu`}
            className="absolute left-0 top-full z-40 mt-2 w-[min(94vw,60rem)] overflow-hidden rounded-xl border border-border-subtle bg-card shadow-xl shadow-black/10"
          >
            <MegaPanel
              module={openModule}
              currentPath={currentPath}
              onNavigate={() => setOpenId(null)}
            />
          </div>
        </>
      )}
    </nav>
  );
};

function MegaPanel({
  module,
  currentPath,
  onNavigate,
}: {
  module: NavMegaModule;
  currentPath: string;
  onNavigate: () => void;
}) {
  const hasGroups = module.groups.some(group => group.links.length > 0);

  return (
    <div className="grid grid-cols-1 md:grid-cols-2">
      <div className="border-b border-border-subtle bg-surface-bg/60 p-4 md:border-b-0 md:border-r">
        <p className="mb-3 px-2 text-sm font-semibold uppercase tracking-wider text-text-muted">
          {module.label}
        </p>
        <ul className="space-y-1">
          {module.featured.map(link => (
            <li key={link.path}>
              <FeaturedLink link={link} currentPath={currentPath} onNavigate={onNavigate} />
            </li>
          ))}
        </ul>
      </div>

      <div className="grid gap-6 p-4 sm:grid-cols-2">
        {hasGroups ? (
          module.groups.map(group => (
            <div key={group.title}>
              <p className="mb-2 px-2 text-sm font-semibold uppercase tracking-wider text-text-muted">
                {group.title}
              </p>
              <ul className="space-y-0.5">
                {group.links.map(link => (
                  <li key={link.path}>
                    <SimpleLink link={link} currentPath={currentPath} onNavigate={onNavigate} />
                  </li>
                ))}
              </ul>
            </div>
          ))
        ) : (
          <div className="px-2 py-6 text-sm text-text-muted sm:col-span-2">
            Choose an item from the list on the left.
          </div>
        )}
      </div>
    </div>
  );
}

function FeaturedLink({
  link,
  currentPath,
  onNavigate,
}: {
  link: NavMegaLink;
  currentPath: string;
  onNavigate: () => void;
}) {
  const Icon = link.icon;
  const active = isRouteActive(currentPath, link.path);

  return (
    <Link
      to={link.path}
      onClick={onNavigate}
      className={`flex gap-3 rounded-lg px-2 py-2.5 transition-colors ${
        active ? 'bg-accent/10 text-text-main' : 'text-text-main hover:bg-card'
      }`}
    >
      <span
        className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border ${
          active ? 'border-accent/30 bg-accent/10 text-accent' : 'border-border-subtle bg-card text-text-muted'
        }`}
      >
        {Icon ? <Icon size={16} /> : <span className="text-xs font-bold">{link.label[0]}</span>}
      </span>
      <span className="min-w-0">
        <span className="block text-base font-semibold leading-tight">{link.label}</span>
        {link.description && (
          <span className="mt-0.5 block text-sm leading-snug text-text-muted">{link.description}</span>
        )}
      </span>
    </Link>
  );
}

function SimpleLink({
  link,
  currentPath,
  onNavigate,
}: {
  link: NavMegaLink;
  currentPath: string;
  onNavigate: () => void;
}) {
  const Icon = link.icon;
  const active = isRouteActive(currentPath, link.path);
  return (
    <Link
      to={link.path}
      onClick={onNavigate}
      className={`flex gap-3 rounded-md px-2 py-2 transition-colors ${
        active
          ? 'bg-accent/10 font-medium text-text-main'
          : 'text-text-muted hover:bg-surface-bg hover:text-text-main'
      }`}
    >
      <span
        className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border ${
          active
            ? 'border-accent/30 bg-accent/10 text-accent'
            : 'border-border-subtle bg-surface-bg text-text-muted'
        }`}
      >
        {Icon ? <Icon size={16} /> : <span className="text-xs font-bold">{link.label[0]}</span>}
      </span>
      <span className="min-w-0">
        <span className="block text-base font-medium text-text-main">{link.label}</span>
        {link.description && (
          <span className="block text-sm text-text-muted">{link.description}</span>
        )}
      </span>
    </Link>
  );
}

export default HeaderMegaNav;
