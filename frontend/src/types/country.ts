export interface CountryRecord {
  id: number;
  iso2: string;
  name: string;
  dial_code: string;
  sort_order: number;
}

export const FALLBACK_COUNTRIES: CountryRecord[] = [
  { id: 1, iso2: 'IN', name: 'India', dial_code: '91', sort_order: 1 },
  { id: 2, iso2: 'US', name: 'United States', dial_code: '1', sort_order: 2 },
  { id: 3, iso2: 'GB', name: 'United Kingdom', dial_code: '44', sort_order: 3 },
  { id: 4, iso2: 'AE', name: 'United Arab Emirates', dial_code: '971', sort_order: 4 },
  { id: 5, iso2: 'IE', name: 'Ireland', dial_code: '353', sort_order: 5 },
  { id: 6, iso2: 'AU', name: 'Australia', dial_code: '61', sort_order: 6 },
  { id: 7, iso2: 'SG', name: 'Singapore', dial_code: '65', sort_order: 7 },
  { id: 8, iso2: 'MY', name: 'Malaysia', dial_code: '60', sort_order: 8 },
  { id: 9, iso2: 'NO', name: 'Norway', dial_code: '47', sort_order: 9 },
  { id: 10, iso2: 'PL', name: 'Poland', dial_code: '48', sort_order: 10 },
  { id: 11, iso2: 'CA', name: 'Canada', dial_code: '1', sort_order: 11 },
  { id: 12, iso2: 'DE', name: 'Germany', dial_code: '49', sort_order: 12 },
  { id: 13, iso2: 'FR', name: 'France', dial_code: '33', sort_order: 13 },
  { id: 14, iso2: 'JP', name: 'Japan', dial_code: '81', sort_order: 14 },
  { id: 15, iso2: 'NZ', name: 'New Zealand', dial_code: '64', sort_order: 15 },
  { id: 16, iso2: 'QA', name: 'Qatar', dial_code: '974', sort_order: 16 },
  { id: 17, iso2: 'NL', name: 'Netherlands', dial_code: '31', sort_order: 17 },
  { id: 18, iso2: 'RU', name: 'Russia', dial_code: '7', sort_order: 18 },
  { id: 19, iso2: 'HK', name: 'Hong Kong', dial_code: '852', sort_order: 19 },
];
