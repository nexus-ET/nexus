export type AcademiaFieldType = 'text' | 'number' | 'checkbox' | 'select';

export interface AcademiaSearchResult {
  entity_type: string;
  entity_label: string;
  category: string;
  id: number;
  title: string;
  subtitle?: string | null;
  path: string;
}

export interface AcademiaFieldConfig {
  key: string;
  label: string;
  type?: AcademiaFieldType;
  required?: boolean;
  placeholder?: string;
  optionsSource?: 'countries' | 'states' | 'institutions' | 'campuses' | 'programs' | 'cities';
  optionValueKey?: string;
  optionLabelKey?: string;
}

export interface AcademiaEntityConfig {
  listColumns: Array<{ key: string; label: string }>;
  fields: AcademiaFieldConfig[];
  redirectToListAfterCreate?: boolean;
}

export const ACADEMIA_ENTITY_CONFIG: Record<string, AcademiaEntityConfig> = {
  countries: {
    listColumns: [
      { key: 'name', label: 'Name' },
      { key: 'iso2', label: 'ISO Code' },
      { key: 'dial_code', label: 'Dial code' },
      { key: 'is_active', label: 'Active' },
    ],
    fields: [
      { key: 'name', label: 'Name', required: true },
      { key: 'iso2', label: 'ISO Code', required: true, placeholder: 'US' },
      { key: 'dial_code', label: 'Dial code', required: true, placeholder: '+1' },
      { key: 'sort_order', label: 'Sort order', type: 'number' },
      { key: 'is_active', label: 'Active', type: 'checkbox' },
    ],
  },
  states: {
    redirectToListAfterCreate: true,
    listColumns: [
      { key: 'name', label: 'Name' },
      { key: 'region_code', label: 'Region code' },
      { key: 'country_name', label: 'Country' },
      { key: 'is_active', label: 'Active' },
    ],
    fields: [
      { key: 'name', label: 'Name', required: true },
      { key: 'region_code', label: 'Region code', placeholder: 'CA, ON, KA' },
      {
        key: 'country_id',
        label: 'Country',
        type: 'select',
        required: true,
        optionsSource: 'countries',
        optionValueKey: 'id',
        optionLabelKey: 'name',
      },
      { key: 'sort_order', label: 'Sort order', type: 'number' },
      { key: 'is_active', label: 'Active', type: 'checkbox' },
    ],
  },
  institutions: {
    listColumns: [
      { key: 'name', label: 'Name' },
      { key: 'code', label: 'Code' },
      { key: 'country_name', label: 'Country' },
      { key: 'campus_count', label: 'Campuses' },
      { key: 'is_active', label: 'Active' },
    ],
    fields: [
      { key: 'name', label: 'Name', required: true },
      { key: 'accreditation_details', label: 'Accreditation details', placeholder: 'Regional body, validity...' },
      { key: 'code', label: 'Code' },
      { key: 'institution_type', label: 'Type', placeholder: 'Public / Private' },
      {
        key: 'country_id',
        label: 'Country',
        type: 'select',
        optionsSource: 'countries',
        optionValueKey: 'id',
        optionLabelKey: 'name',
      },
      { key: 'sort_order', label: 'Sort order', type: 'number' },
      { key: 'is_active', label: 'Active', type: 'checkbox' },
    ],
  },
  campuses: {
    listColumns: [
      { key: 'name', label: 'Name' },
      { key: 'institution_name', label: 'Institution' },
      { key: 'location_label', label: 'Location' },
      { key: 'is_active', label: 'Active' },
    ],
    fields: [
      {
        key: 'institution_id',
        label: 'Institution',
        type: 'select',
        required: true,
        optionsSource: 'institutions',
        optionValueKey: 'id',
        optionLabelKey: 'name',
      },
      { key: 'name', label: 'Name', required: true },
      {
        key: 'location_id',
        label: 'City location',
        type: 'select',
        required: true,
        optionsSource: 'cities',
        optionValueKey: 'id',
        optionLabelKey: 'name',
      },
      { key: 'sort_order', label: 'Sort order', type: 'number' },
      { key: 'is_active', label: 'Active', type: 'checkbox' },
    ],
  },
  colleges: {
    listColumns: [
      { key: 'hierarchy_breadcrumb', label: 'Path' },
      { key: 'name', label: 'Name' },
      { key: 'dean_name', label: 'Dean' },
      { key: 'is_active', label: 'Active' },
    ],
    fields: [
      {
        key: 'institution_id',
        label: 'Institution',
        type: 'select',
        required: true,
        optionsSource: 'institutions',
        optionValueKey: 'id',
        optionLabelKey: 'name',
      },
      {
        key: 'campus_id',
        label: 'Campus',
        type: 'select',
        required: true,
        optionsSource: 'campuses',
        optionValueKey: 'id',
        optionLabelKey: 'name',
      },
      { key: 'name', label: 'Name', required: true },
      { key: 'dean_name', label: 'Dean name' },
      { key: 'sort_order', label: 'Sort order', type: 'number' },
      { key: 'is_active', label: 'Active', type: 'checkbox' },
    ],
  },
};
