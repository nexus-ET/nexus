import React, { useEffect, useRef } from 'react';
import { Loader2 } from 'lucide-react';
import { AcademicProfileSection } from './aspirations/AcademicProfileSection';
import { AspirationsSummaryCard } from './aspirations/AspirationsSummaryCard';
import { CoreVisionSection } from './aspirations/CoreVisionSection';
import { FinancialFrameworkSection } from './aspirations/FinancialFrameworkSection';
import { TimelineReadinessSection } from './aspirations/TimelineReadinessSection';
import { useConsultationStore } from '../stores/consultationStore';
import { apiFetch } from '../utils/api';
import {
  aspirationsToForm,
  aspirationsToSavePayload,
  emptyAspirationsForm,
  validateAspirationsForm,
  type StudentAspirationsResponse,
} from '../types/studentAspirations';

interface MyAspirationsTabProps {
  bookingId?: number;
  compact?: boolean;
}

export default function MyAspirationsTab({ bookingId, compact = false }: MyAspirationsTabProps) {
  const apiPath = bookingId
    ? `bookings/mine/${bookingId}/aspirations`
    : 'users/me/aspirations';

  const loading = useConsultationStore(state => state.loading);
  const saving = useConsultationStore(state => state.saving);
  const error = useConsultationStore(state => state.error);
  const success = useConsultationStore(state => state.success);
  const savedAt = useConsultationStore(state => state.savedAt);
  const validationErrors = useConsultationStore(state => state.validationErrors);
  const loadSeq = useRef(0);

  useEffect(() => {
    const seq = ++loadSeq.current;
    const hydrate = useConsultationStore.getState().hydrate;
    const setLoading = useConsultationStore.getState().setLoading;
    const setError = useConsultationStore.getState().setError;

    // Ensure score-capture can resolve the booking before the async hydrate finishes.
    if (bookingId != null) {
      useConsultationStore.setState({ bookingId });
    }

    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        setError(null);
        const response = (await apiFetch(apiPath)) as StudentAspirationsResponse;
        if (cancelled || seq !== loadSeq.current) return;
        hydrate({
          form: aspirationsToForm(response.aspirations),
          bookingId: bookingId ?? null,
          savedAt: response.saved_at || null,
        });
      } catch (err) {
        if (cancelled || seq !== loadSeq.current) return;
        setError(err instanceof Error ? err.message : 'Failed to load aspirations.');
        hydrate({
          form: emptyAspirationsForm(),
          bookingId: bookingId ?? null,
          savedAt: null,
        });
      } finally {
        if (!cancelled && seq === loadSeq.current) {
          setLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [apiPath, bookingId]);

  useEffect(() => {
    return () => {
      useConsultationStore.getState().dispose();
    };
  }, []);

  const handleCancel = () => {
    useConsultationStore.getState().resetToBaseline();
  };

  const handleSave = async (event: React.FormEvent) => {
    event.preventDefault();
    const {
      form,
      setValidationErrors,
      setError,
      setSuccess,
      setSaving,
      setBaseline,
      setSavedAt,
    } = useConsultationStore.getState();

    const errors = validateAspirationsForm(form);
    if (errors.length > 0) {
      setValidationErrors(errors);
      setError('Please complete all required fields before saving.');
      setSuccess(null);
      return;
    }

    try {
      setSaving(true);
      setError(null);
      setSuccess(null);
      setValidationErrors([]);
      const payload = aspirationsToSavePayload(form);
      const response = (await apiFetch(apiPath, {
        method: 'PUT',
        body: JSON.stringify(payload),
      })) as StudentAspirationsResponse;
      const next = aspirationsToForm(response.aspirations);
      setBaseline(next);
      setSavedAt(response.saved_at || new Date().toISOString());
      setSuccess('Your aspirations have been saved.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save aspirations.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16 text-text-muted text-sm">
        <Loader2 size={22} className="animate-spin mr-2" />
        Loading aspirations questionnaire...
      </div>
    );
  }

  return (
    <form onSubmit={handleSave} className={compact ? 'flex flex-1 min-h-0 flex-col' : 'space-y-4'}>
      {!compact ? (
        <div>
          <h3 className="text-lg font-bold text-text-main">Aspirations</h3>
          <p className="text-sm text-text-muted mt-1">
            Consultation intake across vision, academics, funding, and readiness.
          </p>
          {savedAt ? (
            <p className="text-sm text-emerald-700 mt-1">
              Last saved {new Date(savedAt).toLocaleString()}
            </p>
          ) : null}
        </div>
      ) : savedAt ? (
        <p className="text-sm font-semibold text-emerald-700 shrink-0">
          Last saved {new Date(savedAt).toLocaleString()}
        </p>
      ) : null}

      <div
        className={
          compact
            ? 'flex-1 min-h-0 overflow-y-auto custom-scrollbar space-y-4 pr-1'
            : 'space-y-4'
        }
      >
        {error ? (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
            {validationErrors.length > 0 ? (
              <ul className="mt-2 list-disc pl-4 space-y-0.5 text-sm">
                {validationErrors.map(item => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
        {success ? (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
            {success}
          </div>
        ) : null}

        <AspirationsSummaryCard />
        <CoreVisionSection />
        <AcademicProfileSection />
        <FinancialFrameworkSection />
        <TimelineReadinessSection bookingId={bookingId} />
      </div>

      <div
        className={
          compact
            ? 'shrink-0 flex items-center justify-end gap-2 pt-3 mt-2 border-t border-border-subtle bg-white'
            : 'flex items-center justify-end gap-2 pt-2'
        }
      >
        <button
          type="button"
          onClick={handleCancel}
          disabled={saving}
          className="rounded-md border border-border-subtle bg-white px-4 py-2 text-sm font-semibold text-text-main hover:bg-surface-bg disabled:opacity-60"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={saving}
          className="inline-flex items-center rounded-md bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary/90 disabled:opacity-60"
        >
          {saving ? (
            <>
              <Loader2 size={16} className="animate-spin mr-2" />
              Saving...
            </>
          ) : (
            'Save aspirations'
          )}
        </button>
      </div>
    </form>
  );
}
