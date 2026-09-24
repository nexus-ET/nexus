/**
 * ScanX picker-batch grouping helpers.
 * JPEG path: all images in one selection → one document group.
 * PDF path: only complementary front/back pairs that share a stem.
 */

const SIDE_TOKEN =
  /(?:^|[\s_\-.(\[])(front|frnt|recto|obverse|back|bck|verso|reverse)(?:$|[\s_\-.)\]])/i;

const FRONT_TOKENS = new Set(['front', 'frnt', 'recto', 'obverse']);
const BACK_TOKENS = new Set(['back', 'bck', 'verso', 'reverse']);

export function isScanxPdfFile(file: { name: string; type?: string | null }): boolean {
  const name = (file.name || '').toLowerCase();
  const mime = (file.type || '').toLowerCase();
  if (mime === 'application/pdf') return true;
  return name.endsWith('.pdf');
}

export function passportSideFromFilename(name: string): 'front' | 'back' | null {
  const stem = (name || '').replace(/\.[^.]+$/, '');
  const match = stem.match(SIDE_TOKEN);
  if (!match) return null;
  const tok = (match[1] || '').toLowerCase();
  if (FRONT_TOKENS.has(tok)) return 'front';
  if (BACK_TOKENS.has(tok)) return 'back';
  return null;
}

export function pairingStem(name: string): string {
  const stem = (name || '')
    .replace(/\.[^.]+$/, '')
    .replace(SIDE_TOKEN, ' ')
    .replace(/[\s_\-]+/g, ' ')
    .trim()
    .toLowerCase();
  return stem;
}

/** Pair PDF files that look like front/back of the same passport; leave others alone. */
export function groupPdfFrontBackFiles<T extends { name: string }>(files: T[]): {
  groups: T[][];
  singles: T[];
} {
  const groups: T[][] = [];
  const claimed = new Set<number>();
  const byStem = new Map<string, { front: number[]; back: number[] }>();

  files.forEach((file, index) => {
    const side = passportSideFromFilename(file.name);
    if (!side) return;
    const stem = pairingStem(file.name);
    if (!stem) return;
    let bucket = byStem.get(stem);
    if (!bucket) {
      bucket = { front: [], back: [] };
      byStem.set(stem, bucket);
    }
    bucket[side].push(index);
  });

  const stemKeys = [...byStem.keys()].sort();
  for (const stem of stemKeys) {
    const bucket = byStem.get(stem)!;
    while (bucket.front.length > 0 && bucket.back.length > 0) {
      const fi = bucket.front.shift()!;
      const bi = bucket.back.shift()!;
      groups.push([files[fi], files[bi]]);
      claimed.add(fi);
      claimed.add(bi);
    }
  }

  const singles = files.filter((_, index) => !claimed.has(index));
  return { groups, singles };
}
