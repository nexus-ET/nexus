import type { OfflineLeadCreatePayload } from '../types/offlineLead';

export function validateLocationFields(
  location: OfflineLeadCreatePayload['location']
): string | null {
  if (!location?.city?.trim()) return 'City is required.';
  if (!location?.state?.trim()) return 'State is required.';
  if (!location?.country_iso2) return 'Country is required.';
  return null;
}

export function validateStudyInterestFields(
  targetDestinationIso2?: string,
  targetProgramCode?: string,
  targetCourseCode?: string
): string | null {
  if (!targetDestinationIso2) return 'Target destination is required.';
  if (!targetProgramCode) return 'Target program is required.';
  if (!targetCourseCode) return 'Target course is required.';
  return null;
}
