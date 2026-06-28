import type { GpaCgpaScoreRecord } from '../types/gpaCgpaScore';

export function gpaCgpaToFormFields(
  score: string | null | undefined,
  scoreCode: string | null | undefined,
  scores: GpaCgpaScoreRecord[]
): { gpa_cgpa_code: string; gpa_cgpa_other: string } {
  if (scoreCode) {
    const byCode = scores.find(item => item.code === scoreCode);
    if (byCode?.is_other) {
      return { gpa_cgpa_code: byCode.code, gpa_cgpa_other: score || '' };
    }
    return { gpa_cgpa_code: scoreCode, gpa_cgpa_other: '' };
  }

  if (score) {
    const byLabel = scores.find(
      item => item.label.toLowerCase() === score.toLowerCase() && !item.is_other
    );
    if (byLabel) {
      return { gpa_cgpa_code: byLabel.code, gpa_cgpa_other: '' };
    }
    const other = scores.find(item => item.is_other);
    return { gpa_cgpa_code: other?.code || 'OTHER', gpa_cgpa_other: score };
  }

  return { gpa_cgpa_code: '', gpa_cgpa_other: '' };
}

export function validateGpaCgpaScore(
  scoreCode: string | undefined,
  scoreOther: string | undefined,
  scores: GpaCgpaScoreRecord[]
): string | null {
  if (!scoreCode) return 'GPA/CGPA is required.';
  const selected = scores.find(item => item.code === scoreCode);
  if (!selected) return 'Select a valid GPA/CGPA score.';
  if (selected.is_other && !scoreOther?.trim()) {
    return 'Please enter the GPA/CGPA score when Other is selected.';
  }
  return null;
}
