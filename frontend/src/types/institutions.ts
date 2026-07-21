import type { ContactEntry } from '../schemas/contactEntry';

export interface InstitutionRecord {
  id: number;
  name: string;
  code?: string | null;
  country_id?: number | null;
  country_name?: string | null;
  institution_type?: string | null;
  accreditation_details?: string | null;
  address?: string | null;
  phone_numbers?: ContactEntry[];
  fax_numbers?: ContactEntry[];
  email_addresses?: ContactEntry[];
  dean_name?: string | null;
  is_active: boolean;
  sort_order: number;
  campus_count?: number;
  college_count?: number;
}

export interface CampusRecord {
  id: number;
  institution_id: number;
  location_id?: number | null;
  name: string;
  campus_type_id?: number | null;
  campus_type_code?: string | null;
  campus_type_name?: string | null;
  campus_type_description?: string | null;
  is_residential?: boolean | null;
  is_active: boolean;
  sort_order: number;
  institution_name?: string | null;
  location_name?: string | null;
  location_label?: string | null;
  phone_numbers?: ContactEntry[];
  fax_numbers?: ContactEntry[];
  email_addresses?: ContactEntry[];
  web_links?: ContactEntry[];
}

export interface CollegeRecord {
  id: number;
  institution_id: number;
  campus_id: number;
  name: string;
  code?: string | null;
  category?: string | null;
  dean_name?: string | null;
  web_url?: string | null;
  web_links?: ContactEntry[];
  phone_numbers?: ContactEntry[];
  email_addresses?: ContactEntry[];
  is_active: boolean;
  sort_order: number;
  institution_name?: string | null;
  campus_name?: string | null;
  campus_address?: string | null;
  campus_location_label?: string | null;
  hierarchy_breadcrumb?: string | null;
}

export interface CityOption {
  id: number;
  name: string;
  country_id: number;
  state_id: number;
  country_name?: string | null;
  state_name?: string | null;
}

export interface InstitutionHierarchyCollegeNode {
  id: number;
  name: string;
  dean_name?: string | null;
}

export interface InstitutionHierarchyCampusNode {
  id: number;
  name: string;
  location_label?: string | null;
  colleges: InstitutionHierarchyCollegeNode[];
}

export interface InstitutionHierarchyNode {
  id: number;
  name: string;
  accreditation_details?: string | null;
  campuses: InstitutionHierarchyCampusNode[];
}

export interface InstitutionalHierarchySummary {
  institutions: InstitutionHierarchyNode[];
}

export const INSTITUTIONS_MANAGE_PATH = '/academia/institutions';
