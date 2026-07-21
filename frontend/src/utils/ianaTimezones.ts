export const IANA_TIME_ZONES: string[] = [
  'Africa/Abidjan',
  'Africa/Accra',
  'Africa/Cairo',
  'Africa/Casablanca',
  'Africa/Johannesburg',
  'Africa/Lagos',
  'Africa/Nairobi',
  'America/Anchorage',
  'America/Argentina/Buenos_Aires',
  'America/Bogota',
  'America/Chicago',
  'America/Denver',
  'America/Halifax',
  'America/Lima',
  'America/Los_Angeles',
  'America/Mexico_City',
  'America/New_York',
  'America/Phoenix',
  'America/Sao_Paulo',
  'America/Toronto',
  'America/Vancouver',
  'Asia/Bangkok',
  'Asia/Colombo',
  'Asia/Dhaka',
  'Asia/Dubai',
  'Asia/Hong_Kong',
  'Asia/Jakarta',
  'Asia/Karachi',
  'Asia/Kolkata',
  'Asia/Kuala_Lumpur',
  'Asia/Manila',
  'Asia/Seoul',
  'Asia/Shanghai',
  'Asia/Singapore',
  'Asia/Taipei',
  'Asia/Tokyo',
  'Asia/Yangon',
  'Australia/Adelaide',
  'Australia/Brisbane',
  'Australia/Melbourne',
  'Australia/Perth',
  'Australia/Sydney',
  'Europe/Amsterdam',
  'Europe/Berlin',
  'Europe/Brussels',
  'Europe/Dublin',
  'Europe/Helsinki',
  'Europe/Istanbul',
  'Europe/Lisbon',
  'Europe/London',
  'Europe/Madrid',
  'Europe/Moscow',
  'Europe/Oslo',
  'Europe/Paris',
  'Europe/Rome',
  'Europe/Stockholm',
  'Europe/Warsaw',
  'Europe/Zurich',
  'Pacific/Auckland',
  'Pacific/Fiji',
  'Pacific/Honolulu',
  'UTC',
];

const ZONE_SET = new Set(IANA_TIME_ZONES);

/** Default IANA zone for countries that are mostly a single civil timezone. */
const COUNTRY_DEFAULT_TIMEZONE: Record<string, string> = {
  IN: 'Asia/Kolkata',
  GB: 'Europe/London',
  AE: 'Asia/Dubai',
  IE: 'Europe/Dublin',
  SG: 'Asia/Singapore',
  MY: 'Asia/Kuala_Lumpur',
  NO: 'Europe/Oslo',
  PL: 'Europe/Warsaw',
  DE: 'Europe/Berlin',
  FR: 'Europe/Paris',
  JP: 'Asia/Tokyo',
  NZ: 'Pacific/Auckland',
  QA: 'Asia/Dubai',
  NL: 'Europe/Amsterdam',
  HK: 'Asia/Hong_Kong',
  KR: 'Asia/Seoul',
  CN: 'Asia/Shanghai',
  TW: 'Asia/Taipei',
  TH: 'Asia/Bangkok',
  PH: 'Asia/Manila',
  ID: 'Asia/Jakarta',
  PK: 'Asia/Karachi',
  BD: 'Asia/Dhaka',
  LK: 'Asia/Colombo',
  MM: 'Asia/Yangon',
  VN: 'Asia/Bangkok',
  EG: 'Africa/Cairo',
  ZA: 'Africa/Johannesburg',
  NG: 'Africa/Lagos',
  KE: 'Africa/Nairobi',
  MA: 'Africa/Casablanca',
  GH: 'Africa/Accra',
  CI: 'Africa/Abidjan',
  BR: 'America/Sao_Paulo',
  AR: 'America/Argentina/Buenos_Aires',
  CO: 'America/Bogota',
  PE: 'America/Lima',
  MX: 'America/Mexico_City',
  FI: 'Europe/Helsinki',
  SE: 'Europe/Stockholm',
  CH: 'Europe/Zurich',
  BE: 'Europe/Brussels',
  ES: 'Europe/Madrid',
  IT: 'Europe/Rome',
  PT: 'Europe/Lisbon',
  TR: 'Europe/Istanbul',
  RU: 'Europe/Moscow',
  FJ: 'Pacific/Fiji',
};

/** US state/territory → timezone (region code preferred). */
const US_STATE_TIMEZONE: Record<string, string> = {
  AL: 'America/Chicago',
  AK: 'America/Anchorage',
  AZ: 'America/Phoenix',
  AR: 'America/Chicago',
  CA: 'America/Los_Angeles',
  CO: 'America/Denver',
  CT: 'America/New_York',
  DE: 'America/New_York',
  DC: 'America/New_York',
  FL: 'America/New_York',
  GA: 'America/New_York',
  HI: 'Pacific/Honolulu',
  ID: 'America/Denver',
  IL: 'America/Chicago',
  IN: 'America/New_York',
  IA: 'America/Chicago',
  KS: 'America/Chicago',
  KY: 'America/New_York',
  LA: 'America/Chicago',
  ME: 'America/New_York',
  MD: 'America/New_York',
  MA: 'America/New_York',
  MI: 'America/New_York',
  MN: 'America/Chicago',
  MS: 'America/Chicago',
  MO: 'America/Chicago',
  MT: 'America/Denver',
  NE: 'America/Chicago',
  NV: 'America/Los_Angeles',
  NH: 'America/New_York',
  NJ: 'America/New_York',
  NM: 'America/Denver',
  NY: 'America/New_York',
  NC: 'America/New_York',
  ND: 'America/Chicago',
  OH: 'America/New_York',
  OK: 'America/Chicago',
  OR: 'America/Los_Angeles',
  PA: 'America/New_York',
  RI: 'America/New_York',
  SC: 'America/New_York',
  SD: 'America/Chicago',
  TN: 'America/Chicago',
  TX: 'America/Chicago',
  UT: 'America/Denver',
  VT: 'America/New_York',
  VA: 'America/New_York',
  WA: 'America/Los_Angeles',
  WV: 'America/New_York',
  WI: 'America/Chicago',
  WY: 'America/Denver',
};

const US_STATE_NAME_TIMEZONE: Record<string, string> = {
  alabama: 'America/Chicago',
  alaska: 'America/Anchorage',
  arizona: 'America/Phoenix',
  arkansas: 'America/Chicago',
  california: 'America/Los_Angeles',
  colorado: 'America/Denver',
  connecticut: 'America/New_York',
  delaware: 'America/New_York',
  'district of columbia': 'America/New_York',
  florida: 'America/New_York',
  georgia: 'America/New_York',
  hawaii: 'Pacific/Honolulu',
  idaho: 'America/Denver',
  illinois: 'America/Chicago',
  indiana: 'America/New_York',
  iowa: 'America/Chicago',
  kansas: 'America/Chicago',
  kentucky: 'America/New_York',
  louisiana: 'America/Chicago',
  maine: 'America/New_York',
  maryland: 'America/New_York',
  massachusetts: 'America/New_York',
  michigan: 'America/New_York',
  minnesota: 'America/Chicago',
  mississippi: 'America/Chicago',
  missouri: 'America/Chicago',
  montana: 'America/Denver',
  nebraska: 'America/Chicago',
  nevada: 'America/Los_Angeles',
  'new hampshire': 'America/New_York',
  'new jersey': 'America/New_York',
  'new mexico': 'America/Denver',
  'new york': 'America/New_York',
  'north carolina': 'America/New_York',
  'north dakota': 'America/Chicago',
  ohio: 'America/New_York',
  oklahoma: 'America/Chicago',
  oregon: 'America/Los_Angeles',
  pennsylvania: 'America/New_York',
  'rhode island': 'America/New_York',
  'south carolina': 'America/New_York',
  'south dakota': 'America/Chicago',
  tennessee: 'America/Chicago',
  texas: 'America/Chicago',
  utah: 'America/Denver',
  vermont: 'America/New_York',
  virginia: 'America/New_York',
  washington: 'America/Los_Angeles',
  'west virginia': 'America/New_York',
  wisconsin: 'America/Chicago',
  wyoming: 'America/Denver',
};

/** Canada province → timezone (majority/primary). */
const CA_PROVINCE_TIMEZONE: Record<string, string> = {
  AB: 'America/Denver',
  BC: 'America/Vancouver',
  MB: 'America/Chicago',
  NB: 'America/Halifax',
  NL: 'America/Halifax',
  NS: 'America/Halifax',
  NT: 'America/Denver',
  NU: 'America/Toronto',
  ON: 'America/Toronto',
  PE: 'America/Halifax',
  QC: 'America/Toronto',
  SK: 'America/Chicago',
  YT: 'America/Vancouver',
};

const CA_PROVINCE_NAME_TIMEZONE: Record<string, string> = {
  alberta: 'America/Denver',
  'british columbia': 'America/Vancouver',
  manitoba: 'America/Chicago',
  'new brunswick': 'America/Halifax',
  'newfoundland and labrador': 'America/Halifax',
  'nova scotia': 'America/Halifax',
  'northwest territories': 'America/Denver',
  nunavut: 'America/Toronto',
  ontario: 'America/Toronto',
  'prince edward island': 'America/Halifax',
  quebec: 'America/Toronto',
  saskatchewan: 'America/Chicago',
  yukon: 'America/Vancouver',
};

/** Australia state/territory → timezone. */
const AU_STATE_TIMEZONE: Record<string, string> = {
  NSW: 'Australia/Sydney',
  VIC: 'Australia/Melbourne',
  QLD: 'Australia/Brisbane',
  SA: 'Australia/Adelaide',
  WA: 'Australia/Perth',
  TAS: 'Australia/Sydney',
  ACT: 'Australia/Sydney',
  NT: 'Australia/Brisbane',
};

const AU_STATE_NAME_TIMEZONE: Record<string, string> = {
  'new south wales': 'Australia/Sydney',
  victoria: 'Australia/Melbourne',
  queensland: 'Australia/Brisbane',
  'south australia': 'Australia/Adelaide',
  'western australia': 'Australia/Perth',
  tasmania: 'Australia/Sydney',
  'australian capital territory': 'Australia/Sydney',
  'northern territory': 'Australia/Brisbane',
};

export const filterTimeZones = (query: string): string[] => {
  const needle = query.trim().toLowerCase();
  if (!needle) return IANA_TIME_ZONES;
  return IANA_TIME_ZONES.filter(zone => zone.toLowerCase().includes(needle));
};

const normalizeKey = (value: string | null | undefined): string =>
  (value || '').trim().toLowerCase();

const asKnownZone = (zone: string | null | undefined): string | null => {
  const trimmed = (zone || '').trim();
  if (!trimmed) return null;
  return ZONE_SET.has(trimmed) ? trimmed : null;
};

export interface TimezoneLocationHint {
  countryIso2?: string | null;
  countryName?: string | null;
  stateRegionCode?: string | null;
  stateName?: string | null;
}

/**
 * Suggest an IANA timezone from country (+ optional state/province).
 * Returns null when no confident match exists in the curated list.
 */
export function suggestTimezoneFromLocation(hint: TimezoneLocationHint): string | null {
  const iso2 = (hint.countryIso2 || '').trim().toUpperCase();
  const region = (hint.stateRegionCode || '').trim().toUpperCase();
  const stateName = normalizeKey(hint.stateName);

  if (iso2 === 'US') {
    if (region && US_STATE_TIMEZONE[region]) {
      return asKnownZone(US_STATE_TIMEZONE[region]);
    }
    if (stateName && US_STATE_NAME_TIMEZONE[stateName]) {
      return asKnownZone(US_STATE_NAME_TIMEZONE[stateName]);
    }
    return null;
  }

  if (iso2 === 'CA') {
    if (region && CA_PROVINCE_TIMEZONE[region]) {
      return asKnownZone(CA_PROVINCE_TIMEZONE[region]);
    }
    if (stateName && CA_PROVINCE_NAME_TIMEZONE[stateName]) {
      return asKnownZone(CA_PROVINCE_NAME_TIMEZONE[stateName]);
    }
    return asKnownZone('America/Toronto');
  }

  if (iso2 === 'AU') {
    if (region && AU_STATE_TIMEZONE[region]) {
      return asKnownZone(AU_STATE_TIMEZONE[region]);
    }
    if (stateName && AU_STATE_NAME_TIMEZONE[stateName]) {
      return asKnownZone(AU_STATE_NAME_TIMEZONE[stateName]);
    }
    return asKnownZone('Australia/Sydney');
  }

  if (iso2 && COUNTRY_DEFAULT_TIMEZONE[iso2]) {
    return asKnownZone(COUNTRY_DEFAULT_TIMEZONE[iso2]);
  }

  const countryName = normalizeKey(hint.countryName);
  if (countryName.includes('united states') || countryName === 'usa') {
    if (region && US_STATE_TIMEZONE[region]) return asKnownZone(US_STATE_TIMEZONE[region]);
    if (stateName && US_STATE_NAME_TIMEZONE[stateName]) {
      return asKnownZone(US_STATE_NAME_TIMEZONE[stateName]);
    }
    return null;
  }
  if (countryName.includes('united kingdom') || countryName === 'uk') {
    return asKnownZone('Europe/London');
  }
  if (countryName === 'india') return asKnownZone('Asia/Kolkata');
  if (countryName === 'japan') return asKnownZone('Asia/Tokyo');
  if (countryName === 'singapore') return asKnownZone('Asia/Singapore');
  if (countryName === 'australia') {
    if (region && AU_STATE_TIMEZONE[region]) return asKnownZone(AU_STATE_TIMEZONE[region]);
    if (stateName && AU_STATE_NAME_TIMEZONE[stateName]) {
      return asKnownZone(AU_STATE_NAME_TIMEZONE[stateName]);
    }
    return asKnownZone('Australia/Sydney');
  }
  if (countryName === 'canada') {
    if (region && CA_PROVINCE_TIMEZONE[region]) return asKnownZone(CA_PROVINCE_TIMEZONE[region]);
    if (stateName && CA_PROVINCE_NAME_TIMEZONE[stateName]) {
      return asKnownZone(CA_PROVINCE_NAME_TIMEZONE[stateName]);
    }
    return asKnownZone('America/Toronto');
  }

  return null;
}
