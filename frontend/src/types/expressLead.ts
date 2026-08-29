export type ExpressLeadMatchedOn = 'email' | 'phone' | 'both';
export type ExpressLeadRecordKind = 'lead' | 'students_master';

export interface ExpressLeadMatch {
  id: number;
  full_name: string;
  email?: string | null;
  phone_number?: string | null;
  matched_on: ExpressLeadMatchedOn;
  stage: string;
  status_label: string;
  source?: string | null;
  source_label?: string | null;
  preferred_country?: string | null;
  academic_summary?: string | null;
  created_at?: string | null;
  record_kind?: ExpressLeadRecordKind;
  students_master_id?: number | null;
  lead_id?: number | null;
  page_path: string;
  page_label: string;
  prospects_path: string;
}

export interface ExpressLeadDuplicateCheck {
  email_match: ExpressLeadMatch | null;
  phone_match: ExpressLeadMatch | null;
}

export function parseExpressDuplicateError(raw: string): {
  message: string;
  matches: ExpressLeadMatch[];
} | null {
  const text = raw.trim();
  if (!text.startsWith('{')) return null;
  try {
    const parsed = JSON.parse(text) as { message?: unknown; matches?: unknown };
    if (!parsed || !Array.isArray(parsed.matches)) return null;
    const matches = parsed.matches.filter(
      (row): row is ExpressLeadMatch =>
        Boolean(row) &&
        typeof row === 'object' &&
        typeof (row as ExpressLeadMatch).id === 'number' &&
        typeof (row as ExpressLeadMatch).full_name === 'string' &&
        typeof (row as ExpressLeadMatch).page_path === 'string' &&
        typeof (row as ExpressLeadMatch).prospects_path === 'string'
    );
    if (!matches.length) return null;
    return {
      message:
        typeof parsed.message === 'string' && parsed.message.trim()
          ? parsed.message.trim()
          : 'This person already exists.',
      matches,
    };
  } catch {
    return null;
  }
}

export interface ExpressLeadCreatePayload {
  first_name: string;
  last_name: string;
  email: string;
  phone_country_iso2: string;
  phone_local: string;
  target_destination_iso2s: string[];
  target_major_ids: number[];
}

export interface ExpressLeadCreated {
  id: number;
  full_name: string;
  email?: string | null;
  phone_number?: string | null;
  stage: string;
  source: string;
  target_destination_iso2s: string[];
  target_destinations: string[];
  target_major_ids: number[];
  target_majors: string[];
}
