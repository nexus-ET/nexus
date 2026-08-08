/** ISO 3166-1 alpha-2 helpers for country flags. */

/** Convert ISO 3166-1 alpha-2 to a regional-indicator flag emoji (macOS/iOS; often blank on Windows). */
export function countryFlagEmoji(iso2: string | null | undefined): string {
  const code = (iso2 || '').trim().toUpperCase();
  if (!/^[A-Z]{2}$/.test(code)) return '🏳️';
  return String.fromCodePoint(...[...code].map(char => 0x1f1e6 - 65 + char.charCodeAt(0)));
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
