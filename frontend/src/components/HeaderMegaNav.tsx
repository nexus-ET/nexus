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
import { isNavLinkActive, normalizePath } from '../utils/routeAccess';

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
            className={`absolute left-0 top-full z-40 mt-2 overflow-hidden rounded-xl border border-border-subtle bg-card shadow-xl shadow-black/10 ${
              openModule.groups.filter(group => group.links.length > 0).length >= 3
                ? 'w-[min(96vw,76rem)]'
                : 'w-[min(94vw,60rem)]'
            }`}
          >
            <MegaPanel
              module={openModule}
              currentPath={currentPath}
              currentSearch={location.search}
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
  currentSearch,
  onNavigate,
}: {
  module: NavMegaModule;
  currentPath: string;
  currentSearch: string;
  onNavigate: () => void;
}) {
  const hasFeatured = module.featured.length > 0;
  const visibleGroups = module.groups.filter(group => group.links.length > 0);
  const hasGroups = visibleGroups.length > 0;
  const columnCount = (hasFeatured ? 1 : 0) + visibleGroups.length;

  const columnGridClass =
    columnCount >= 4
      ? 'grid-cols-1 sm:grid-cols-2 xl:grid-cols-4'
      : columnCount === 3
        ? 'grid-cols-1 sm:grid-cols-3'
        : columnCount === 2
          ? 'grid-cols-1 sm:grid-cols-2'
          : 'grid-cols-1';

  const renderGroupColumn = (
    title: string,
    links: NavMegaLink[],
    options?: { featured?: boolean; columnKey?: string }
  ) => (
    <div
      key={options?.columnKey || title || 'untitled'}
      className={`min-w-0 p-4 ${
        options?.featured ? 'bg-surface-bg/60' : ''
      }`}
    >
      {title ? (
        <p className="mb-2 px-2 text-sm font-semibold uppercase tracking-wider text-text-muted">
          {title}
        </p>
      ) : null}
      <ul className="space-y-0.5">
        {links.map(link => (
          <li key={link.path}>
            {options?.featured ? (
              <FeaturedLink
                link={link}
                currentPath={currentPath}
                currentSearch={currentSearch}
                onNavigate={onNavigate}
              />
            ) : (
              <SimpleLink
                link={link}
                currentPath={currentPath}
                currentSearch={currentSearch}
                onNavigate={onNavigate}
              />
            )}
          </li>
        ))}
      </ul>
    </div>
  );

  if (!hasFeatured && hasGroups) {
    return (
      <div className={`grid ${columnGridClass} divide-y divide-border-subtle sm:divide-x sm:divide-y-0`}>
        {visibleGroups.map(group => renderGroupColumn(group.title, group.links))}
      </div>
    );
  }

  if (!hasGroups) {
    return (
      <div className="p-4">
        <p className="mb-3 px-2 text-sm font-semibold uppercase tracking-wider text-text-muted">
          {module.label}
        </p>
        <ul className="space-y-1">
          {module.featured.map(link => (
            <li key={link.path}>
              <FeaturedLink
                link={link}
                currentPath={currentPath}
                currentSearch={currentSearch}
                onNavigate={onNavigate}
              />
            </li>
          ))}
        </ul>
      </div>
    );
  }

  // Featured + groups share equal-width columns (Admin: Settings | Accounts | Access).
  return (
    <div className={`grid ${columnGridClass} divide-y divide-border-subtle sm:divide-x sm:divide-y-0`}>
      {hasFeatured ? renderGroupColumn(module.label, module.featured, { featured: true }) : null}
      {visibleGroups.map(group => renderGroupColumn(group.title, group.links))}
    </div>
  );
}

function FeaturedLink({
  link,
  currentPath,
  currentSearch,
  onNavigate,
}: {
  link: NavMegaLink;
  currentPath: string;
  currentSearch: string;
  onNavigate: () => void;
}) {
  const Icon = link.icon;
  const active = isNavLinkActive(currentPath, currentSearch, link.path);

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
      <span className="min-w-0 flex-1">
        <span className="block truncate text-base font-semibold leading-tight">{link.label}</span>
        {link.description && (
          <span className="mt-0.5 block line-clamp-2 text-sm leading-snug text-text-muted">
            {link.description}
          </span>
        )}
      </span>
    </Link>
  );
}

function SimpleLink({
  link,
  currentPath,
  currentSearch,
  onNavigate,
}: {
  link: NavMegaLink;
  currentPath: string;
  currentSearch: string;
  onNavigate: () => void;
}) {
  const Icon = link.icon;
  const active = isNavLinkActive(currentPath, currentSearch, link.path);
  return (
    <Link
      to={link.path}
      onClick={onNavigate}
      className={`flex gap-3 rounded-md px-2 py-2 transition-colors ${
        link.nested ? 'ml-5' : ''
      } ${
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
      <span className="min-w-0 flex-1">
        <span className="block truncate text-base font-medium text-text-main">{link.label}</span>
        {link.description && (
          <span className="block line-clamp-2 text-sm text-text-muted">{link.description}</span>
        )}
      </span>
    </Link>
  );
}

export default HeaderMegaNav;
