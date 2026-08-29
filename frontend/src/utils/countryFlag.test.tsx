import { describe, expect, it } from 'vitest';
import { countryIso2FromName, stripLeadingCountryFlag } from './countryFlag';

describe('country flag normalization', () => {
  it.each([
    ['United States', 'US'],
    ['USA', 'US'],
    ['America', 'US'],
    ['GBR', 'GB'],
    ['Britain', 'GB'],
    ['United Arab Emirates', 'AE'],
    ['ARE', 'AE'],
    ['AUS', 'AU'],
    ['🇨🇦 Canada', 'CA'],
  ])('normalizes %s to %s', (country, iso2) => {
    expect(countryIso2FromName(country)).toBe(iso2);
  });

  it('removes an existing emoji before rendering an image flag', () => {
    expect(stripLeadingCountryFlag('🇦🇺 Australia')).toBe('Australia');
  });
});
