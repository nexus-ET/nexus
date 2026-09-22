/** Safe href for Intel AI source / markdown links. */

const UNSAFE_SCHEME = /^(javascript|data|vbscript|file):/i;
const APP_PATH =
  /^\/(academia|nexus-intel|prospects|express-leads|offline-leads|my-bookings|book-appointment|students|flowx)(\/|\?|$)/i;

function appOrigin(origin?: string): string {
  if (origin) return origin.replace(/\/$/, '');
  if (typeof window !== 'undefined' && window.location?.origin) {
    return window.location.origin.replace(/\/$/, '');
  }
  return '';
}

/** Return an absolute http(s) URL, or null if the value is empty/unsafe. */
export function sourceHref(url?: string | null, origin?: string): string | null {
  if (!url) return null;
  const trimmed = url.trim().replace(/^<|>$/g, '').trim();
  if (!trimmed || UNSAFE_SCHEME.test(trimmed)) return null;
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  if (trimmed.startsWith('//') && trimmed.length > 2) return `https:${trimmed}`;
  if (trimmed.startsWith('/') && !trimmed.startsWith('//')) {
    if (!APP_PATH.test(trimmed)) return null;
    const base = appOrigin(origin);
    return base ? `${base}${trimmed}` : trimmed;
  }
  if (trimmed.includes(' ')) return null;
  const host = trimmed.split('/')[0].split('?')[0];
  if (host.includes('.') && !host.startsWith('.') && !host.includes(':')) {
    return `https://${trimmed.replace(/^\/+/, '')}`;
  }
  return null;
}

export function displaySourceUrl(url: string, origin?: string): string {
  try {
    const parsed = new URL(url);
    const path = `${parsed.pathname}${parsed.search}`.replace(/\/$/, '');
    const sameOrigin = appOrigin(origin) === parsed.origin;
    const hostPath = sameOrigin
      ? path || '/'
      : `${parsed.host}${path === '/' ? '' : path}`;
    return hostPath.length > 64 ? `${hostPath.slice(0, 61)}…` : hostPath;
  } catch {
    return url.length > 64 ? `${url.slice(0, 61)}…` : url;
  }
}
