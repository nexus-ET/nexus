/** Indian numbering format + amount-in-words for ROI INR equivalents. */

const ONES = [
  '',
  'one',
  'two',
  'three',
  'four',
  'five',
  'six',
  'seven',
  'eight',
  'nine',
  'ten',
  'eleven',
  'twelve',
  'thirteen',
  'fourteen',
  'fifteen',
  'sixteen',
  'seventeen',
  'eighteen',
  'nineteen',
];

const TENS = [
  '',
  '',
  'twenty',
  'thirty',
  'forty',
  'fifty',
  'sixty',
  'seventy',
  'eighty',
  'ninety',
];

function twoDigits(n: number): string {
  if (n < 20) return ONES[n];
  const ten = Math.floor(n / 10);
  const one = n % 10;
  return one ? `${TENS[ten]}-${ONES[one]}` : TENS[ten];
}

function threeDigits(n: number): string {
  const hundred = Math.floor(n / 100);
  const rest = n % 100;
  if (hundred && rest) return `${ONES[hundred]} hundred ${twoDigits(rest)}`;
  if (hundred) return `${ONES[hundred]} hundred`;
  return twoDigits(rest);
}

/** Convert a non-negative integer to Indian English words (lakh / crore). */
export function numberToIndianWords(value: number): string {
  const abs = Math.abs(Math.round(value));
  if (abs === 0) return 'zero';

  const crore = Math.floor(abs / 1_00_00_000);
  const lakh = Math.floor((abs % 1_00_00_000) / 1_00_000);
  const thousand = Math.floor((abs % 1_00_000) / 1000);
  const hundred = abs % 1000;

  const parts: string[] = [];
  if (crore) parts.push(`${threeDigits(crore)} crore`);
  if (lakh) parts.push(`${threeDigits(lakh)} lakh`);
  if (thousand) parts.push(`${threeDigits(thousand)} thousand`);
  if (hundred) parts.push(threeDigits(hundred));

  const words = parts.join(' ').replace(/\s+/g, ' ').trim();
  return value < 0 ? `minus ${words}` : words;
}

/** Format INR with Indian grouping: 12,34,567 */
export function formatInrNumber(value: number): string {
  const sign = value < 0 ? '-' : '';
  const rounded = Math.round(Math.abs(value));
  const str = String(rounded);
  if (str.length <= 3) return `${sign}₹${str}`;

  const last3 = str.slice(-3);
  let rest = str.slice(0, -3);
  const groups: string[] = [];
  while (rest.length > 2) {
    groups.unshift(rest.slice(-2));
    rest = rest.slice(0, -2);
  }
  if (rest) groups.unshift(rest);
  return `${sign}₹${groups.join(',')},${last3}`;
}

export function formatInrWithWords(value: number): { number: string; words: string } {
  return {
    number: formatInrNumber(value),
    words: `${numberToIndianWords(value)} rupees`,
  };
}
