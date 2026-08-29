import type { CountryRecord } from '../types/country';
import { FALLBACK_COUNTRIES } from '../types/country';

export type { CountryRecord };

/** Phone keypad letter mapping (ITU E.161 / NANP vanity numbers). */
const VANITY_KEYPAD: Record<string, string> = {
  a: '2',
  b: '2',
  c: '2',
  d: '3',
  e: '3',
  f: '3',
  g: '4',
  h: '4',
  i: '4',
  j: '5',
  k: '5',
  l: '5',
  m: '6',
  n: '6',
  o: '6',
  p: '7',
  q: '7',
  r: '7',
  s: '7',
  t: '8',
  u: '8',
  v: '8',
  w: '9',
  x: '9',
  y: '9',
  z: '9',
};

export const PHONE_LOCAL_PLACEHOLDER = 'e.g. 5551234567 or 877-88-CAREY';
export const PHONE_LOCAL_REQUIREMENTS =
  'Enter 10 digits, or a vanity number (letters map to the phone keypad, e.g. 877-88-CAREY).';
export const EMAIL_FORMAT_HINT = 'Enter email id in a correct format.';
export const MIN_APPLICANT_AGE = 16;

/** Max characters while typing a local/vanity number (before keypad conversion). */
export const PHONE_LOCAL_DRAFT_MAX_LENGTH = 20;

const LOCAL_PHONE_PATTERN = /^\d{10}$/;

function findCountryByIso2(
  countries: CountryRecord[],
  iso2: string
): CountryRecord | undefined {
  if (!iso2) return undefined;
  return countries.find(item => item.iso2 === iso2);
}

function sortedByDialCode(countries: CountryRecord[]): CountryRecord[] {
  return [...countries].sort((a, b) => b.dial_code.length - a.dial_code.length);
}

/** Map vanity letters to keypad digits; leave other characters unchanged. */
export function vanityLettersToDigits(raw: string): string {
  return raw.replace(/[a-z]/gi, char => VANITY_KEYPAD[char.toLowerCase()] ?? '');
}

/** Digits only after vanity letter conversion (for storage / length checks). */
export function phoneLocalToDigits(raw: string): string {
  return vanityLettersToDigits(raw).replace(/\D/g, '');
}

/**
 * Allow digits, vanity letters, and common phone punctuation while the user is typing.
 * Does not convert letters yet — conversion happens on commit/normalize.
 */
export function sanitizePhoneLocalDraft(raw: string): string {
  return raw.replace(/[^0-9a-zA-Z\s().+-]/g, '').slice(0, PHONE_LOCAL_DRAFT_MAX_LENGTH);
}

export function formatPhoneCountryLabel(country: CountryRecord): string {
  return `${country.iso2} +${country.dial_code}`;
}

export function normalizeLocalPhoneDigits(
  raw: string,
  countryIso2: string,
  countries: CountryRecord[] = FALLBACK_COUNTRIES
): string {
  let digits = phoneLocalToDigits(raw);
  if (!digits) return '';

  const country = findCountryByIso2(countries, countryIso2);
  if (country?.dial_code) {
    if (digits.startsWith(country.dial_code) && digits.length > country.dial_code.length) {
      const withoutDialCode = digits.slice(country.dial_code.length);
      if (withoutDialCode.length >= 10) {
        return withoutDialCode.slice(-10);
      }
      digits = withoutDialCode;
    }
    if (country.dial_code === '1' && digits.length === 11 && digits.startsWith('1')) {
      digits = digits.slice(1);
    }
  }

  return digits.slice(0, 10);
}

export function parseStoredPhone(
  stored: string | null | undefined,
  countries: CountryRecord[] = FALLBACK_COUNTRIES
): {
  countryIso2: string;
  localNumber: string;
} {
  const trimmed = (stored || '').trim();
  if (!trimmed) {
    return { countryIso2: '', localNumber: '' };
  }

  const dialSorted = sortedByDialCode(countries);

  if (trimmed.startsWith('+')) {
    const digits = phoneLocalToDigits(trimmed.slice(1));
    for (const country of dialSorted) {
      if (digits.startsWith(country.dial_code) && digits.length === country.dial_code.length + 10) {
        const localNumber = digits.slice(country.dial_code.length);
        if (LOCAL_PHONE_PATTERN.test(localNumber)) {
          return { countryIso2: country.iso2, localNumber };
        }
      }
    }
    if (digits.length === 11 && digits.startsWith('1') && LOCAL_PHONE_PATTERN.test(digits.slice(1))) {
      const nanpCountry = dialSorted.find(country => country.dial_code === '1');
      return {
        countryIso2: nanpCountry?.iso2 || 'US',
        localNumber: digits.slice(1),
      };
    }
    if (digits.length === 10 && LOCAL_PHONE_PATTERN.test(digits)) {
      return { countryIso2: '', localNumber: digits };
    }
  }

  const digits = phoneLocalToDigits(trimmed);
  if (digits.length === 10 && LOCAL_PHONE_PATTERN.test(digits)) {
    return { countryIso2: '', localNumber: digits };
  }

  if (digits.length > 10) {
    return { countryIso2: '', localNumber: digits.slice(-10) };
  }

  // Preserve vanity / partial draft text when it has not resolved to 10 digits yet.
  if (/[a-z]/i.test(trimmed) && digits.length < 10) {
    return { countryIso2: '', localNumber: sanitizePhoneLocalDraft(trimmed) };
  }

  return { countryIso2: '', localNumber: digits };
}

export function formatFullPhone(
  countryIso2: string,
  localNumber: string,
  countries: CountryRecord[] = FALLBACK_COUNTRIES
): string {
  const local = normalizeLocalPhoneDigits(localNumber, countryIso2, countries);
  if (!local) return '';
  const country = findCountryByIso2(countries, countryIso2);
  if (!country) return local;
  return `+${country.dial_code}${local}`;
}

export function validateLocalPhoneNumber(localNumber: string): string | null {
  const digits = phoneLocalToDigits(localNumber);
  if (!digits) return 'Mobile number is required.';
  if (digits.length !== 10) {
    return `Mobile number must be exactly 10 digits after converting letters (you entered ${digits.length}).`;
  }
  if (!LOCAL_PHONE_PATTERN.test(digits)) return PHONE_LOCAL_REQUIREMENTS;
  return null;
}

export function validatePhoneWithCountry(
  countryIso2: string,
  localNumber: string,
  countries: CountryRecord[] = FALLBACK_COUNTRIES
): string | null {
  if (!countryIso2) return 'Please select a country code.';
  if (!countries.some(country => country.iso2 === countryIso2)) {
    return 'Select a valid country code.';
  }
  return validateLocalPhoneNumber(localNumber);
}

export function computeAgeFromDob(dob: string | null | undefined): number | null {
  if (!dob) return null;
  return computeAgeAsOf(dob, new Date());
}

export function computeAgePartsAsOf(
  dob: string | null | undefined,
  referenceDate: string | Date | null | undefined = new Date()
): { years: number; months: number; days: number } | null {
  if (!dob || !referenceDate) return null;
  const birth = new Date(`${dob}T00:00:00`);
  const rawRef = referenceDate instanceof Date ? referenceDate : new Date(referenceDate);
  if (Number.isNaN(birth.getTime()) || Number.isNaN(rawRef.getTime())) return null;

  const ref = new Date(rawRef.getFullYear(), rawRef.getMonth(), rawRef.getDate());
  if (birth > ref) return null;

  let years = ref.getFullYear() - birth.getFullYear();
  let months = ref.getMonth() - birth.getMonth();
  let days = ref.getDate() - birth.getDate();

  if (days < 0) {
    months -= 1;
    const daysInPrevMonth = new Date(ref.getFullYear(), ref.getMonth(), 0).getDate();
    days += daysInPrevMonth;
  }
  if (months < 0) {
    years -= 1;
    months += 12;
  }

  if (years < 0) return null;
  return { years, months, days };
}

/** e.g. "(Age: 18Y 3M 4D)" from DOB vs today (or a reference date). */
export function formatAgeYmd(
  dob: string | null | undefined,
  referenceDate: string | Date | null | undefined = new Date()
): string | null {
  const parts = computeAgePartsAsOf(dob, referenceDate);
  if (!parts) return null;
  return `(Age: ${parts.years}Y ${parts.months}M ${parts.days}D)`;
}

export function computeAgeAsOf(
  dob: string | null | undefined,
  referenceDate: string | Date | null | undefined
): number | null {
  if (!dob || !referenceDate) return null;
  const birth = new Date(`${dob}T00:00:00`);
  const ref = referenceDate instanceof Date ? referenceDate : new Date(referenceDate);
  if (Number.isNaN(birth.getTime()) || Number.isNaN(ref.getTime())) return null;
  let age = ref.getFullYear() - birth.getFullYear();
  const monthDiff = ref.getMonth() - birth.getMonth();
  if (monthDiff < 0 || (monthDiff === 0 && ref.getDate() < birth.getDate())) {
    age -= 1;
  }
  return age >= 0 ? age : null;
}

export function validateDateOfBirth(dob: string | null | undefined): string | null {
  if (!dob) return 'Date of birth is required.';

  const birth = new Date(`${dob}T00:00:00`);
  if (Number.isNaN(birth.getTime())) return 'Enter a valid date of birth.';

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  if (birth > today) {
    return 'Date of birth cannot be in the future.';
  }

  const age = computeAgeFromDob(dob);
  if (age === null) return 'Enter a valid date of birth.';
  if (age < MIN_APPLICANT_AGE) {
    return `Applicants must be at least ${MIN_APPLICANT_AGE} years old.`;
  }

  return null;
}
