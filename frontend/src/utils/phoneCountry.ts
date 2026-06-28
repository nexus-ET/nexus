import type { CountryRecord } from '../types/country';
import { FALLBACK_COUNTRIES } from '../types/country';

export type { CountryRecord };

export const PHONE_LOCAL_REQUIREMENTS = 'Enter exactly 10 numeric digits.';
export const MIN_APPLICANT_AGE = 16;

const LOCAL_PHONE_PATTERN = /^\d{10}$/;

function sortedByDialCode(countries: CountryRecord[]): CountryRecord[] {
  return [...countries].sort((a, b) => b.dial_code.length - a.dial_code.length);
}

export function formatPhoneCountryLabel(country: CountryRecord): string {
  return `${country.iso2} +${country.dial_code}`;
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
    const digits = trimmed.slice(1).replace(/\D/g, '');
    for (const country of dialSorted) {
      if (digits.startsWith(country.dial_code) && digits.length === country.dial_code.length + 10) {
        const localNumber = digits.slice(country.dial_code.length);
        if (LOCAL_PHONE_PATTERN.test(localNumber)) {
          return { countryIso2: country.iso2, localNumber };
        }
      }
    }
  }

  const digits = trimmed.replace(/\D/g, '');
  if (digits.length === 10 && LOCAL_PHONE_PATTERN.test(digits)) {
    return { countryIso2: '', localNumber: digits };
  }

  if (digits.length > 10) {
    return { countryIso2: '', localNumber: digits.slice(-10) };
  }

  return { countryIso2: '', localNumber: digits };
}

export function formatFullPhone(
  countryIso2: string,
  localNumber: string,
  countries: CountryRecord[] = FALLBACK_COUNTRIES
): string {
  const local = localNumber.replace(/\D/g, '');
  const country = countries.find(item => item.iso2 === countryIso2);
  if (!country) return `+${local}`;
  return `+${country.dial_code}${local}`;
}

export function validateLocalPhoneNumber(localNumber: string): string | null {
  const digits = localNumber.replace(/\D/g, '');
  if (!digits) return 'Mobile number is required.';
  if (digits.length !== 10) {
    return `Mobile number must be exactly 10 digits (you entered ${digits.length}).`;
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
