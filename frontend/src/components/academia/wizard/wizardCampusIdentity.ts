import type { WizardCampusItem } from '../../../schemas/wizard/step2-campus';
import type { WizardCollegeCampusLink } from './CollegeCampusLinkPanel';

function normalizeCampusKey(value: string | number | null | undefined): string {
  if (value == null) return '';
  return String(value).trim().toLowerCase();
}

/** Canonical draft key for a Step 2 campus row. */
export function resolveCampusDraftKey(campus: WizardCampusItem): string {
  return (
    campus.local_id?.trim() ||
    (campus.id != null ? String(campus.id) : '') ||
    campus.name.trim()
  );
}

export function resolveCampusDraftKeys(campus: WizardCampusItem): Set<string> {
  const keys = new Set<string>();
  const localId = campus.local_id?.trim();
  if (localId) keys.add(normalizeCampusKey(localId));
  if (campus.id != null) keys.add(normalizeCampusKey(campus.id));
  if (campus.name?.trim()) keys.add(normalizeCampusKey(campus.name));
  return keys;
}

export function resolveCampusLinkKeys(link: WizardCollegeCampusLink): Set<string> {
  const keys = new Set<string>();
  if (link.campus_local_id?.trim()) {
    keys.add(normalizeCampusKey(link.campus_local_id));
  }
  if (link.campus_id != null) {
    keys.add(normalizeCampusKey(link.campus_id));
  }
  if (link.name?.trim()) {
    keys.add(normalizeCampusKey(link.name));
  }
  return keys;
}

export function campusLinksMatch(
  left: WizardCollegeCampusLink,
  right: WizardCollegeCampusLink
): boolean {
  const leftKeys = resolveCampusLinkKeys(left);
  return [...resolveCampusLinkKeys(right)].some(key => leftKeys.has(key));
}

export function isWizardCampusLinked(
  campus: WizardCampusItem,
  linkedCampuses: WizardCollegeCampusLink[]
): boolean {
  const campusKeys = resolveCampusDraftKeys(campus);
  return linkedCampuses.some(link =>
    [...resolveCampusLinkKeys(link)].some(key => campusKeys.has(key))
  );
}

export function findCampusDraftForLink(
  campuses: WizardCampusItem[],
  link: WizardCollegeCampusLink
): WizardCampusItem | undefined {
  const linkKeys = resolveCampusLinkKeys(link);
  return campuses.find(campus =>
    [...resolveCampusDraftKeys(campus)].some(key => linkKeys.has(key))
  );
}

export function findCampusDraftByKey(
  campuses: WizardCampusItem[],
  key: string
): WizardCampusItem | undefined {
  const normalized = normalizeCampusKey(key);
  return campuses.find(campus =>
    [...resolveCampusDraftKeys(campus)].some(draftKey => draftKey === normalized)
  );
}

export function mergeUniqueCampusLinks(
  current: WizardCollegeCampusLink[],
  incoming: WizardCollegeCampusLink[],
  campuses: WizardCampusItem[]
): WizardCollegeCampusLink[] {
  const merged = [...current];
  for (const link of incoming) {
    const draftCampus = findCampusDraftForLink(campuses, link);
    if (draftCampus && isWizardCampusLinked(draftCampus, merged)) {
      continue;
    }
    if (merged.some(existing => campusLinksMatch(existing, link))) {
      continue;
    }
    merged.push(link);
  }
  return merged;
}
