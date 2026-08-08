import { create } from 'zustand';
import { apiFetch } from '../utils/api';
import {
  emptyIntakeAssessment,
  type IntakeAssessmentPayload,
  type IntakeAssessmentResponse,
  type IntakeProfileSnapshot,
} from '../types/intakeAssessment';

type IntakeSessionStore = {
  bookingId: number | null;
  assessment: IntakeAssessmentPayload;
  profile: IntakeProfileSnapshot | null;
  loading: boolean;
  saving: boolean;
  saveError: string | null;
  lastSavedAt: string | null;
  hydrated: boolean;
  load: (bookingId: number) => Promise<void>;
  patchAssessment: (partial: Partial<IntakeAssessmentPayload>) => void;
  patchSection: <K extends keyof IntakeAssessmentPayload>(
    section: K,
    partial: Partial<IntakeAssessmentPayload[K]>
  ) => void;
  flushSave: () => Promise<void>;
  dispose: () => void;
  reset: () => void;
};

let saveTimer: ReturnType<typeof setTimeout> | null = null;

async function persist(bookingId: number, assessment: IntakeAssessmentPayload) {
  return (await apiFetch(`bookings/mine/${bookingId}/intake-assessment`, {
    method: 'PUT',
    body: JSON.stringify(assessment),
  })) as IntakeAssessmentResponse;
}

export const useIntakeSessionStore = create<IntakeSessionStore>((set, get) => ({
  bookingId: null,
  assessment: emptyIntakeAssessment(),
  profile: null,
  loading: false,
  saving: false,
  saveError: null,
  lastSavedAt: null,
  hydrated: false,

  reset: () => {
    if (saveTimer) {
      clearTimeout(saveTimer);
      saveTimer = null;
    }
    set({
      bookingId: null,
      assessment: emptyIntakeAssessment(),
      profile: null,
      loading: false,
      saving: false,
      saveError: null,
      lastSavedAt: null,
      hydrated: false,
    });
  },

  load: async (bookingId: number) => {
    if (saveTimer) {
      clearTimeout(saveTimer);
      saveTimer = null;
    }
    set({ loading: true, saveError: null, bookingId, hydrated: false });
    try {
      const data = (await apiFetch(
        `bookings/mine/${bookingId}/intake-assessment`
      )) as IntakeAssessmentResponse;
      set({
        bookingId,
        assessment: data.assessment || emptyIntakeAssessment(),
        profile: data.profile_snapshot || null,
        loading: false,
        hydrated: true,
        lastSavedAt: new Date().toISOString(),
      });
    } catch (err) {
      set({
        loading: false,
        hydrated: true,
        saveError: err instanceof Error ? err.message : 'Failed to load intake assessment',
        assessment: emptyIntakeAssessment(),
        profile: null,
      });
    }
  },

  patchAssessment: partial => {
    const next = { ...get().assessment, ...partial };
    set({ assessment: next });
    const bookingId = get().bookingId;
    if (!bookingId || !get().hydrated) return;
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      void get().flushSave();
    }, 600);
  },

  patchSection: (section, partial) => {
    const current = get().assessment;
    const next = {
      ...current,
      [section]: { ...current[section], ...partial },
    };
    set({ assessment: next });
    const bookingId = get().bookingId;
    if (!bookingId || !get().hydrated) return;
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      void get().flushSave();
    }, 600);
  },

  flushSave: async () => {
    const { bookingId, assessment, hydrated } = get();
    if (!bookingId || !hydrated) return;
    if (saveTimer) {
      clearTimeout(saveTimer);
      saveTimer = null;
    }
    set({ saving: true, saveError: null });
    try {
      const data = await persist(bookingId, assessment);
      // Ignore stale responses after booking switch / reset
      if (get().bookingId !== bookingId) return;
      set({
        saving: false,
        assessment: data.assessment || assessment,
        profile: data.profile_snapshot || get().profile,
        lastSavedAt: new Date().toISOString(),
      });
    } catch (err) {
      if (get().bookingId !== bookingId) return;
      set({
        saving: false,
        saveError: err instanceof Error ? err.message : 'Failed to save intake assessment',
      });
    }
  },

  /** Flush pending edits for the active booking, then clear local state (drawer close). */
  dispose: () => {
    const { bookingId, assessment, hydrated } = get();
    if (saveTimer) {
      clearTimeout(saveTimer);
      saveTimer = null;
    }
    if (bookingId && hydrated) {
      void persist(bookingId, assessment).catch(() => undefined);
    }
    set({
      bookingId: null,
      assessment: emptyIntakeAssessment(),
      profile: null,
      loading: false,
      saving: false,
      saveError: null,
      lastSavedAt: null,
      hydrated: false,
    });
  },
}));
