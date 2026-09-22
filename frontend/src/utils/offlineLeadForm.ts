import type { OfflineLeadCreatePayload } from '../types/offlineLead';

export function validateLocationFields(
  location: OfflineLeadCreatePayload['location'],
  options?: { requireComplete?: boolean }
): string | null {
  const city = location?.city?.trim() || '';
  const state = location?.state?.trim() || '';
  const country = location?.country_iso2 || '';
  const zip = location?.zip_code?.trim() || '';
  const address1 = location?.address_line_1?.trim() || '';
  const address2 = location?.address_line_2?.trim() || '';
  const hasGeo = Boolean(city || state || country || zip);
  const hasAddress = Boolean(address1 || address2);
  if (!hasGeo && !hasAddress) return null;
  if (options?.requireComplete === false) return null;
  // Address-only is allowed. If any geo field is started, require city/state/country.
  if (hasGeo) {
    if (!city) return 'City is required when location is provided.';
    if (!state) return 'State is required when location is provided.';
    if (!country) return 'Country is required when location is provided.';
  }
  return null;
}

export function validateStudyInterestFields(options: {
  targetDestinationIso2s?: string[];
  targetLevelId?: number | string | null;
  targetMajorIds?: number[];
  targetProgramCodes?: string[];
}): string | null {
  const destinations = options.targetDestinationIso2s || [];
  const majors = options.targetMajorIds || [];
  const programs = options.targetProgramCodes || [];
  const hasAny =
    destinations.length > 0 ||
    Boolean(options.targetLevelId) ||
    majors.length > 0 ||
    programs.length > 0;
  if (!hasAny) return null;
  if (!destinations.length) return 'Select at least one target destination.';
  if (destinations.length > 6) return 'Select up to 6 target destinations.';
  if (!options.targetLevelId) return 'Target level is required when study interest is provided.';
  if (!majors.length) return 'Select at least one target major.';
  if (majors.length > 3) return 'Select up to 3 target majors.';
  if (!programs.length) return 'Select at least one target program.';
  return null;
}
