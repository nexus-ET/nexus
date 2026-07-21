import type { CountryRecord } from './country';

export interface GeographyCountry {
  id: number;
  name: string;
  iso2: string;
  dial_code: string;
}

export function resolveGeographyCountryIso2(
  countries: GeographyCountry[],
  countryId?: number | null
): string {
  if (!countryId) return '';
  return countries.find(country => country.id === countryId)?.iso2 ?? '';
}

export function findGeographyCountryByIso2(
  countries: GeographyCountry[],
  iso2?: string | null
): GeographyCountry | undefined {
  if (!iso2) return undefined;
  const normalized = iso2.trim().toUpperCase();
  return countries.find(country => country.iso2 === normalized);
}

export function geographyCountriesToPhoneCountries(
  countries: GeographyCountry[]
): CountryRecord[] {
  return countries.map((country, index) => ({
    id: country.id,
    iso2: country.iso2,
    name: country.name,
    dial_code: country.dial_code,
    sort_order: index,
  }));
}
