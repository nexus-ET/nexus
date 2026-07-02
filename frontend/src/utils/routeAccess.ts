export function normalizePath(path: string): string {
  return path.replace(/\/$/, '') || '/';
}

const JOURNEY_ROUTE_PARENTS = ['/my-bookings', '/prospects', '/counselling'];

export function isJourneyRoute(path: string): boolean {
  return /^\/journey\/\d+$/.test(normalizePath(path));
}

export function isAllowedRoute(currentPath: string, allowedRoutes: string[]): boolean {
  const path = normalizePath(currentPath);

  if (isJourneyRoute(path)) {
    return JOURNEY_ROUTE_PARENTS.some(route => isAllowedRoute(route, allowedRoutes));
  }

  if (allowedRoutes.includes(path)) return true;

  return allowedRoutes.some(route => {
    if (route === '/') return false;
    const base = normalizePath(route);
    return path === base || path.startsWith(`${base}/`);
  });
}

export function isRouteActive(currentPath: string, routePath: string): boolean {
  const path = normalizePath(currentPath);
  const route = normalizePath(routePath);
  if (route === '/') return path === '/';
  return path === route || path.startsWith(`${route}/`);
}
