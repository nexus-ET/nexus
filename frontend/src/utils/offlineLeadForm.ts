import type { OfflineLeadCreatePayload } from '../types/offlineLead';

export function validateLocationFields(
  location: OfflineLeadCreatePayload['location']
): string | null {
  if (!location?.city?.trim()) return 'City is required.';
  if (!location?.state?.trim()) return 'State is required.';
  if (!location?.country_iso2) return 'Country is required.';
  return null;
}

export function validateStudyInterestFields(options: {
  targetDestinationIso2s?: string[];
  targetLevelId?: number | string | null;
  targetMajorIds?: number[];
  targetProgramCodes?: string[];
}): string | null {
  const destinations = options.targetDestinationIso2s || [];
  if (!destinations.length) return 'Select at least one target destination.';
  if (destinations.length > 6) return 'Select up to 6 target destinations.';
  if (!options.targetLevelId) return 'Target level is required.';
  const majors = options.targetMajorIds || [];
  if (!majors.length) return 'Select at least one target major.';
  if (majors.length > 3) return 'Select up to 3 target majors.';
  const programs = options.targetProgramCodes || [];
  if (!programs.length) return 'Select at least one target program.';
  return null;
}
