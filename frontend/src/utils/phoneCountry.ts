export interface CountryDialCode {
  code: string;
  label: string;
}

export const COUNTRY_DIAL_CODES: CountryDialCode[] = [
  { code: '91', label: 'India (+91)' },
  { code: '1', label: 'United States / Canada (+1)' },
  { code: '44', label: 'United Kingdom (+44)' },
  { code: '971', label: 'UAE (+971)' },
  { code: '966', label: 'Saudi Arabia (+966)' },
  { code: '61', label: 'Australia (+61)' },
  { code: '65', label: 'Singapore (+65)' },
  { code: '92', label: 'Pakistan (+92)' },
  { code: '880', label: 'Bangladesh (+880)' },
  { code: '94', label: 'Sri Lanka (+94)' },
];

const SORTED_DIAL_CODES = [...COUNTRY_DIAL_CODES].sort((a, b) => b.code.length - a.code.length);

const LOCAL_PHONE_PATTERN = /^\d{10}$/;

export const PHONE_LOCAL_REQUIREMENTS = 'Enter exactly 10 numeric digits.';

export function parseStoredPhone(stored: string | null | undefined): {
  countryCode: string;
  localNumber: string;
} {
  const trimmed = (stored || '').trim();
  if (!trimmed) {
    return { countryCode: '', localNumber: '' };
  }

  if (trimmed.startsWith('+')) {
    const digits = trimmed.slice(1).replace(/\D/g, '');
    for (const country of SORTED_DIAL_CODES) {
      if (digits.startsWith(country.code) && digits.length === country.code.length + 10) {
        const localNumber = digits.slice(country.code.length);
        if (LOCAL_PHONE_PATTERN.test(localNumber)) {
          return { countryCode: country.code, localNumber };
        }
      }
    }
  }

  const digits = trimmed.replace(/\D/g, '');
  if (digits.length === 10 && LOCAL_PHONE_PATTERN.test(digits)) {
    return { countryCode: '', localNumber: digits };
  }

  if (digits.length > 10) {
    return { countryCode: '', localNumber: digits.slice(-10) };
  }

  return { countryCode: '', localNumber: digits };
}

export function formatFullPhone(countryCode: string, localNumber: string): string {
  const local = localNumber.replace(/\D/g, '');
  return `+${countryCode}${local}`;
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
  countryCode: string,
  localNumber: string
): string | null {
  if (!countryCode) return 'Please select a country code.';
  if (!COUNTRY_DIAL_CODES.some(country => country.code === countryCode)) {
    return 'Select a valid country code.';
  }
  return validateLocalPhoneNumber(localNumber);
}
