export interface EducationSuperMajorRecord {
  id: number;
  name: string;
  code: string;
  description?: string | null;
  sort_order: number;
  is_active: boolean;
  major_count?: number;
}

export interface EducationSuperMajorListResponse {
  items: EducationSuperMajorRecord[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}
