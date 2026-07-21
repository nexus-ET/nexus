import type { CSSProperties } from 'react';

export const MAJOR_COLOR_PALETTE = [
  '#6366F1',
  '#8B5CF6',
  '#EC4899',
  '#F43F5E',
  '#F97316',
  '#EAB308',
  '#22C55E',
  '#14B8A6',
  '#06B6D4',
  '#3B82F6',
  '#A855F7',
  '#84CC16',
] as const;

export type MajorColor = (typeof MAJOR_COLOR_PALETTE)[number];

export function normalizeMajorLabel(label: string): string {
  return label.trim().toLowerCase();
}

function hslToHex(hue: number, saturation: number, lightness: number): string {
  const s = saturation / 100;
  const l = lightness / 100;
  const chroma = (1 - Math.abs(2 * l - 1)) * s;
  const x = chroma * (1 - Math.abs(((hue / 60) % 2) - 1));
  const m = l - chroma / 2;

  let red = 0;
  let green = 0;
  let blue = 0;

  if (hue < 60) {
    red = chroma;
    green = x;
  } else if (hue < 120) {
    red = x;
    green = chroma;
  } else if (hue < 180) {
    green = chroma;
    blue = x;
  } else if (hue < 240) {
    green = x;
    blue = chroma;
  } else if (hue < 300) {
    red = x;
    blue = chroma;
  } else {
    red = chroma;
    blue = x;
  }

  const toByte = (value: number) =>
    Math.round((value + m) * 255)
      .toString(16)
      .padStart(2, '0')
      .toUpperCase();

  return `#${toByte(red)}${toByte(green)}${toByte(blue)}`;
}

function generateUniqueColor(
  used: Set<string>,
  label: string,
  majorCount: number
): string {
  const seed = [...normalizeMajorLabel(label)].reduce((sum, char) => sum + char.charCodeAt(0), 0) || 1;
  for (let attempt = 0; attempt < 360; attempt += 1) {
    const hue = (seed * 47 + majorCount * 29 + attempt * 41) % 360;
    const color = hslToHex(hue, 62, 50);
    if (!used.has(color.toUpperCase())) {
      return color;
    }
  }
  return hslToHex((seed * 17) % 360, 62, 50);
}

export function assignMajorColor(
  label: string,
  usedColors: Iterable<string | null | undefined> = [],
  majorCount = 0
): string {
  const used = new Set(
    [...usedColors]
      .filter((color): color is string => Boolean(color?.trim()))
      .map(color => color.toUpperCase())
  );
  const available = MAJOR_COLOR_PALETTE.find(color => !used.has(color.toUpperCase()));
  if (available) return available;
  return generateUniqueColor(used, label, majorCount);
}

export function buildMajorColorByLabel(
  majors: Array<{ label: string; color?: string | null; program_id?: string | null; id: number }>
): Map<string, string> {
  const sorted = [...majors].sort((left, right) => {
    if (!left.program_id && right.program_id) return -1;
    if (left.program_id && !right.program_id) return 1;
    return left.id - right.id;
  });

  const map = new Map<string, string>();
  for (const major of sorted) {
    if (!major.color) continue;
    const key = normalizeMajorLabel(major.label);
    if (!map.has(key)) {
      map.set(key, major.color);
    }
  }
  return map;
}

export function buildMajorColorById(
  majors: Array<{ id: number; color?: string | null }>
): Map<number, string> {
  const map = new Map<number, string>();
  for (const major of majors) {
    if (major.color) {
      map.set(major.id, major.color);
    }
  }
  return map;
}

export function resolveMajorColor(
  major: { id?: number; label: string; color?: string | null } | null | undefined,
  colorByLabel: Map<string, string>,
  colorById?: Map<number, string>
): string | undefined {
  if (!major) return undefined;
  if (major.color) return major.color;
  if (major.id && colorById?.has(major.id)) {
    return colorById.get(major.id);
  }
  return colorByLabel.get(normalizeMajorLabel(major.label));
}

function hexToRgb(hex: string): { r: number; g: number; b: number } | null {
  const normalized = hex.trim().replace('#', '');
  if (!/^[0-9a-fA-F]{6}$/.test(normalized)) return null;
  return {
    r: Number.parseInt(normalized.slice(0, 2), 16),
    g: Number.parseInt(normalized.slice(2, 4), 16),
    b: Number.parseInt(normalized.slice(4, 6), 16),
  };
}

export function majorColorStyles(color?: string | null) {
  const rgb = color ? hexToRgb(color) : null;
  if (!rgb) {
    return {
      borderColor: undefined,
      backgroundColor: undefined,
      badgeBackgroundColor: undefined,
      badgeBorderColor: undefined,
      textColor: undefined,
      swatchStyle: undefined,
    };
  }

  return {
    borderColor: `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, 0.45)`,
    backgroundColor: `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, 0.12)`,
    badgeBackgroundColor: `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, 0.16)`,
    badgeBorderColor: `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, 0.28)`,
    textColor: color,
    swatchStyle: { backgroundColor: color },
  };
}

export function majorMappingPanelStyle(color?: string | null): CSSProperties | undefined {
  const styles = majorColorStyles(color);
  if (!styles.borderColor || !styles.backgroundColor) return undefined;
  return {
    borderLeftWidth: '4px',
    borderLeftStyle: 'solid',
    borderLeftColor: styles.borderColor,
    backgroundColor: styles.backgroundColor,
  };
}
