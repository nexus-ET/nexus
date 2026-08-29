import type { ContactEntry } from '../schemas/contactEntry';

export interface InstitutionRecord {
  id: number;
  name: string;
  code?: string | null;
  country_id?: number | null;
  country_name?: string | null;
  institution_type_id?: number | null;
  institution_type_code?: string | null;
  institution_type_name?: string | null;
  accreditation_details?: string | null;
  address?: string | null;
  phone_numbers?: ContactEntry[];
  fax_numbers?: ContactEntry[];
  email_addresses?: ContactEntry[];
  dean_name?: string | null;
  year_established?: string | null;
  global_ranking?: string | null;
  national_ranking?: string | null;
  brochure_url?: string | null;
  tuition_fees?: string | null;
  hostel_expenses?: string | null;
  food_expense?: string | null;
  books_expense?: string | null;
  commutation_expense?: string | null;
  insurance_expense?: string | null;
  medical_expense?: string | null;
  other_expense?: string | null;
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
  description?: string | null;
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
  campus_id: number | null;
  campus_ids?: number[];
  linked_campuses?: Array<{
    campus_id: number;
    name: string;
    address?: string | null;
    location_label?: string | null;
    is_primary: boolean;
    source_url?: string | null;
    evidence?: string | null;
  }>;
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
  campus_names?: string[];
}

export interface InstitutionHierarchyCampusNode {
  id: number;
  name: string;
  location_label?: string | null;
  description?: string | null;
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
