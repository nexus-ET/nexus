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
  { id: 5, iso2: 'SA', name: 'Saudi Arabia', dial_code: '966', sort_order: 5 },
  { id: 6, iso2: 'AU', name: 'Australia', dial_code: '61', sort_order: 6 },
  { id: 7, iso2: 'SG', name: 'Singapore', dial_code: '65', sort_order: 7 },
  { id: 8, iso2: 'PK', name: 'Pakistan', dial_code: '92', sort_order: 8 },
  { id: 9, iso2: 'BD', name: 'Bangladesh', dial_code: '880', sort_order: 9 },
  { id: 10, iso2: 'LK', name: 'Sri Lanka', dial_code: '94', sort_order: 10 },
  { id: 11, iso2: 'CA', name: 'Canada', dial_code: '1', sort_order: 11 },
  { id: 12, iso2: 'DE', name: 'Germany', dial_code: '49', sort_order: 12 },
  { id: 13, iso2: 'FR', name: 'France', dial_code: '33', sort_order: 13 },
  { id: 14, iso2: 'JP', name: 'Japan', dial_code: '81', sort_order: 14 },
];
