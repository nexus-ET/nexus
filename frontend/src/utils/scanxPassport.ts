/**
 * ScanX passport extract → counsellor table mapping helpers.
 * Hydrates missing schema keys from flat fields/categories and normalizes addresses.
 */

export type ScanxPassportExtract = {
  surname?: string | null;
  given_names?: string | null;
  date_of_birth?: string | null;
  sex?: string | null;
  nationality?: string | null;
  country_code?: string | null;
  place_of_birth?: string | null;
  document_number?: string | null;
  document_type?: string | null;
  place_of_issue?: string | null;
  date_of_issue?: string | null;
  date_of_expiry?: string | null;
  mrz_string?: string | null;
  father_name?: string | null;
  mother_name?: string | null;
  spouse_name?: string | null;
  address?: string | null;
  file_number?: string | null;
  bounding_boxes?: Record<string, number[][]>;
  bounding_box_pages?: Record<string, number>;
  confidence_scores?: Record<string, number>;
  is_low_confidence?: boolean;
  [key: string]: unknown;
};

export type PassportLabelValue = { label?: string | null; value?: unknown; category?: string };

/** Canonical biographic / document keys shown in passport tables. */
export const PASSPORT_PERSONAL_KEYS = [
  'surname',
  'given_names',
  'date_of_birth',
  'sex',
  'nationality',
  'country_code',
  'place_of_birth',
  'father_name',
  'mother_name',
  'spouse_name',
] as const;

export const PASSPORT_DOCUMENT_KEYS = [
  'document_number',
  'document_type',
  'place_of_issue',
  'date_of_issue',
  'date_of_expiry',
  'file_number',
  'address',
] as const;

export const PASSPORT_MRZ_KEYS = ['mrz_string'] as const;

export const PASSPORT_AUDIT_KEYS = [
  'bounding_boxes',
  'confidence_scores',
  'is_low_confidence',
] as const;

export const PASSPORT_FIELD_LABELS: Record<string, string> = {
  surname: 'Surname',
  given_names: 'Given names',
  date_of_birth: 'Date of birth',
  sex: 'Sex',
  nationality: 'Nationality',
  country_code: 'Country code',
  place_of_birth: 'Place of birth',
  father_name: 'Father / guardian name',
  mother_name: 'Mother name',
  spouse_name: 'Spouse name',
  document_number: 'Passport number',
  document_type: 'Document type',
  place_of_issue: 'Place of issue',
  date_of_issue: 'Date of issue',
  date_of_expiry: 'Date of expiry',
  file_number: 'File number',
  address: 'Address',
  mrz_string: 'MRZ string',
  bounding_boxes: 'Bounding boxes',
  confidence_scores: 'Confidence scores',
  is_low_confidence: 'Is low confidence',
};

function isPassportNameJunk(raw: string): boolean {
  const text = raw.trim();
  if (!text) return true;
  if (
    /^(n\/?a|na|n\.a\.|nil|none|not\s*applicable|-|\/|—|–|\.|x+|went)(?:\s*\/.*)?$/i.test(
      text
    )
  ) {
    return true;
  }
  if (
    /\b(republic|nationality|passport|type\b|code\b|sex\b|place of|date of|name of|name ot|foter|lepai|curdian|mather|guardian|guardlan|uimeer|enpe|spouse|address|went|legal|stand in need|whom it may|assistance and protection|bearer to pass|freely without|let or hindrance)\b/i.test(
      text
    )
  ) {
    return true;
  }
  if (/[/\\|]/.test(text)) return true;
  if (/(?:^|[\s/])(?:fn|afy|faf)(?:[\s/]|$)/i.test(text)) return true;
  if (/\b[A-Z]\d{7}\b/i.test(text)) return true;
  const tokens = text.split(/\s+/).filter(Boolean);
  if (tokens.length === 1 && tokens[0].length < 5) return true;
  return false;
}

function isGarbageFileNumber(raw: string): boolean {
  const text = raw.trim();
  if (!text) return true;
  if (/\d{1,2}[./-]\d{1,2}[./-]\d{2,4}/.test(text)) return true;
  if (/\b(pita|father|foter|issue|lssue|expiry|expir)\b/i.test(text)) return true;
  return false;
}

/** Label / alias → canonical schema key. */
const LABEL_TO_KEY: Record<string, keyof ScanxPassportExtract> = {
  surname: 'surname',
  'family name': 'surname',
  'last name': 'surname',
  '/surname': 'surname',
  given_names: 'given_names',
  'given names': 'given_names',
  'given name': 'given_names',
  givenname: 'given_names',
  givennames: 'given_names',
  'first name': 'given_names',
  'first names': 'given_names',
  forenames: 'given_names',
  forename: 'given_names',
  date_of_birth: 'date_of_birth',
  'date of birth': 'date_of_birth',
  dob: 'date_of_birth',
  birth: 'date_of_birth',
  sex: 'sex',
  gender: 'sex',
  nationality: 'nationality',
  citizenship: 'nationality',
  country_code: 'country_code',
  'country code': 'country_code',
  place_of_birth: 'place_of_birth',
  'place of birth': 'place_of_birth',
  'birth place': 'place_of_birth',
  pob: 'place_of_birth',
  father_name: 'father_name',
  'father / guardian name': 'father_name',
  'father name': 'father_name',
  "father's name": 'father_name',
  'name of father': 'father_name',
  'name of guardian': 'father_name',
  'guardian name': 'father_name',
  mother_name: 'mother_name',
  'mother name': 'mother_name',
  "mother's name": 'mother_name',
  'name of mother': 'mother_name',
  spouse_name: 'spouse_name',
  'spouse name': 'spouse_name',
  "spouse's name": 'spouse_name',
  'name of spouse': 'spouse_name',
  document_number: 'document_number',
  'document number': 'document_number',
  'passport number': 'document_number',
  'passport no': 'document_number',
  'passport no.': 'document_number',
  passport_number: 'document_number',
  document_type: 'document_type',
  'document type': 'document_type',
  'passport type': 'document_type',
  type: 'document_type',
  place_of_issue: 'place_of_issue',
  'place of issue': 'place_of_issue',
  'place of iss ue': 'place_of_issue',
  date_of_issue: 'date_of_issue',
  'date of issue': 'date_of_issue',
  'date of lssue': 'date_of_issue',
  'issue date': 'date_of_issue',
  date_of_expiry: 'date_of_expiry',
  'date of expiry': 'date_of_expiry',
  'expiry date': 'date_of_expiry',
  expiry: 'date_of_expiry',
  expiration: 'date_of_expiry',
  'date of expiration': 'date_of_expiry',
  file_number: 'file_number',
  'file number': 'file_number',
  'file no': 'file_number',
  'file no.': 'file_number',
  fileno: 'file_number',
  'a3 / f no': 'file_number',
  'name of father / legal guardian': 'father_name',
  'name of father/legal guardian': 'father_name',
  'father / legal guardian': 'father_name',
  address: 'address',
  'residential address': 'address',
  mrz_string: 'mrz_string',
  'mrz string': 'mrz_string',
  mrz: 'mrz_string',
};

const CANONICAL_STRING_KEYS = [
  ...PASSPORT_PERSONAL_KEYS,
  ...PASSPORT_DOCUMENT_KEYS,
  ...PASSPORT_MRZ_KEYS,
] as const;

/**
 * Collapse multi-line OCR address fragments into one readable line.
 * Newlines → commas; squeeze whitespace; trim dangling separators.
 */
export function normalizeMultilineAddress(raw: unknown): string {
  const text = coercePassportScalar(raw);
  if (!text) return '';
  const unified = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  const parts = unified
    .split('\n')
    .map(part => part.replace(/\s+/g, ' ').trim().replace(/^[,;]+|[,;]+$/g, '').trim())
    .filter(Boolean);
  if (parts.length === 0) return '';
  let joined = parts.join(', ');
  joined = joined.replace(/\s*,\s*/g, ', ').replace(/(,\s*){2,}/g, ', ').trim();
  return joined.replace(/^,+|,+$/g, '').trim();
}

/** Coerce OCR / JSON scalars (and small arrays / {value}) to a display string. */
export function coercePassportScalar(raw: unknown): string {
  if (raw == null) return '';
  if (typeof raw === 'string') return raw.trim();
  if (typeof raw === 'number' || typeof raw === 'boolean') return String(raw).trim();
  if (Array.isArray(raw)) {
    return raw
      .map(item => coercePassportScalar(item))
      .filter(Boolean)
      .join('\n')
      .trim();
  }
  if (typeof raw === 'object') {
    const obj = raw as Record<string, unknown>;
    if ('value' in obj) return coercePassportScalar(obj.value);
    if ('text' in obj) return coercePassportScalar(obj.text);
  }
  return '';
}

function normalizeLabelKey(label: string): string {
  return label
    .trim()
    .toLowerCase()
    .replace(/[_/]+/g, ' ')
    .replace(/\s+/g, ' ')
    .replace(/[.:]+$/g, '')
    .trim();
}

function resolveCanonicalKey(labelOrKey: string): keyof ScanxPassportExtract | null {
  const raw = labelOrKey.trim();
  if (!raw) return null;
  // Direct snake_case / camelCase
  const snake = raw
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .replace(/[\s-]+/g, '_')
    .toLowerCase();
  if ((CANONICAL_STRING_KEYS as readonly string[]).includes(snake)) {
    return snake as keyof ScanxPassportExtract;
  }
  const normalized = normalizeLabelKey(raw);
  const fromAlias = LABEL_TO_KEY[normalized] || LABEL_TO_KEY[snake];
  if (fromAlias) return fromAlias;

  // Fuzzy: printed Indian page-2 labels → canonical keys (not UI display strings).
  // UI "Father / guardian name" is only a display label for key father_name.
  if (
    /\b(father|foter|fother|guardian|curdian)\b/i.test(normalized) &&
    !/\b(mother|mather|spouse|spouce)\b/i.test(normalized)
  ) {
    return 'father_name';
  }
  if (/\b(mother|mather|mothor|maches)\b/i.test(normalized)) return 'mother_name';
  if (/\b(spouse|spouce)\b/i.test(normalized)) return 'spouse_name';
  if (
    /\b(file\s*(no\.?|number|#)|fileno|a3\s*\/\s*f|fke\s*no|f\.?\s*no\.?)\b/i.test(
      normalized
    )
  ) {
    if (/\bpita\b/i.test(normalized)) return null;
    return 'file_number';
  }
  return null;
}

function collectLabelValuePairs(
  fields?: PassportLabelValue[] | null,
  categories?: Array<{ id?: string; label?: string; items?: PassportLabelValue[] }> | null
): PassportLabelValue[] {
  const out: PassportLabelValue[] = [];
  for (const f of fields || []) {
    if (f && typeof f === 'object') out.push(f);
  }
  for (const cat of categories || []) {
    for (const item of cat?.items || []) {
      if (item && typeof item === 'object') out.push(item);
    }
  }
  return out;
}

/** Format ISO or DMY dates for passport display (default DD-MM-YYYY). */
export function formatPassportDate(raw: unknown): string {
  const text = coercePassportScalar(raw);
  if (!text) return '';
  // Already DD-MM-YYYY / DD/MM/YYYY
  const dmy = text.match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$/);
  if (dmy) {
    return `${dmy[1].padStart(2, '0')}-${dmy[2].padStart(2, '0')}-${dmy[3]}`;
  }
  // ISO YYYY-MM-DD
  const iso = text.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (iso) {
    return `${iso[3]}-${iso[2]}-${iso[1]}`;
  }
  return text;
}

function mrzLine1NameParts(mrz: string | null | undefined): {
  surname: string | null;
  given_names: string | null;
} {
  for (const raw of String(mrz || '').split(/\r?\n/)) {
    const line = raw.replace(/\s+/g, '').toUpperCase();
    if (!line.startsWith('P') || line.length < 10) continue;
    const names = line.slice(5, 44);
    const sep = names.indexOf('<<');
    if (sep < 0) continue;
    const surname = names.slice(0, sep).replace(/</g, ' ').trim() || null;
    const given_names =
      names
        .slice(sep + 2)
        .replace(/</g, ' ')
        .replace(/\s+/g, ' ')
        .trim() || null;
    return { surname, given_names };
  }
  return { surname: null, given_names: null };
}

function rejectCrossFilledHolderNames(hydrated: ScanxPassportExtract): void {
  const sn = coercePassportScalar(hydrated.surname);
  const gn = coercePassportScalar(hydrated.given_names);
  if (!sn || !gn || sn.toUpperCase() !== gn.toUpperCase()) return;
  const parts = mrzLine1NameParts(hydrated.mrz_string);
  const snOk = !!(parts.surname && parts.surname.toUpperCase() === sn.toUpperCase());
  const gnOk = !!(
    parts.given_names && parts.given_names.toUpperCase() === gn.toUpperCase()
  );
  if (!snOk) hydrated.surname = null;
  if (!gnOk) hydrated.given_names = null;
}

/** Blank family fields that are exact copies of the holder's given name. */
function rejectHolderGivenCopiedIntoFamily(hydrated: ScanxPassportExtract): void {
  const gn = coercePassportScalar(hydrated.given_names);
  if (!gn) return;
  const gnU = gn.toUpperCase();
  for (const key of ['father_name', 'mother_name', 'spouse_name'] as const) {
    const v = coercePassportScalar(hydrated[key]);
    if (v && v.toUpperCase() === gnU) {
      hydrated[key] = null;
    }
  }
}

/**
 * Build a counsellor-ready passport object:
 * - Prefer explicit passport schema values
 * - Fill blanks from fields/categories via label aliases
 * - Normalize address newlines
 * - Normalize dates to DD-MM-YYYY for display
 */
export function hydratePassportExtract(
  passport: ScanxPassportExtract | null | undefined,
  opts?: {
    fields?: PassportLabelValue[] | null;
    categories?: Array<{ id?: string; label?: string; items?: PassportLabelValue[] }> | null;
  }
): ScanxPassportExtract {
  const src = passport && typeof passport === 'object' ? { ...passport } : {};
  const hydrated: ScanxPassportExtract = { ...src };
  const dateKeys = new Set(['date_of_birth', 'date_of_issue', 'date_of_expiry']);
  const apiSurname = coercePassportScalar(src.surname);
  const apiGiven = coercePassportScalar(src.given_names);

    // 1) Coerce direct schema keys (including camelCase on the same object).
  for (const key of CANONICAL_STRING_KEYS) {
    const direct = coercePassportScalar(hydrated[key]);
    if (direct) {
      if (
        (key === 'father_name' || key === 'mother_name' || key === 'spouse_name') &&
        isPassportNameJunk(direct)
      ) {
        hydrated[key] = null;
        continue;
      }
      if (key === 'file_number' && isGarbageFileNumber(direct)) {
        hydrated[key] = null;
        continue;
      }
      if (key === 'address') {
        hydrated[key] = normalizeMultilineAddress(direct);
      } else if (dateKeys.has(key)) {
        hydrated[key] = formatPassportDate(direct);
      } else {
        hydrated[key] = direct;
      }
      continue;
    }
    // camelCase twin e.g. givenNames
    const camel = key.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase());
    const fromCamel = coercePassportScalar((src as Record<string, unknown>)[camel]);
    if (fromCamel) {
      if (key === 'file_number' && isGarbageFileNumber(fromCamel)) {
        hydrated[key] = null;
      } else if (key === 'address') {
        hydrated[key] = normalizeMultilineAddress(fromCamel);
      } else if (dateKeys.has(key)) {
        hydrated[key] = formatPassportDate(fromCamel);
      } else {
        hydrated[key] = fromCamel;
      }
    }
  }

    // 2) Fill / upgrade from flat Field|Value rows / category items.
    // Never fill a blank by copying a sibling field's value.
    const pairs = collectLabelValuePairs(opts?.fields, opts?.categories);
    const nameKeys = new Set(['surname', 'given_names', 'father_name', 'mother_name', 'spouse_name']);
    const siblingValues = (): Set<string> => {
      const out = new Set<string>();
      for (const k of CANONICAL_STRING_KEYS) {
        const v = coercePassportScalar(hydrated[k]).toUpperCase();
        if (v) out.add(v);
      }
      return out;
    };
    for (const pair of pairs) {
      const label = String(pair.label || '').trim();
      const value = coercePassportScalar(pair.value);
      if (!label || !value) continue;
      const key = resolveCanonicalKey(label);
      if (!key) continue;
      if ((CANONICAL_STRING_KEYS as readonly string[]).includes(key as string)) {
        const existing = coercePassportScalar(hydrated[key]);
        if (existing) {
          // Prefer a clean person name — never upgrade to OCR label junk.
          if (nameKeys.has(key)) {
            const existingJunk = isPassportNameJunk(existing);
            const valueJunk = isPassportNameJunk(value);
            if (existingJunk && !valueJunk) {
              hydrated[key] = value;
            }
          }
          if (key === 'file_number' && isGarbageFileNumber(existing) && !isGarbageFileNumber(value)) {
            hydrated[key] = value;
          }
          // Prefer two-line MRZ over a single line.
          if (
            key === 'mrz_string' &&
            value.includes('\n') &&
            !existing.includes('\n')
          ) {
            hydrated[key] = value;
          }
          continue;
        }
        if (nameKeys.has(key) && isPassportNameJunk(value)) {
          continue;
        }
        if (key === 'file_number' && isGarbageFileNumber(value)) {
          continue;
        }
        const siblings = siblingValues();
        if (siblings.has(value.toUpperCase())) {
          continue;
        }
        if (key === 'address') {
          hydrated[key] = normalizeMultilineAddress(value);
        } else if (dateKeys.has(key)) {
          hydrated[key] = formatPassportDate(value);
        } else {
          hydrated[key] = value;
        }
      }
    }

  // 3) Final address + date pass.
  if (hydrated.address != null) {
    hydrated.address = normalizeMultilineAddress(hydrated.address) || null;
  }
  const fileNo = coercePassportScalar(hydrated.file_number);
  if (!fileNo || isGarbageFileNumber(fileNo)) {
    hydrated.file_number = null;
  }
  for (const key of dateKeys) {
    const v = coercePassportScalar(hydrated[key as keyof ScanxPassportExtract]);
    if (v) {
      (hydrated as Record<string, unknown>)[key] = formatPassportDate(v);
    }
  }

  const demonym: Record<string, string> = {
    IND: 'INDIAN',
    USA: 'AMERICAN',
    GBR: 'BRITISH',
    AUS: 'AUSTRALIAN',
    CAN: 'CANADIAN',
    NZL: 'NEW ZEALANDER',
    PAK: 'PAKISTANI',
    BGD: 'BANGLADESHI',
    NPL: 'NEPALI',
    LKA: 'SRI LANKAN',
    CHN: 'CHINESE',
    JPN: 'JAPANESE',
    KOR: 'KOREAN',
    DEU: 'GERMAN',
    FRA: 'FRENCH',
    ARE: 'EMIRATI',
  };
  const nationalityBleed =
    /\b(sex|sexe|gender|male|female|date|dale|birth|birthdate|dob|place|issue|expiry|surname|given|passport|type|code|father|mother|guardian|croufuft|faiq)\b/i;
  const legacyCode = coercePassportScalar(
    (src as Record<string, unknown>).issuing_state ?? hydrated.country_code
  ).toUpperCase();
  let nat = coercePassportScalar(hydrated.nationality).toUpperCase();
  if (nat && (nationalityBleed.test(nat) || nat.split(/\s+/).length > 4 || nat.length > 32)) {
    nat = '';
    hydrated.nationality = null;
  }
  if (!hydrated.country_code && /^[A-Z]{3}$/.test(nat) && demonym[nat]) {
    hydrated.country_code = nat;
  } else if (!hydrated.country_code && /^[A-Z]{3}$/.test(legacyCode) && demonym[legacyCode]) {
    hydrated.country_code = legacyCode;
  }
  const code = coercePassportScalar(hydrated.country_code).toUpperCase();
  if (code && demonym[code] && (!nat || nat === code || nationalityBleed.test(nat))) {
    hydrated.nationality = demonym[code];
  } else if (nat && Object.values(demonym).includes(nat)) {
    hydrated.nationality = nat;
  } else if (nat && demonym[nat]) {
    hydrated.nationality = demonym[nat];
    if (!hydrated.country_code) hydrated.country_code = nat;
  } else if (nat && !Object.values(demonym).includes(nat) && !/^[A-Z]{3}$/.test(nat)) {
    // Unknown multi-word OCR soup — clear rather than display garbage.
    hydrated.nationality = code && demonym[code] ? demonym[code] : null;
  }
  const poi = coercePassportScalar(hydrated.place_of_issue).replace(/^\d+\s+/, '').trim();
  if (poi) hydrated.place_of_issue = poi;

  // Preserve audit metadata
  if (src.bounding_boxes && typeof src.bounding_boxes === 'object') {
    hydrated.bounding_boxes = src.bounding_boxes as Record<string, number[][]>;
  }
  if (src.bounding_box_pages && typeof src.bounding_box_pages === 'object') {
    hydrated.bounding_box_pages = src.bounding_box_pages as Record<string, number>;
  }
  if (src.confidence_scores && typeof src.confidence_scores === 'object') {
    hydrated.confidence_scores = src.confidence_scores as Record<string, number>;
  }
  if (typeof src.is_low_confidence === 'boolean') {
    hydrated.is_low_confidence = src.is_low_confidence;
  }

  // API already returned equal names: keep only sides MRZ independently supports.
  // Hydrate must not leave a blank filled from the sibling after the API left it empty.
  if (
    apiSurname &&
    apiGiven &&
    apiSurname.toUpperCase() === apiGiven.toUpperCase()
  ) {
    rejectCrossFilledHolderNames(hydrated);
  } else {
    const sn = coercePassportScalar(hydrated.surname);
    const gn = coercePassportScalar(hydrated.given_names);
    if (sn && gn && sn.toUpperCase() === gn.toUpperCase()) {
      if (!apiSurname) hydrated.surname = null;
      if (!apiGiven) hydrated.given_names = null;
      rejectCrossFilledHolderNames(hydrated);
    }
  }
  rejectHolderGivenCopiedIntoFamily(hydrated);

  return hydrated;
}

export function formatPassportAuditValue(
  key: (typeof PASSPORT_AUDIT_KEYS)[number],
  passport: ScanxPassportExtract
): string {
  if (key === 'is_low_confidence') {
    if (passport.is_low_confidence == null) return '';
    return passport.is_low_confidence ? 'true' : 'false';
  }
  if (key === 'confidence_scores') {
    const scores = passport.confidence_scores;
    if (!scores || typeof scores !== 'object') return '';
    const parts = Object.entries(scores)
      .filter(([, v]) => Number(v) > 0)
      .map(([k, v]) => `${k}=${Math.round(Number(v) * 100)}%`);
    return parts.join('; ');
  }
  if (key === 'bounding_boxes') {
    const boxes = passport.bounding_boxes;
    if (!boxes || typeof boxes !== 'object') return '';
    const parts = Object.entries(boxes).map(
      ([k, box]) => `${k}: ${Array.isArray(box) ? box.length : 0} pts`
    );
    return parts.join('; ');
  }
  return '';
}
