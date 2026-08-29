export function normalizePath(path: string): string {
  return path.replace(/\/$/, '') || '/';
}

/** Split a nav path that may include a query string (`/settings?tab=billing`). */
export function splitNavPath(path: string): { pathname: string; search: string } {
  const trimmed = path.trim();
  const queryIndex = trimmed.indexOf('?');
  if (queryIndex < 0) {
    return { pathname: normalizePath(trimmed), search: '' };
  }
  return {
    pathname: normalizePath(trimmed.slice(0, queryIndex)),
    search: trimmed.slice(queryIndex),
  };
}

export function navPathname(path: string): string {
  return splitNavPath(path).pathname;
}

const JOURNEY_ROUTE_PARENTS = ['/my-bookings', '/prospects', '/counselling'];

export function isJourneyRoute(path: string): boolean {
  return /^\/journey\/\d+$/.test(normalizePath(path));
}

export function isAllowedRoute(currentPath: string, allowedRoutes: string[]): boolean {
  const path = navPathname(currentPath);

  if (isJourneyRoute(path)) {
    return JOURNEY_ROUTE_PARENTS.some(route => isAllowedRoute(route, allowedRoutes));
  }

  if (allowedRoutes.includes(path)) return true;

  // Invoice Workspace lives under Admin → Accounts with billing settings.
  // Allow it whenever Settings is allowed so the submenu appears before/without
  // a separate /invoices RBAC row (seed still recommended for Access Control).
  if (
    (path === '/invoices' || path.startsWith('/invoices/')) &&
    allowedRoutes.includes('/settings')
  ) {
    return true;
  }

  if (
    (path === '/express-leads' || path.startsWith('/express-leads/')) &&
    allowedRoutes.includes('/offline-leads')
  ) {
    return true;
  }

  return allowedRoutes.some(route => {
    if (route === '/') return false;
    const base = normalizePath(route);
    return path === base || path.startsWith(`${base}/`);
  });
}

export function isRouteActive(currentPath: string, routePath: string): boolean {
  const path = navPathname(currentPath);
  const route = navPathname(routePath);
  if (route === '/') return path === '/';
  return path === route || path.startsWith(`${route}/`);
}

/**
 * Active state for sidebar/mega links that may include query params.
 * Path-only `/settings` matches organization (no tab / tab=organization).
 */
export function isNavLinkActive(
  pathname: string,
  search: string,
  linkPath: string
): boolean {
  const currentPath = normalizePath(pathname);
  const { pathname: routePath, search: routeSearch } = splitNavPath(linkPath);
  if (!isRouteActive(currentPath, routePath)) return false;

  const currentParams = new URLSearchParams(
    search.startsWith('?') ? search.slice(1) : search
  );
  const linkParams = new URLSearchParams(
    routeSearch.startsWith('?') ? routeSearch.slice(1) : routeSearch
  );

  if (![...linkParams.keys()].length) {
    // Bare /settings = Organization tab (default when tab is absent).
    if (routePath === '/settings') {
      const tab = currentParams.get('tab');
      return !tab || tab === 'organization';
    }
    return true;
  }

  for (const [key, value] of linkParams.entries()) {
    if (currentParams.get(key) !== value) return false;
  }
  return true;
}
