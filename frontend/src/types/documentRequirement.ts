export interface DocumentRequirementCountry {
  id: number;
  iso2: string;
  name: string;
}

export interface DocumentTemplateSummary {
  id: number;
  template_name: string;
  file_url: string;
  file_size?: number | null;
  uploaded_by?: number | null;
  created_at?: string | null;
  download_url?: string | null;
}

export interface DocumentRequirementRecord {
  id: number;
  document_name: string;
  description?: string | null;
  accepted_format?: string | null;
  program_levels: string[];
  /** First level — kept for older clients; prefer program_levels. */
  program_level?: string | null;
  is_mandatory: boolean;
  is_global: boolean;
  template_id?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
  countries: DocumentRequirementCountry[];
  template?: DocumentTemplateSummary | null;
}

export interface DocumentRequirementListResponse {
  items: DocumentRequirementRecord[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface DocumentRequirementPayload {
  document_name: string;
  description?: string | null;
  accepted_format?: string | null;
  program_levels: string[];
  is_mandatory: boolean;
  is_global: boolean;
  country_ids: number[];
}

export interface DocumentTemplateDownloadResponse {
  template_id: number;
  template_name: string;
  file_url: string;
  download_url: string;
  file_size?: number | null;
}

export function resolveProgramLevels(
  row: Pick<DocumentRequirementRecord, 'program_levels' | 'program_level'>
): string[] {
  if (Array.isArray(row.program_levels) && row.program_levels.length > 0) {
    return row.program_levels.map(String);
  }
  if (row.program_level) {
    return [String(row.program_level)];
  }
  return [];
}

/** Merge catalog level names with any saved values missing from the catalog. */
export function mergeLevelOptions(
  catalogNames: string[],
  selectedValues: string[] = []
): { value: string; label: string }[] {
  const options: { value: string; label: string }[] = [];
  const seen = new Set<string>();
  for (const name of catalogNames) {
    const value = String(name || '').trim();
    if (!value || seen.has(value)) continue;
    seen.add(value);
    options.push({ value, label: value });
  }
  for (const raw of selectedValues) {
    const value = String(raw || '').trim();
    if (!value || seen.has(value)) continue;
    seen.add(value);
    options.push({ value, label: value });
  }
  return options;
}
