/** Cross-page signal: NZ/CA Mapping Review applied PEMs → Programs should refetch. */

export const PEM_MAPPINGS_CHANGED_EVENT = 'nexus:pem-mappings-changed';
export const PEM_MAPPINGS_CHANGED_AT_KEY = 'nexus:pem-mappings-changed-at';

export function notifyPemMappingsChanged(): void {
  const at = String(Date.now());
  try {
    sessionStorage.setItem(PEM_MAPPINGS_CHANGED_AT_KEY, at);
  } catch {
    /* private mode / quota */
  }
  window.dispatchEvent(new CustomEvent(PEM_MAPPINGS_CHANGED_EVENT, { detail: { at } }));
}

export function readPemMappingsChangedAt(): string | null {
  try {
    return sessionStorage.getItem(PEM_MAPPINGS_CHANGED_AT_KEY);
  } catch {
    return null;
  }
}
