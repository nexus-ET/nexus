export interface WizardStepHandle<T> {
  validate: () => Promise<boolean>;
  getValues: () => T;
  /** Live form values (not API-serialized). Used for inherit/copy into other steps. */
  getFormValues?: () => T;
  reset: (values: T) => void;
  isDirty: () => boolean;
  markClean: () => void;
  /** Most recent validation failure message from this step, if any. */
  getValidationError?: () => string | null;
  getCollegeAcademicOverrides?: () => string[];
  getCollegePictureOverrides?: () => string[];
  /**
   * Persist step-owned side effects before the wizard draft payload is written
   * (e.g. intake calendars live outside the draft JSON).
   */
  persistPending?: () => Promise<boolean>;
}
