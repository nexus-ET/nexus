import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../utils/api';
import type { CountryRecord } from '../types/country';
import { FALLBACK_COUNTRIES } from '../types/country';

export function useCountries() {
  const query = useQuery<CountryRecord[]>({
    queryKey: ['countries'],
    queryFn: () => apiFetch('countries'),
    staleTime: 1000 * 60 * 60,
  });

  const countries = query.data?.length ? query.data : FALLBACK_COUNTRIES;

  return {
    countries,
    isLoading: query.isLoading,
    isError: query.isError,
  };
}

export function findCountryByIso2(
  countries: CountryRecord[],
  iso2: string | null | undefined
): CountryRecord | undefined {
  if (!iso2) return undefined;
  return countries.find(country => country.iso2 === iso2.trim().toUpperCase());
}

export function formatPhoneCountryLabel(country: CountryRecord): string {
  return `${country.iso2} +${country.dial_code}`;
}

export function countryNameOptions(countries: CountryRecord[]) {
  return countries.map(country => ({
    value: country.iso2,
    label: country.name,
  }));
}
