/** Global destination taxonomy for FlowX country workflow catalog. */

export type FlowxMacroRegion =
  | 'NAM'
  | 'UK_IRE'
  | 'ANZ'
  | 'EUR'
  | 'ASIA_HUB'
  | 'MENA'
  | 'LATAM'
  | 'ROW';

export interface FlowxMacroRegionMeta {
  key: FlowxMacroRegion;
  code: string;
  label: string;
  description: string;
  /** Core compliance / operational shared traits for the region. */
  traits: string;
}

export const FLOWX_MACRO_REGIONS: FlowxMacroRegionMeta[] = [
  {
    key: 'NAM',
    code: 'NAM',
    label: 'North America',
    description: 'United States, Canada, Mexico',
    traits:
      'Standardized testing (SAT/GRE/GMAT), F-1 / I-20 & SEVIS (USA), SDS / Study Permit & GIC (Canada).',
  },
  {
    key: 'UK_IRE',
    code: 'UK_IRE',
    label: 'UK & Ireland',
    description: 'United Kingdom, Republic of Ireland',
    traits:
      'UCAS centralized apps, CAS, points-based visas, Immigration Health Surcharge (IHS), critical English proficiency (IELTS/PTE).',
  },
  {
    key: 'ANZ',
    code: 'ANZ',
    label: 'Australasia',
    description: 'Australia, New Zealand, Fiji',
    traits:
      'Genuine Student (GS) / Genuine Temporary Entrant (GTE) tests, CoE issuance, mid-year/Feb intake structures.',
  },
  {
    key: 'EUR',
    code: 'EUR',
    label: 'Europe',
    description:
      'Germany, France, Netherlands, Sweden, Finland, Switzerland, Italy, Spain, Denmark, Norway, Austria, Belgium, Poland, Czech Republic, Hungary',
    traits:
      'APS certificates (Germany), blocked accounts, tuition-free/low-tuition public models, ECTS credit conversions, Erasmus guidelines.',
  },
  {
    key: 'ASIA_HUB',
    code: 'ASIA_HUB',
    label: 'Asia Hubs',
    description:
      'Japan, South Korea, Singapore, Malaysia, China, Hong Kong, Taiwan, Thailand',
    traits:
      'Language certifications (JLPT, TOPIK, HSK), localized student passes, high-tech/business hub corporate placement tracks.',
  },
  {
    key: 'MENA',
    code: 'MENA',
    label: 'MENA',
    description:
      'United Arab Emirates, Qatar, Saudi Arabia, Oman, Egypt, Turkey, Bahrain, Kuwait',
    traits:
      'Transnational Education (TNE) branch campuses, regional residency visas, government scholarship compliance tracking.',
  },
  {
    key: 'LATAM',
    code: 'LATAM',
    label: 'LatAm',
    description: 'Argentina, Brazil, Chile, Colombia, Costa Rica, Peru',
    traits:
      'Emerging Spanish/Portuguese medium programs, specialized regional exchange agreements.',
  },
  {
    key: 'ROW',
    code: 'ROW',
    label: 'RoW',
    description: 'South Africa, Israel, Cyprus, Malta, and any unmapped nation',
    traits: 'Generic multi-track workflows, fallback manual compliance checks.',
  },
];

/** ISO 3166-1 alpha-2 → destination region. Unmapped codes fall back to ROW. */
const ISO2_TO_REGION: Record<string, FlowxMacroRegion> = {
  // NAM — North America
  US: 'NAM',
  CA: 'NAM',
  MX: 'NAM',
  // UK_IRE
  GB: 'UK_IRE',
  IE: 'UK_IRE',
  // ANZ — Australasia / Oceania
  AU: 'ANZ',
  NZ: 'ANZ',
  FJ: 'ANZ',
  // EUR — Continental Europe
  DE: 'EUR',
  FR: 'EUR',
  NL: 'EUR',
  SE: 'EUR',
  FI: 'EUR',
  CH: 'EUR',
  IT: 'EUR',
  ES: 'EUR',
  DK: 'EUR',
  NO: 'EUR',
  AT: 'EUR',
  BE: 'EUR',
  PL: 'EUR',
  CZ: 'EUR',
  HU: 'EUR',
  // ASIA_HUB
  JP: 'ASIA_HUB',
  KR: 'ASIA_HUB',
  SG: 'ASIA_HUB',
  MY: 'ASIA_HUB',
  CN: 'ASIA_HUB',
  HK: 'ASIA_HUB',
  TW: 'ASIA_HUB',
  TH: 'ASIA_HUB',
  // MENA
  AE: 'MENA',
  QA: 'MENA',
  SA: 'MENA',
  OM: 'MENA',
  EG: 'MENA',
  TR: 'MENA',
  BH: 'MENA',
  KW: 'MENA',
  // LATAM
  AR: 'LATAM',
  BR: 'LATAM',
  CL: 'LATAM',
  CO: 'LATAM',
  CR: 'LATAM',
  PE: 'LATAM',
  // ROW — explicit fallback destinations
  ZA: 'ROW',
  IL: 'ROW',
  CY: 'ROW',
  MT: 'ROW',
};

const HIDDEN_REGIONS_STORAGE_KEY = 'flowx-hidden-regions';

export function getFlowxMacroRegion(iso2: string): FlowxMacroRegion {
  const code = (iso2 || '').trim().toUpperCase();
  return ISO2_TO_REGION[code] ?? 'ROW';
}

export function getFlowxRegionMeta(key: FlowxMacroRegion): FlowxMacroRegionMeta {
  return (
    FLOWX_MACRO_REGIONS.find(region => region.key === key) ??
    FLOWX_MACRO_REGIONS[FLOWX_MACRO_REGIONS.length - 1]
  );
}

export function loadHiddenFlowxRegions(): Set<FlowxMacroRegion> {
  try {
    const raw = localStorage.getItem(HIDDEN_REGIONS_STORAGE_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return new Set();
    const valid = new Set(FLOWX_MACRO_REGIONS.map(r => r.key));
    return new Set(parsed.filter((key): key is FlowxMacroRegion => valid.has(key as FlowxMacroRegion)));
  } catch {
    return new Set();
  }
}

export function saveHiddenFlowxRegions(hidden: Set<FlowxMacroRegion>): void {
  localStorage.setItem(HIDDEN_REGIONS_STORAGE_KEY, JSON.stringify([...hidden]));
}
