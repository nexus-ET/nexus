export interface HierarchyStatusImpact {
  entity_type: 'level' | 'major' | 'program' | 'course';
  entity_id: string;
  entity_name: string;
  current_is_active: boolean;
  proposed_is_active: boolean;
  majors: number;
  programs: number;
  courses: number;
  message: string;
}
