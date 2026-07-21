import type { WizardCollegeItem } from '../../../schemas/wizard/step3-colleges';
import type { WizardPictureItem } from '../../../schemas/wizard/step6-pictures';

export type WizardPicturesEntityScope =
  | { type: 'institution' }
  | { type: 'college'; collegeLocalId: string; collegeName: string };

export function institutionScopeKey(): string {
  return 'institution';
}

export function collegeScopeKey(collegeLocalId: string): string {
  return `college:${collegeLocalId}`;
}

/** Stable college scope id — prefer local_id, fall back to name. */
export function resolveCollegeLocalId(
  college: Pick<WizardCollegeItem, 'local_id' | 'name'>
): string {
  const localId = college.local_id?.trim();
  if (localId) return localId;
  return (college.name || '').trim();
}

/**
 * Ensure each college has a unique local_id for picture scoping.
 * Prefers existing local_id, then name — same resolution as resolveCollegeLocalId.
 */
export function ensureUniqueCollegeLocalIds(
  colleges: WizardCollegeItem[]
): WizardCollegeItem[] {
  const used = new Set<string>();
  return colleges.map(college => {
    let localId = resolveCollegeLocalId(college);
    if (!localId) {
      localId = crypto.randomUUID();
    }
    const base = localId;
    let suffix = 2;
    while (used.has(localId)) {
      localId = `${base}-${suffix}`;
      suffix += 1;
    }
    used.add(localId);
    return localId === college.local_id ? college : { ...college, local_id: localId };
  });
}

/** Remap picture college_local_id values onto the ensured college local_ids (name → id). */
export function remapPictureCollegeLocalIds(
  pictures: WizardPictureItem[],
  colleges: WizardCollegeItem[]
): WizardPictureItem[] {
  const toCanonical = new Map<string, string>();
  for (const college of colleges) {
    const canonical = resolveCollegeLocalId(college);
    if (!canonical) continue;
    toCanonical.set(canonical, canonical);
    const name = college.name?.trim();
    if (name) toCanonical.set(name, canonical);
  }
  let changed = false;
  const next = pictures.map(picture => {
    const current = picture.college_local_id?.trim();
    if (!current) return picture;
    const mapped = toCanonical.get(current);
    if (!mapped || mapped === current) return picture;
    changed = true;
    return { ...picture, college_local_id: mapped };
  });
  return changed ? next : pictures;
}

/** Create missing college reference clones for university assets (cascade on). */
export function ensureCascadeCollegePictureClones(
  pictures: WizardPictureItem[],
  colleges: WizardCollegeItem[],
  collegeOverrides: Set<string>
): WizardPictureItem[] {
  const institutionPictures = pictures.filter(
    item => pictureScopeKey(item) === institutionScopeKey()
  );
  if (institutionPictures.length === 0 || colleges.length === 0) return pictures;

  const additions: WizardPictureItem[] = [];
  const seenCollegeIds = new Set<string>();
  for (const college of colleges) {
    const collegeLocalId = resolveCollegeLocalId(college);
    if (!collegeLocalId || seenCollegeIds.has(collegeLocalId)) continue;
    seenCollegeIds.add(collegeLocalId);
    if (collegeOverrides.has(collegeLocalId)) continue;
    const existingKeys = new Set(
      pictures
        .filter(item => pictureScopeKey(item) === collegeScopeKey(collegeLocalId))
        .map(pictureAssetKey)
        .filter(Boolean)
    );
    for (const picture of institutionPictures) {
      const assetKey = pictureAssetKey(picture);
      if (!assetKey || existingKeys.has(assetKey)) continue;
      existingKeys.add(assetKey);
      additions.push(clonePictureForCollege(picture, college));
    }
  }
  return additions.length > 0 ? [...pictures, ...additions] : pictures;
}

export function scopeKey(scope: WizardPicturesEntityScope): string {
  return scope.type === 'institution'
    ? institutionScopeKey()
    : collegeScopeKey(scope.collegeLocalId);
}

export function pictureScopeKey(
  picture: Pick<WizardPictureItem, 'college_id' | 'college_local_id'>
): string {
  if (picture.college_local_id?.trim()) {
    return collegeScopeKey(picture.college_local_id.trim());
  }
  if (picture.college_id) {
    return `college-id:${picture.college_id}`;
  }
  return institutionScopeKey();
}

/** Stable identity for the Cloudflare/local blob — shared across entity links. */
export function pictureAssetKey(
  picture: Pick<WizardPictureItem, 'storage_key' | 'url'>
): string {
  const key = picture.storage_key?.trim().replace(/^\/+/, '');
  if (key) return key;
  return picture.url?.trim() || '';
}

/** Stable UI selection key for a picture reference row. */
export function pictureSelectionKey(picture: WizardPictureItem): string {
  if (picture.local_id?.trim()) return picture.local_id.trim();
  return `${pictureAssetKey(picture)}|${pictureScopeKey(picture)}`;
}

export function filterPicturesForScope(
  pictures: WizardPictureItem[],
  scope: WizardPicturesEntityScope,
  options?: {
    collegeOverrides?: Set<string>;
    includeInherited?: boolean;
  }
): WizardPictureItem[] {
  const overrides = options?.collegeOverrides ?? new Set<string>();
  const includeInherited = options?.includeInherited ?? true;

  if (scope.type === 'institution') {
    return pictures.filter(item => pictureScopeKey(item) === institutionScopeKey());
  }

  const collegeKey = collegeScopeKey(scope.collegeLocalId);
  const hasOverride = overrides.has(scope.collegeLocalId);
  const collegeOwnedRaw = pictures.filter(item => pictureScopeKey(item) === collegeKey);
  // Guard against accidental duplicate cascade clones for the same asset.
  const collegeOwned: WizardPictureItem[] = [];
  const seenOwned = new Set<string>();
  for (const item of collegeOwnedRaw) {
    const assetKey = pictureAssetKey(item);
    if (!assetKey) {
      collegeOwned.push(item);
      continue;
    }
    if (seenOwned.has(assetKey)) continue;
    seenOwned.add(assetKey);
    collegeOwned.push(item);
  }

  if (hasOverride || !includeInherited) {
    return collegeOwned;
  }

  // Cascade clones share the same storage_key/url as the university asset.
  // Prefer the college-owned reference and hide the inherited duplicate.
  const ownedAssetKeys = new Set(
    collegeOwned.map(pictureAssetKey).filter(Boolean)
  );
  const inherited = pictures.filter(item => {
    if (pictureScopeKey(item) !== institutionScopeKey()) return false;
    const assetKey = pictureAssetKey(item);
    return Boolean(assetKey) && !ownedAssetKeys.has(assetKey);
  });

  return [...inherited, ...collegeOwned];
}

export function stampPictureScope(
  picture: WizardPictureItem,
  scope: WizardPicturesEntityScope
): WizardPictureItem {
  if (scope.type === 'institution') {
    return {
      ...picture,
      college_id: null,
      college_local_id: null,
    };
  }
  return {
    ...picture,
    college_id: null,
    college_local_id: scope.collegeLocalId,
  };
}

/** Cascade clone: same storage_key/url, new reference row — no R2 re-upload. */
export function clonePictureForCollege(
  picture: WizardPictureItem,
  college: WizardCollegeItem
): WizardPictureItem {
  return {
    ...picture,
    local_id: crypto.randomUUID(),
    college_id: null,
    college_local_id: resolveCollegeLocalId(college),
  };
}

export function getCollegeOwnedPictureIndices(
  pictures: WizardPictureItem[],
  collegeLocalId: string,
  candidateIndices?: number[]
): number[] {
  const normalizedCollegeId = collegeLocalId.trim();
  const collegeKey = collegeScopeKey(normalizedCollegeId);
  let indices: number[] = [];
  pictures.forEach((picture, index) => {
    if (!pictureAssetKey(picture)) return;
    // Exact college ownership only — never institution rows or other colleges.
    if ((picture.college_local_id || '').trim() !== normalizedCollegeId) return;
    if (pictureScopeKey(picture) !== collegeKey) return;
    indices.push(index);
  });
  if (candidateIndices?.length) {
    const allowed = new Set(candidateIndices);
    indices = indices.filter(index => allowed.has(index));
  }
  return indices;
}

/** When unlinking a university picture, also drop cascaded college copies of the same asset. */
export function expandInstitutionPictureUnlinkIndices(
  pictures: WizardPictureItem[],
  indices: number[],
  collegeOverrides: Set<string>
): number[] {
  const expanded = new Set(indices);
  for (const index of indices) {
    const source = pictures[index];
    if (!source || pictureScopeKey(source) !== institutionScopeKey()) continue;
    const assetKey = pictureAssetKey(source);
    if (!assetKey) continue;
    pictures.forEach((item, itemIndex) => {
      if (expanded.has(itemIndex)) return;
      const scope = pictureScopeKey(item);
      if (!scope.startsWith('college')) return;
      if (pictureAssetKey(item) !== assetKey) return;
      const collegeLocalId = item.college_local_id?.trim();
      if (collegeLocalId && collegeOverrides.has(collegeLocalId)) return;
      expanded.add(itemIndex);
    });
  }
  return [...expanded].sort((a, b) => a - b);
}

export function assetsBecomingUnreferenced(
  pictures: WizardPictureItem[],
  removeIndices: number[]
): string[] {
  const removeSet = new Set(removeIndices);
  const remainingKeys = new Set(
    pictures
      .filter((_, index) => !removeSet.has(index))
      .map(pictureAssetKey)
      .filter(Boolean)
  );
  const orphaned = new Set<string>();
  for (const index of removeIndices) {
    const key = pictureAssetKey(pictures[index] || {});
    if (key && !remainingKeys.has(key)) orphaned.add(key);
  }
  return [...orphaned];
}
