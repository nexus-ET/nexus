/** Derive study/employment gaps from education + work timeline for intake 1.1. */

export type TimelineGap = {
  id: string;
  kind: 'study' | 'employment' | 'mixed';
  fromLabel: string;
  toLabel: string;
  months: number;
  summary: string;
};

type EduLike = {
  graduation_year?: number | null;
  graduation_month?: number | null;
  university_name?: string | null;
  degree_label?: string | null;
};

type WorkLike = {
  start_date?: string | null;
  end_date?: string | null;
  is_current?: boolean;
  company_name?: string | null;
  job_title?: string | null;
};

function monthIndex(year: number, month: number): number {
  return year * 12 + (month - 1);
}

function labelFromIndex(idx: number): string {
  const year = Math.floor(idx / 12);
  const month = (idx % 12) + 1;
  const names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${names[month - 1]} ${year}`;
}

function parseWorkStart(w: WorkLike): number | null {
  if (!w.start_date) return null;
  const d = new Date(w.start_date);
  if (Number.isNaN(d.getTime())) return null;
  return monthIndex(d.getFullYear(), d.getMonth() + 1);
}

function parseWorkEnd(w: WorkLike, nowIdx: number): number | null {
  if (w.is_current) return nowIdx;
  if (!w.end_date) return null;
  const d = new Date(w.end_date);
  if (Number.isNaN(d.getTime())) return null;
  return monthIndex(d.getFullYear(), d.getMonth() + 1);
}

function parseEduEnd(e: EduLike): number | null {
  if (!e.graduation_year) return null;
  const month = e.graduation_month && e.graduation_month >= 1 && e.graduation_month <= 12
    ? e.graduation_month
    : 6;
  return monthIndex(e.graduation_year, month);
}

/** Gaps ≥ 3 months between education end and next activity, or between work stints. */
export function computeProfileGaps(
  educations: EduLike[],
  experiences: WorkLike[],
  now = new Date()
): TimelineGap[] {
  const nowIdx = monthIndex(now.getFullYear(), now.getMonth() + 1);
  type Marker = { idx: number; label: string; kind: 'edu' | 'work' };
  const markers: Marker[] = [];

  educations.forEach(edu => {
    const idx = parseEduEnd(edu);
    if (idx == null) return;
    const name = edu.university_name || edu.degree_label || 'Education';
    markers.push({ idx, label: `Graduated · ${name}`, kind: 'edu' });
  });

  experiences.forEach(work => {
    const start = parseWorkStart(work);
    const end = parseWorkEnd(work, nowIdx);
    if (start == null) return;
    const role = [work.job_title, work.company_name].filter(Boolean).join(' @ ') || 'Employment';
    markers.push({ idx: start, label: `Started · ${role}`, kind: 'work' });
    if (end != null && end > start) {
      markers.push({
        idx: end,
        label: work.is_current ? `Ongoing · ${role}` : `Ended · ${role}`,
        kind: 'work',
      });
    }
  });

  if (markers.length < 2) {
    if (markers.length === 1) {
      const sole = markers[0];
      const months = nowIdx - sole.idx;
      if (months >= 3) {
        return [
          {
            id: 'sole-to-now',
            kind: sole.kind === 'edu' ? 'study' : 'employment',
            fromLabel: labelFromIndex(sole.idx),
            toLabel: labelFromIndex(nowIdx),
            months,
            summary: `${months} mo after ${sole.label} with no later activity on file`,
          },
        ];
      }
    }
    return [];
  }

  markers.sort((a, b) => a.idx - b.idx);
  const gaps: TimelineGap[] = [];
  for (let i = 0; i < markers.length - 1; i += 1) {
    const a = markers[i];
    const b = markers[i + 1];
    const months = b.idx - a.idx;
    if (months < 3) continue;
    // Skip contiguous work start/end of same stint (~0–2 already filtered)
    if (a.kind === 'work' && b.kind === 'work' && months < 3) continue;
    const kind: TimelineGap['kind'] =
      a.kind === 'edu' && b.kind === 'edu'
        ? 'study'
        : a.kind === 'work' && b.kind === 'work'
          ? 'employment'
          : 'mixed';
    gaps.push({
      id: `gap-${i}-${a.idx}-${b.idx}`,
      kind,
      fromLabel: labelFromIndex(a.idx),
      toLabel: labelFromIndex(b.idx),
      months,
      summary: `${months} mo between “${a.label}” and “${b.label}”`,
    });
  }
  return gaps;
}

export const COUNTRY_COST_PRESETS: Record<string, { currency: string; min: number; max: number; label: string }> = {
  US: { currency: 'USD', min: 25000, max: 70000, label: 'US tuition + COL estimate' },
  GB: { currency: 'GBP', min: 18000, max: 45000, label: 'UK tuition + COL estimate' },
  CA: { currency: 'CAD', min: 20000, max: 50000, label: 'Canada tuition + COL estimate' },
  AU: { currency: 'AUD', min: 22000, max: 55000, label: 'Australia tuition + COL estimate' },
  NZ: { currency: 'NZD', min: 18000, max: 42000, label: 'New Zealand tuition + COL estimate' },
  DE: { currency: 'EUR', min: 8000, max: 28000, label: 'Germany tuition + COL estimate' },
  FR: { currency: 'EUR', min: 10000, max: 32000, label: 'France tuition + COL estimate' },
  JP: { currency: 'JPY', min: 1200000, max: 3500000, label: 'Japan tuition + COL estimate' },
  SG: { currency: 'SGD', min: 22000, max: 55000, label: 'Singapore tuition + COL estimate' },
  AE: { currency: 'AED', min: 40000, max: 120000, label: 'UAE tuition + COL estimate' },
  SE: { currency: 'SEK', min: 90000, max: 250000, label: 'Sweden tuition + COL estimate' },
  CH: { currency: 'CHF', min: 18000, max: 45000, label: 'Switzerland tuition + COL estimate' },
};
