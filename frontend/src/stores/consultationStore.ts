import { create } from 'zustand';
import {
  computeAspirationsProgress,
  detectAspirationMismatches,
  type AspirationMismatchFlag,
} from '../config/aspirations.config';
import {
  emptyAspirationsForm,
  type StudentAspirationsFormState,
} from '../types/studentAspirations';

type FormPatch =
  | Partial<StudentAspirationsFormState>
  | ((prev: StudentAspirationsFormState) => Partial<StudentAspirationsFormState>);

type ConsultationStore = {
  bookingId: number | null;
  form: StudentAspirationsFormState;
  baseline: StudentAspirationsFormState;
  loading: boolean;
  saving: boolean;
  error: string | null;
  success: string | null;
  savedAt: string | null;
  validationErrors: string[];
  hydrated: boolean;
  hydrate: (payload: {
    form: StudentAspirationsFormState;
    bookingId?: number | null;
    savedAt?: string | null;
  }) => void;
  patchForm: (partialOrUpdater: FormPatch) => void;
  resetToBaseline: () => void;
  setBaseline: (form: StudentAspirationsFormState) => void;
  setLoading: (loading: boolean) => void;
  setSaving: (saving: boolean) => void;
  setError: (error: string | null) => void;
  setSuccess: (success: string | null) => void;
  setSavedAt: (savedAt: string | null) => void;
  setValidationErrors: (errors: string[]) => void;
  getProgress: () => ReturnType<typeof computeAspirationsProgress>;
  getMismatchFlags: () => AspirationMismatchFlag[];
  dispose: () => void;
};

export const useConsultationStore = create<ConsultationStore>((set, get) => ({
  bookingId: null,
  form: emptyAspirationsForm(),
  baseline: emptyAspirationsForm(),
  loading: false,
  saving: false,
  error: null,
  success: null,
  savedAt: null,
  validationErrors: [],
  hydrated: false,

  hydrate: ({ form, bookingId = null, savedAt = null }) => {
    set({
      form,
      baseline: form,
      bookingId: bookingId ?? null,
      savedAt: savedAt ?? null,
      loading: false,
      error: null,
      success: null,
      validationErrors: [],
      hydrated: true,
    });
  },

  patchForm: partialOrUpdater => {
    set(state => {
      const partial =
        typeof partialOrUpdater === 'function'
          ? partialOrUpdater(state.form)
          : partialOrUpdater;
      return {
        form: { ...state.form, ...partial },
        success: null,
        validationErrors: [],
      };
    });
  },

  resetToBaseline: () => {
    const { baseline } = get();
    set({
      form: baseline,
      error: null,
      success: null,
      validationErrors: [],
    });
  },

  setBaseline: form => set({ baseline: form, form }),
  setLoading: loading => set({ loading }),
  setSaving: saving => set({ saving }),
  setError: error => set({ error }),
  setSuccess: success => set({ success }),
  setSavedAt: savedAt => set({ savedAt }),
  setValidationErrors: validationErrors => set({ validationErrors }),

  getProgress: () => computeAspirationsProgress(get().form),
  getMismatchFlags: () => detectAspirationMismatches(get().form),

  dispose: () => {
    set({
      bookingId: null,
      form: emptyAspirationsForm(),
      baseline: emptyAspirationsForm(),
      loading: false,
      saving: false,
      error: null,
      success: null,
      savedAt: null,
      validationErrors: [],
      hydrated: false,
    });
  },
}));
