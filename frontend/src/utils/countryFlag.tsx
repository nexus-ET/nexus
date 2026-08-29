/** ISO 3166-1 alpha-2 helpers for country flags. */

/** Convert ISO 3166-1 alpha-2 to a regional-indicator flag emoji (macOS/iOS; often blank on Windows). */
export function countryFlagEmoji(iso2: string | null | undefined): string {
  const code = (iso2 || '').trim().toUpperCase();
  if (!/^[A-Z]{2}$/.test(code)) return '🏳️';
  return String.fromCodePoint(...[...code].map(char => 0x1f1e6 - 65 + char.charCodeAt(0)));
}

const COUNTRY_NAME_TO_ISO2: Record<string, string> = {
  ae: 'AE',
  are: 'AE',
  emirates: 'AE',
  unitedarabemirates: 'AE',
  uae: 'AE',
  au: 'AU',
  aus: 'AU',
  australia: 'AU',
  ca: 'CA',
  can: 'CA',
  canada: 'CA',
  de: 'DE',
  deu: 'DE',
  germany: 'DE',
  deutschland: 'DE',
  fr: 'FR',
  fra: 'FR',
  france: 'FR',
  hk: 'HK',
  hkg: 'HK',
  hongkong: 'HK',
  in: 'IN',
  ind: 'IN',
  india: 'IN',
  ie: 'IE',
  irl: 'IE',
  ireland: 'IE',
  jp: 'JP',
  jpn: 'JP',
  japan: 'JP',
  my: 'MY',
  mys: 'MY',
  malaysia: 'MY',
  nl: 'NL',
  nld: 'NL',
  netherlands: 'NL',
  holland: 'NL',
  no: 'NO',
  nor: 'NO',
  norway: 'NO',
  newzealand: 'NZ',
  nz: 'NZ',
  nzl: 'NZ',
  pl: 'PL',
  pol: 'PL',
  poland: 'PL',
  qa: 'QA',
  qat: 'QA',
  qatar: 'QA',
  ru: 'RU',
  rus: 'RU',
  russia: 'RU',
  russianfederation: 'RU',
  sg: 'SG',
  sgp: 'SG',
  singapore: 'SG',
  gb: 'GB',
  gbr: 'GB',
  uk: 'GB',
  unitedkingdomofgreatbritainandnorthernireland: 'GB',
  unitedkingdom: 'GB',
  britain: 'GB',
  greatbritain: 'GB',
  england: 'GB',
  us: 'US',
  usa: 'US',
  unitedstates: 'US',
  unitedstatesofamerica: 'US',
  america: 'US',
};

const LEADING_FLAG_PATTERN = /^\p{Regional_Indicator}{2}\s*/u;

export function stripLeadingCountryFlag(value: string | null | undefined): string {
  return (value || '').trim().replace(LEADING_FLAG_PATTERN, '').trim();
}

/** Resolve the intake country names/codes used by WhatsApp to ISO alpha-2. */
export function countryIso2FromName(country: string | null | undefined): string | null {
  const value = stripLeadingCountryFlag(country);
  if (!value) return null;

  const normalized = value
    .toLowerCase()
    .replace(/[^a-z]/g, '');
  return COUNTRY_NAME_TO_ISO2[normalized] || null;
}

/** Prefix a known intake country with its flag, without duplicating an existing flag. */
export function formatCountryWithFlag(country: string | null | undefined): string {
  const value = (country || '').trim();
  if (!value || LEADING_FLAG_PATTERN.test(value)) return value;

  const iso2 = countryIso2FromName(value);
  return iso2 ? `${countryFlagEmoji(iso2)} ${value}` : value;
}

type CountryWithFlagProps = {
  country: string | null | undefined;
  className?: string;
  size?: 'sm' | 'md' | 'lg';
};

/** Country label with an image flag, including on Windows where flag emoji render blank. */
export function CountryWithFlag({ country, className = '', size = 'sm' }: CountryWithFlagProps) {
  const label = stripLeadingCountryFlag(country);
  const iso2 = countryIso2FromName(country);
  if (!label) return null;
  if (!iso2) return <>{label}</>;

  return (
    <span className={`inline-flex items-center gap-1.5 ${className}`}>
      <CountryFlag iso2={iso2} title={label} size={size} />
      <span>{label}</span>
    </span>
  );
}

/** PNG flag URL via flagcdn (reliable across Windows / browsers). */
export function countryFlagUrl(
  iso2: string | null | undefined,
  width: 20 | 40 | 80 = 40
): string | null {
  const code = (iso2 || '').trim().toLowerCase();
  if (!/^[a-z]{2}$/.test(code)) return null;
  return `https://flagcdn.com/w${width}/${code}.png`;
}

type CountryFlagProps = {
  iso2: string | null | undefined;
  title?: string;
  className?: string;
  size?: 'sm' | 'md' | 'lg';
};

const SIZE_CLASS = {
  sm: 'h-5 w-7',
  md: 'h-6 w-8',
  lg: 'h-7 w-10',
} as const;

const SIZE_WIDTH = {
  sm: 20,
  md: 40,
  lg: 40,
} as const;

/** Image-based flag icon — works on Windows where emoji flags do not. */
export function CountryFlag({ iso2, title, className = '', size = 'md' }: CountryFlagProps) {
  const code = (iso2 || '').trim().toUpperCase();
  const src = countryFlagUrl(code, SIZE_WIDTH[size]);

  if (!src) {
    return (
      <span
        className={`inline-flex shrink-0 items-center justify-center rounded-sm bg-surface-bg text-[10px] font-semibold text-text-muted ${SIZE_CLASS[size]} ${className}`}
        title={title || 'Unknown'}
        aria-hidden
      >
        ?
      </span>
    );
  }

  return (
    <img
      src={src}
      alt=""
      title={title || code}
      loading="lazy"
      decoding="async"
      className={`inline-block shrink-0 rounded-sm object-cover shadow-sm ${SIZE_CLASS[size]} ${className}`}
      aria-hidden
    />
  );
}
